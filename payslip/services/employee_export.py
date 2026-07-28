"""Export employee master data as .xlsx with user-selected columns."""
from __future__ import annotations

from io import BytesIO
from typing import Sequence

from ..models import Employee

EXPORTABLE_COLUMNS = [
    ("employee_code", "Employee Code"),
    ("name", "Name"),
    ("designation", "Designation"),
    ("department", "Department"),
    ("doj", "Date of Joining"),
    ("relieving_date", "Relieving Date"),
    ("is_active", "Active Status"),
    ("employment_status", "Employment Status"),
    ("date_of_birth", "Date of Birth"),
    ("blood_group", "Blood Group"),
    ("marital_status", "Marital Status"),
    ("parent_spouse_name", "Parent / Spouse Name"),
    ("aadhar_no", "Aadhar No"),
    ("address", "Address"),
    ("personal_email", "Personal Email"),
    ("official_email", "Official Email"),
    ("contact_no", "Contact No"),
    ("official_no", "Official No"),
    ("emergency_no", "Emergency No"),
    ("agreement_signed", "Agreement Signed"),
    ("agreement_sign_date", "Agreement Sign Date"),
    ("biometric_id", "Biometric ID"),
    ("current_monthly_package", "Monthly Package (₹)"),
    ("bank_name", "Bank Name"),
    ("bank_account_number", "Bank Account No"),
    ("ifsc_code", "IFSC Code"),
    ("pan_number", "PAN Number"),
    ("pf_number", "PF Number"),
    ("pf_uan", "PF UAN"),
    ("esi_number", "ESI Number"),
    ("is_esi_eligible", "ESI Eligible"),
    ("is_pf_applicable", "PF Applicable"),
    ("reason_for_leaving", "Reason for Leaving"),
    ("notes", "Notes"),
]

COLUMN_KEYS = {k for k, _ in EXPORTABLE_COLUMNS}


def _format_value(val):
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return val


def build_employee_workbook(org, selected_columns: Sequence[str]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    columns = [(k, label) for k, label in EXPORTABLE_COLUMNS
                if k in selected_columns]
    if not columns:
        columns = EXPORTABLE_COLUMNS[:5]

    employees = Employee.objects.filter(organization=org).order_by("name")

    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append([label for _, label in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    for emp in employees:
        row = []
        for key, _ in columns:
            val = getattr(emp, key, "")
            if key == "employment_status" and val:
                val = emp.get_employment_status_display()
            row.append(_format_value(val))
        ws.append(row)

    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 40)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
