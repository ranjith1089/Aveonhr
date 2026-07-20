"""Payslip PDF generation for the Payroll module - reuses the existing,
already-tested ReportLab layout in payslip/utils.py (build_payslip_pdf)
rather than duplicating it. That builder expects a pandas Series keyed by
its column-alias vocabulary; entry_to_series() is the adapter.
"""
from __future__ import annotations


def entry_to_series(entry):
    """Adapt a PayslipEntry + its Employee into the exact keys
    utils.build_payslip_pdf() reads via row.get(...)."""
    import pandas as pd

    emp = entry.employee
    return pd.Series({
        "employee_name": emp.name,
        "employee_id": emp.employee_code,
        "designation": emp.designation,
        "joining_date": emp.doj,
        "bank_name": emp.bank_name,
        "account_number": emp.bank_account_number,
        "pan_number": emp.pan_number,
        "pf_no": emp.pf_number,
        "pf_uan": emp.pf_uan,
        "month": entry.run.period,
        "total_working_days": entry.total_working_days,
        "present_days": entry.present_days,
        "pay_days": entry.pay_days,
        "lop_days": entry.lop_days,
        "basic": entry.basic,
        "da": entry.da,
        "hra": entry.hra,
        "transport_allowances": entry.transport_allowance,
        "food_allowances": entry.food_allowance,
        "internet_allowances": entry.internet_allowance,
        "salary_arrear_allowance": entry.salary_arrear_allowance,
        "gross_salary": entry.gross_salary,
        "pf_employee": entry.pf_employee,
        "esi_employee": entry.esi_employee,
        "salary_advance": entry.salary_advance,
        "tds": entry.tds,
        "total_deductions": entry.total_deductions,
        "net_payable": entry.net_payable,
    })


def build_entry_pdf(entry, company, logo_bytes) -> bytes:
    from ..utils import build_payslip_pdf
    return build_payslip_pdf(entry_to_series(entry), company, logo_bytes)
