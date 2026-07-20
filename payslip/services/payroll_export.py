"""Export a payroll run's register as an .xlsx, matching the source
sheet's original column layout."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

HEADERS = [
    "S.No", "Name", "Designation", "Total Working Days", "CL Credit",
    "Emp Leave Days", "LOP Days", "Present Days", "Pay Days", "Basic", "DA",
    "HRA", "Transport Allowance", "Food Allowance", "Internet Allowance",
    "Salary Arrear / Allowance", "Gross Salary", "ESI Employee", "ESI Employer",
    "PF Employee", "PF Employer", "Salary Advance", "TDS", "Total Deductions",
    "Net Payable", "Remarks",
]
MONEY_COLS = set(range(10, 26))  # Basic..Net Payable (1-based columns)
HEADER_ROW = 3                   # row 1 = title, row 2 = spacer


def build_payroll_register_workbook(org, period) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    from ..models import PayslipEntry

    entries = (
        PayslipEntry.objects.filter(organization=org, run__period=period)
        .select_related("employee")
        .order_by("employee__name")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Payroll Register"

    # Title banner across the full table width, matching the printed
    # salary statement's heading.
    last_col = get_column_letter(len(HEADERS))
    ws["A1"] = f"Salary Statement For The Month Of {period:%B %Y}"
    ws.merge_cells(f"A1:{last_col}1")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    ws.append([])                    # row 2 - spacer
    ws.append(HEADERS)               # row 3 - column headers
    for cell in ws[HEADER_ROW]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
    ws.freeze_panes = f"A{HEADER_ROW + 1}"

    totals = {"gross": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0")}
    for serial, e in enumerate(entries, start=1):
        totals["gross"] += e.gross_salary
        totals["deductions"] += e.total_deductions
        totals["net"] += e.net_payable
        ws.append([
            serial, e.employee.name, e.employee.designation, e.total_working_days,
            e.cl_credit, e.emp_leave_days, e.lop_days, e.present_days, e.pay_days,
            e.basic, e.da, e.hra, e.transport_allowance, e.food_allowance,
            e.internet_allowance, e.salary_arrear_allowance, e.gross_salary,
            e.esi_employee, e.esi_employer, e.pf_employee, e.pf_employer,
            e.salary_advance, e.tds, e.total_deductions, e.net_payable, e.remarks,
        ])

    for row in ws.iter_rows(min_row=HEADER_ROW + 1):
        for cell in row:
            if cell.column in MONEY_COLS and cell.value is not None:
                cell.number_format = "#,##0.00"

    ws.append([])
    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
               "TOTAL:", totals["gross"], "", "", "", "", "", "",
               totals["deductions"], totals["net"]])
    for col in (17, 24, 25):
        ws.cell(row=ws.max_row, column=col).number_format = "#,##0.00"
        ws.cell(row=ws.max_row, column=col).font = Font(bold=True)
    ws.cell(row=ws.max_row, column=16).font = Font(bold=True)

    widths = [6, 24, 18, 10, 9, 11, 9, 10, 9, 11, 10, 10, 12, 11, 11, 14, 13,
             12, 12, 11, 11, 12, 10, 13, 13, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
