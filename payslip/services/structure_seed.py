"""Seed an organization's default SalaryStructure from its PayrollSettings.

The default structure's components reproduce the legacy hardcoded engine
(services.payroll_calc.compute_entry) exactly, so a brand-new structure
behaves identically to today until an admin edits a formula. The engine-
equivalence test is what guarantees the translation is exact.
"""
from __future__ import annotations

import datetime

from ..models import (PayrollSettings, SalaryComponent, SalaryStructure,
                      payroll_settings_for)


def _fmt(value) -> str:
    """A Decimal as a plain formula literal (strip trailing zeros/point)."""
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def default_component_specs(s: PayrollSettings) -> list[dict]:
    """The component rows that reproduce PayrollSettings `s`. Formulas are
    explicit (they reference component codes and context vars) and each
    component's own rounding/decimals do the rounding - matching the legacy
    engine's per-component rounding (whole-rupee basic/ESI, 2dp the rest)."""
    C = SalaryComponent
    basic_pct = s.basic_percent_of_package / 100
    esi_base = "(BASIC + DA + HRA + TRANSPORT + FOOD)"
    pf_capped = f"MIN((BASIC + DA) * {_fmt(s.pf_wage_factor / 100)}, {_fmt(s.pf_wage_cap)})"

    specs = [
        # --- earnings (into gross) ---
        dict(code="BASIC", name="Basic", kind=C.Kind.EARNING, seq=10,
             formula=f"PACKAGE * {_fmt(basic_pct)} / TWD * PAY_DAYS",
             rounding=C.Rounding.HALF_UP, decimals=0,
             is_esi_base=True, is_pf_base=True),
        dict(code="DA", name="Dearness Allowance", kind=C.Kind.EARNING, seq=20,
             formula=f"BASIC * {_fmt(s.da_percent_of_basic / 100)}",
             rounding=C.Rounding.HALF_UP, decimals=2,
             is_esi_base=True, is_pf_base=True),
        dict(code="HRA", name="House Rent Allowance", kind=C.Kind.EARNING, seq=30,
             formula=f"BASIC * {_fmt(s.hra_percent_of_basic / 100)}",
             rounding=C.Rounding.HALF_UP, decimals=2, is_esi_base=True),
        dict(code="TRANSPORT", name="Transport Allowance", kind=C.Kind.EARNING, seq=40,
             formula=f"BASIC * {_fmt(s.transport_percent_of_basic / 100)}",
             rounding=C.Rounding.HALF_UP, decimals=2, is_esi_base=True),
        dict(code="FOOD", name="Food Allowance", kind=C.Kind.EARNING, seq=50,
             formula=f"BASIC * {_fmt(s.food_percent_of_basic / 100)}",
             rounding=C.Rounding.HALF_UP, decimals=2, is_esi_base=True),
        # --- employee deductions ---
        dict(code="ESI_EMP", name="ESI (Employee)", kind=C.Kind.DEDUCTION, seq=80,
             formula=f"IF(IS_ESI, {esi_base} * {_fmt(s.esi_employee_percent / 100)}, 0)",
             rounding=C.Rounding.CEILING, decimals=0,
             include_in_gross=False, statutory_type=C.Statutory.ESI),
        dict(code="PF_EMP", name="PF (Employee)", kind=C.Kind.DEDUCTION, seq=90,
             formula=f"IF(IS_PF, {pf_capped} * {_fmt(s.pf_employee_percent / 100)}, 0)",
             rounding=C.Rounding.HALF_UP, decimals=2,
             include_in_gross=False, statutory_type=C.Statutory.PF),
        # --- employer contributions ---
        dict(code="ESI_ER", name="ESI (Employer)", kind=C.Kind.EMPLOYER_CONTRIB, seq=120,
             formula=f"IF(IS_ESI, {esi_base} * {_fmt(s.esi_employer_percent / 100)}, 0)",
             rounding=C.Rounding.CEILING, decimals=0,
             include_in_gross=False, statutory_type=C.Statutory.ESI),
    ]
    # PF employer: matched to employee, or computed independently.
    if s.pf_employer_matches_employee:
        pf_er_formula = "PF_EMP"
    else:
        pf_er_formula = f"IF(IS_PF, {pf_capped} * {_fmt(s.pf_employer_percent / 100)}, 0)"
    specs.append(dict(code="PF_ER", name="PF (Employer)", kind=C.Kind.EMPLOYER_CONTRIB,
                      seq=130, formula=pf_er_formula, rounding=C.Rounding.HALF_UP,
                      decimals=2, include_in_gross=False, statutory_type=C.Statutory.PF))
    return specs


def build_components(structure: SalaryStructure, specs: list[dict]) -> None:
    """(Re)create the component rows for a structure from specs."""
    C = SalaryComponent
    structure.components.all().delete()
    C.objects.bulk_create([
        C(structure=structure, code=spec["code"], name=spec["name"],
          kind=spec["kind"], calc_method=C.Method.FORMULA, formula=spec["formula"],
          rounding=spec["rounding"], decimals=spec["decimals"],
          include_in_gross=spec.get("include_in_gross", True),
          is_esi_base=spec.get("is_esi_base", False),
          is_pf_base=spec.get("is_pf_base", False),
          statutory_type=spec.get("statutory_type", C.Statutory.NONE),
          sequence=spec["seq"])
        for spec in specs
    ])


def seed_default_structure(org, *, created_by=None) -> SalaryStructure:
    """Get-or-create the org's default structure (effective from the epoch so
    it covers every historical period), populated from PayrollSettings."""
    settings_obj = payroll_settings_for(org)
    structure = (SalaryStructure.objects
                 .filter(organization=org, effective_from=datetime.date(2000, 1, 1))
                 .first())
    if structure is None:
        structure = SalaryStructure.objects.create(
            organization=org, label="Default structure",
            effective_from=datetime.date(2000, 1, 1), created_by=created_by)
        build_components(structure, default_component_specs(settings_obj))
    return structure
