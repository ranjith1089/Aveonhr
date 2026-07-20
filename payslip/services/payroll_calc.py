"""Payroll calculation engine - pure, DB-independent, Decimal-only.

Reproduces the source Salary Excel's formulas exactly, parameterized by a
PayrollSettings instance (org-configurable) instead of hardcoded rates:

    Basic  = ROUND(((package * basic%) / total_working_days) * pay_days, 0)
    DA/HRA/Transport/Food = Basic * their % (2dp, no whole-rupee rounding)
    Gross  = Basic + DA + HRA + Transport + Food + Internet + Arrear
    ESI Employee/Employer = ROUNDUP(base * their %, 0), base = Basic+DA+HRA+Transport+Food
        - only applied when the employee is ESI-eligible; eligibility is a
          sticky per-employee flag, not derived from this month's gross
          (confirmed against the source sheet: gross can temporarily exceed
          the wage ceiling due to a one-off arrear without losing coverage)
    PF Employee = min((Basic+DA)*wage_factor%, wage_cap) * pf_employee%
    PF Employer = matched to PF Employee, or computed independently
        - only applied when the employee is PF-applicable; like ESI, this is
          a sticky per-employee flag, not a universal rule (confirmed
          against the source sheet: only about half the roster is ever
          PF-enrolled - the rest carry a literal 0, never a formula)
    Total Deductions = ESI Employee + PF Employee + Advance + TDS
    Net Payable = Gross - Total Deductions

Excel's ROUND() is banker's-rounding-free "round half away from zero", i.e.
Python's ROUND_HALF_UP; ROUNDUP() always rounds away from zero, i.e.
ROUND_CEILING for these non-negative amounts.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

WHOLE_RUPEE = Decimal("1")
TWO_DP = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass
class EntryComputation:
    present_days: Decimal
    pay_days: Decimal
    basic: Decimal
    da: Decimal
    hra: Decimal
    transport_allowance: Decimal
    food_allowance: Decimal
    gross_salary: Decimal
    esi_employee: Decimal
    esi_employer: Decimal
    pf_employee: Decimal
    pf_employer: Decimal
    total_deductions: Decimal
    net_payable: Decimal


def compute_entry(
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
    settings,
) -> EntryComputation:
    """`settings` is any object exposing the PayrollSettings fields (a
    saved instance, an unsaved one, or a stand-in) - kept duck-typed so the
    historical importer can pass a throwaway default instance without a DB
    round trip."""
    twd = Decimal(total_working_days)
    present_days = twd - emp_leave_days
    pay_days = twd - lop_days

    basic_pct = settings.basic_percent_of_package / HUNDRED
    per_day = (monthly_package * basic_pct) / twd if twd else Decimal("0")
    basic = (per_day * pay_days).quantize(WHOLE_RUPEE, rounding=ROUND_HALF_UP)

    da = (basic * settings.da_percent_of_basic / HUNDRED).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    hra = (basic * settings.hra_percent_of_basic / HUNDRED).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    transport = (basic * settings.transport_percent_of_basic / HUNDRED).quantize(
        TWO_DP, rounding=ROUND_HALF_UP)
    food = (basic * settings.food_percent_of_basic / HUNDRED).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    gross = (basic + da + hra + transport + food + internet_allowance
             + salary_arrear_allowance).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    esi_base = basic + da + hra + transport + food
    if is_esi_eligible:
        esi_employee = (esi_base * settings.esi_employee_percent / HUNDRED).quantize(
            WHOLE_RUPEE, rounding=ROUND_CEILING)
        esi_employer = (esi_base * settings.esi_employer_percent / HUNDRED).quantize(
            WHOLE_RUPEE, rounding=ROUND_CEILING)
    else:
        esi_employee = esi_employer = Decimal("0")

    if is_pf_applicable:
        pf_wage_base = (basic + da) * settings.pf_wage_factor / HUNDRED
        capped_base = min(pf_wage_base, settings.pf_wage_cap)
        pf_employee = (capped_base * settings.pf_employee_percent / HUNDRED).quantize(
            TWO_DP, rounding=ROUND_HALF_UP)
        if settings.pf_employer_matches_employee:
            pf_employer = pf_employee
        else:
            pf_employer = (capped_base * settings.pf_employer_percent / HUNDRED).quantize(
                TWO_DP, rounding=ROUND_HALF_UP)
    else:
        pf_employee = pf_employer = Decimal("0")

    total_deductions = (esi_employee + pf_employee + salary_advance + tds).quantize(
        TWO_DP, rounding=ROUND_HALF_UP)
    net_payable = (gross - total_deductions).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    return EntryComputation(
        present_days=present_days, pay_days=pay_days,
        basic=basic, da=da, hra=hra, transport_allowance=transport, food_allowance=food,
        gross_salary=gross, esi_employee=esi_employee, esi_employer=esi_employer,
        pf_employee=pf_employee, pf_employer=pf_employer,
        total_deductions=total_deductions, net_payable=net_payable,
    )


def apply_computation(entry, computation: EntryComputation) -> None:
    """Copy an EntryComputation's fields onto a PayslipEntry instance
    in-place (caller is responsible for saving/bulk_update)."""
    entry.present_days = computation.present_days
    entry.pay_days = computation.pay_days
    entry.basic = computation.basic
    entry.da = computation.da
    entry.hra = computation.hra
    entry.transport_allowance = computation.transport_allowance
    entry.food_allowance = computation.food_allowance
    entry.gross_salary = computation.gross_salary
    entry.esi_employee = computation.esi_employee
    entry.esi_employer = computation.esi_employer
    entry.pf_employee = computation.pf_employee
    entry.pf_employer = computation.pf_employer
    entry.total_deductions = computation.total_deductions
    entry.net_payable = computation.net_payable
