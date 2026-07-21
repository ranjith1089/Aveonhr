"""Resolve a SalaryStructure into a payslip computation.

This is the configurable engine that drives NEW draft runs. It evaluates
each component's formula in dependency order, applies per-component
rounding, derives the gross/deductions/net/employer/CTC totals from
component kinds, and bridges the standard component codes back onto the
legacy PayslipEntry columns so every downstream consumer (payslip PDF,
Excel register, month comparison) keeps working unchanged.

Finalized and imported runs are never routed through here - they keep the
stored values they already have.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from ..models import SalaryComponent
from .formula_engine import component_dependencies, evaluate, order_components

TWO_DP = Decimal("0.01")

# Standard component code -> legacy PayslipEntry column. Keeps the PDF /
# export / comparison contracts intact while the component table is the
# source of truth and audit log.
LEGACY_COLUMN = {
    "BASIC": "basic",
    "DA": "da",
    "HRA": "hra",
    "TRANSPORT": "transport_allowance",
    "FOOD": "food_allowance",
    "ESI_EMP": "esi_employee",
    "ESI_ER": "esi_employer",
    "PF_EMP": "pf_employee",
    "PF_ER": "pf_employer",
}

_ROUNDINGS = {
    SalaryComponent.Rounding.HALF_UP: ROUND_HALF_UP,
    SalaryComponent.Rounding.CEILING: ROUND_CEILING,
    SalaryComponent.Rounding.FLOOR: ROUND_FLOOR,
}


@dataclass
class ResolvedComponent:
    code: str
    name: str
    kind: str
    amount: Decimal
    sequence: int
    source_expr: str


@dataclass
class StructureComputation:
    present_days: Decimal
    pay_days: Decimal
    components: list  # ResolvedComponent, in display (sequence) order
    gross_salary: Decimal
    total_deductions: Decimal
    net_payable: Decimal
    employer_contributions: Decimal
    ctc: Decimal


def _apply_rounding(value: Decimal, rounding: str, decimals: int) -> Decimal:
    places = int(decimals)
    quant = Decimal(1) if places <= 0 else Decimal(1).scaleb(-places)
    mode = _ROUNDINGS.get(rounding)
    if mode is None:  # NONE -> store at the column's 2dp precision, unrounded intent
        return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)
    return value.quantize(quant, rounding=mode)


def compute_entry_from_structure(
    structure,
    *,
    monthly_package: Decimal,
    total_working_days: int,
    emp_leave_days: Decimal = Decimal("0"),
    lop_days: Decimal = Decimal("0"),
    internet_allowance: Decimal = Decimal("0"),
    salary_arrear_allowance: Decimal = Decimal("0"),
    salary_advance: Decimal = Decimal("0"),
    tds: Decimal = Decimal("0"),
    is_esi_eligible: bool = False,
    is_pf_applicable: bool = False,
) -> StructureComputation:
    twd = Decimal(total_working_days)
    present_days = twd - emp_leave_days
    pay_days = twd - lop_days

    context = {
        "PACKAGE": monthly_package, "TWD": twd, "PAY_DAYS": pay_days,
        "PRESENT_DAYS": present_days, "LOP_DAYS": lop_days,
        "EMP_LEAVE_DAYS": emp_leave_days,
        "INTERNET": internet_allowance, "ARREAR": salary_arrear_allowance,
        "ADVANCE": salary_advance, "TDS": tds,
        "IS_ESI": Decimal("1") if is_esi_eligible else Decimal("0"),
        "IS_PF": Decimal("1") if is_pf_applicable else Decimal("0"),
    }

    components = list(structure.components.filter(is_active=True))
    codes = {c.code for c in components}
    edges = {c.code: component_dependencies(c.as_expression(), codes) for c in components}
    order = order_components(edges)  # raises FormulaError on a cycle
    by_code = {c.code: c for c in components}

    Kind = SalaryComponent.Kind
    line_items: list[tuple[ResolvedComponent, bool]] = []  # (component, include_in_gross)
    for code in order:
        comp = by_code[code]
        expr = comp.as_expression()
        raw = evaluate(expr, context)
        amount = _apply_rounding(raw, comp.rounding, comp.decimals)
        context[code] = amount
        line_items.append((ResolvedComponent(
            code=code, name=comp.name, kind=comp.kind, amount=amount,
            sequence=comp.sequence, source_expr=expr), comp.include_in_gross))

    # Per-run manual inputs are entered on the grid, not driven by the
    # structure's formulas (and their codes would collide with the context
    # variable names). Inject them as breakdown lines so gross/deductions and
    # the audit log stay complete, while keeping them out of the formula graph.
    for code, name, kind, value, in_gross, seq in (
        ("INTERNET_ALLOWANCE", "Internet Allowance", Kind.EARNING, internet_allowance, True, 900),
        ("SALARY_ARREAR", "Salary Arrear / Allowance", Kind.EARNING, salary_arrear_allowance, True, 910),
        ("SALARY_ADVANCE", "Salary Advance", Kind.DEDUCTION, salary_advance, False, 920),
        ("TDS", "TDS", Kind.DEDUCTION, tds, False, 930),
    ):
        if value:
            line_items.append((ResolvedComponent(
                code=code, name=name, kind=kind,
                amount=value.quantize(TWO_DP, rounding=ROUND_HALF_UP),
                sequence=seq, source_expr="manual input"), in_gross))

    gross = sum((r.amount for r, in_gross in line_items
                 if r.kind == Kind.EARNING and in_gross),
                Decimal("0")).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    emp_ded = sum((r.amount for r, _ in line_items if r.kind == Kind.DEDUCTION),
                  Decimal("0")).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    employer = sum((r.amount for r, _ in line_items if r.kind == Kind.EMPLOYER_CONTRIB),
                   Decimal("0")).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    net = (gross - emp_ded).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    ctc = (gross + employer).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    ordered = sorted((r for r, _ in line_items), key=lambda r: (r.sequence, r.code))
    return StructureComputation(
        present_days=present_days, pay_days=pay_days, components=ordered,
        gross_salary=gross, total_deductions=emp_ded, net_payable=net,
        employer_contributions=employer, ctc=ctc)


def apply_structure_computation(entry, computation: StructureComputation) -> None:
    """Copy a StructureComputation onto a PayslipEntry in place: legacy
    columns from the standard codes, then the derived totals. Caller saves.
    (Component-amount rows need entry.pk, so persist those separately with
    save_component_amounts once the entry exists.)"""
    entry.present_days = computation.present_days
    entry.pay_days = computation.pay_days
    # Zero the mapped columns first so a structure missing a standard
    # component doesn't leave a stale value behind.
    for field in LEGACY_COLUMN.values():
        setattr(entry, field, Decimal("0"))
    for comp in computation.components:
        field = LEGACY_COLUMN.get(comp.code)
        if field:
            setattr(entry, field, comp.amount)
    entry.gross_salary = computation.gross_salary
    entry.total_deductions = computation.total_deductions
    entry.net_payable = computation.net_payable
    entry.employer_contributions = computation.employer_contributions
    entry.ctc = computation.ctc


def save_component_amounts(entry, computation: StructureComputation) -> None:
    """Persist the per-entry breakdown / audit log. Replaces any existing
    rows for the entry (a recompute supersedes them)."""
    from ..models import PayslipComponentAmount
    entry.component_amounts.all().delete()
    PayslipComponentAmount.objects.bulk_create([
        PayslipComponentAmount(
            entry=entry, code=c.code, name=c.name, kind=c.kind,
            amount=c.amount, sequence=c.sequence, source_expr=c.source_expr)
        for c in computation.components
    ])
