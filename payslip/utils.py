from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from datetime import date, datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib.units import mm
from PIL import Image as PilImage
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class CompanyInfo:
    name: str
    address: str
    email: str | None = None
    phone: str | None = None


REQUIRED_COLUMNS = {"employee_name", "employee_id", "month"}

COLUMN_ALIASES = {
    "employee_id": {
        "employee_id",
        "emp_id",
        "employeeid",
        "emp code",
        "employee code",
        "employee no",
        "employee number",
        "emp no",
    },
    "employee_name": {"employee_name", "employee name", "emp_name", "emp name"},
    "department": {"department", "dept"},
    "designation": {"designation", "role"},
    "gender": {"gender"},
    "joining_date": {"joining_date", "date_of_joining", "doj", "joining date"},
    "bank_name": {"bank_name", "bank"},
    "account_number": {
        "account_number",
        "account_no",
        "a/c",
        "a/c #",
        "ac no",
        "ac_no",
        "bank account no",
        "bank account number",
    },
    "ifsc_code": {"ifsc_code", "ifsc"},
    "pan_number": {"pan_number", "pan", "pan no", "pan number"},
    "pf_no": {"pf_no", "pf number", "pf no"},
    "pf_uan": {"pf_uan", "uan", "pf uan"},
    "location": {"location"},
    "effective_work_days": {"effective work days", "effective_work_days"},
    "month": {"month", "pay_month", "payslip_month", "payslip for the month of"},
    "total_working_days": {"total_working_days", "total working days"},
    "present_days": {"present_days", "present days"},
    "lop_days": {"lop_days", "lop days", "lwp", "loss of pay", "lop"},
    "pay_days": {"pay_days", "pay days", "paid_days", "pay days(26)"},
    "days_in_month": {"days_in_month", "days in month"},
    "basic": {"basic"},
    "da": {"da", "dearness allowance"},
    "hra": {"hra", "house rent allowance"},
    "transport_allowances": {"transport_allowances", "transport allowance", "ta"},
    "food_allowances": {"food_allowances", "food allowance"},
    "internet_allowances": {"internet_allowances", "internet allowance"},
    "other_allowances": {"other_allowances", "other allowance"},
    "salary_arrear_allowance": {
        "salary_arrear_allowance",
        "salary arrier / allowance",
        "salary arrear allowance",
    },
    "gross_salary": {"gross_salary", "gross salary"},
    "pf_employee": {"pf_employee", "pf employee", "provident fund"},
    "pf_employer": {"pf_employer", "pf employer"},
    "esi_employee": {"esi_employee", "esi employee"},
    "esi_employer": {"esi_employer", "esi employer"},
    "professional_tax": {"professional_tax", "professional tax"},
    "salary_advance": {"salary_advance", "salary advance"},
    "tds": {"tds"},
    "other_deduction": {"other_deduction", "other deduction"},
    "total_deductions": {"total_deductions", "total deductions"},
    "net_payable": {"net_payable", "net payable", "net pay"},
}

EARNING_COLUMNS = (
    "basic",
    "da",
    "hra",
    "transport_allowances",
    "food_allowances",
    "internet_allowances",
    "other_allowances",
    "salary_arrear_allowance",
)
DEDUCTION_COLUMNS = (
    "pf_employee",
    "esi_employee",
    "professional_tax",
    "salary_advance",
    "tds",
    "other_deduction",
)


def _normalize_name(name: str) -> str:
    cleaned = name.strip().lower().replace("/", " ").replace("#", " ")
    cleaned = re.sub(r"[\(\)]", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return cleaned.strip("_")


def _build_alias_map() -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        alias_map[_normalize_name(canonical)] = canonical
        for alias in aliases:
            alias_map[_normalize_name(alias)] = canonical
    return alias_map


ALIAS_MAP = _build_alias_map()


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    normalized = []
    for col in frame.columns:
        key = _normalize_name(str(col))
        normalized.append(ALIAS_MAP.get(key, key))
    frame.columns = normalized
    return frame


def validate_columns(frame: pd.DataFrame) -> list[str]:
    missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    return missing


def parse_salary_file(file_bytes: bytes) -> pd.DataFrame:
    data = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    data = normalize_columns(data)
    return data


def safe_number(value: object) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        if isinstance(value, str) and value.strip() in {"", "-"}:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def display_value(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if isinstance(value, str) and value.strip() == "":
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (pd.Timestamp, datetime, date)):
        if pd.isnull(value):
            return "-"
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str) and "00:00:00" in value:
        return value.split(" ")[0]
    return str(value)


def format_money(value: object) -> str:
    return f"{safe_number(value):,.2f}"


def format_month(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if isinstance(value, str) and value.strip() == "":
        return "-"
    try:
        parsed = pd.to_datetime(value)
        if pd.isnull(parsed):
            return "-"
        return parsed.strftime("%b %Y").upper()
    except Exception:
        return display_value(value)


_ONES = (
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = (
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
)


def _convert_hundreds(number: int) -> str:
    words: list[str] = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        words.append(f"{_ONES[hundreds]} Hundred")
    if remainder:
        if remainder < 20:
            words.append(_ONES[remainder])
        else:
            tens, ones = divmod(remainder, 10)
            words.append(_TENS[tens] if ones == 0 else f"{_TENS[tens]} {_ONES[ones]}")
    return " ".join(words)


def number_to_words(value: object) -> str:
    amount = int(round(safe_number(value)))
    if amount == 0:
        return "Zero"

    parts: list[str] = []
    crores, amount = divmod(amount, 10_000_000)
    lakhs, amount = divmod(amount, 100_000)
    thousands, amount = divmod(amount, 1_000)
    hundreds = amount

    if crores:
        parts.append(f"{_convert_hundreds(crores)} Crore")
    if lakhs:
        parts.append(f"{_convert_hundreds(lakhs)} Lakh")
    if thousands:
        parts.append(f"{_convert_hundreds(thousands)} Thousand")
    if hundreds:
        parts.append(_convert_hundreds(hundreds))

    return " ".join(parts)


def pick_value(row: pd.Series, *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def build_payslip_pdf(row: pd.Series, company: CompanyInfo, logo_bytes: bytes | None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story: list = []

    BRAND_COLOR = colors.HexColor("#1e3a5f")
    BRAND_LIGHT = colors.HexColor("#e8f0fe")

    logo = None
    logo_buffer = None  # keep reference alive for PDF rendering
    if logo_bytes:
        try:
            max_w_pt = 26 * mm
            max_h_pt = 18 * mm
            pil_img = PilImage.open(BytesIO(logo_bytes))
            pil_img.load()
            pil_img = pil_img.convert("RGBA")
            pil_img.thumbnail((int(max_w_pt * 3), int(max_h_pt * 3)), PilImage.LANCZOS)
            display_w = pil_img.width / 3
            display_h = pil_img.height / 3
            logo_buffer = BytesIO()
            pil_img.save(logo_buffer, format="PNG")
            logo_buffer.seek(0)
            logo = Image(logo_buffer, width=display_w, height=display_h)
            logo.hAlign = "CENTER"
        except Exception:
            logo = None

    month_label = format_month(row.get("month"))
    center_title = ParagraphStyle("CenterTitle", parent=styles["Title"], alignment=TA_CENTER)
    center_normal = ParagraphStyle("CenterNormal", parent=styles["Normal"], alignment=TA_CENTER)
    month_style = ParagraphStyle(
        "MonthStyle", parent=styles["Heading3"],
        alignment=TA_CENTER, textColor=BRAND_COLOR,
    )
    company_lines = [
        Paragraph(f"<b>{company.name}</b>", center_title),
        Paragraph(company.address.replace("\n", "<br />"), center_normal),
    ]
    contact_parts = [part for part in [company.email, company.phone] if part]
    if contact_parts:
        company_lines.append(Paragraph(" | ".join(contact_parts), center_normal))

    # Brand accent bar (full width, thin colored stripe)
    accent_bar = Table([[""]],
        colWidths=[170 * mm], rowHeights=[3 * mm])
    accent_bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_COLOR),
        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
    ]))
    story.append(accent_bar)

    header_table = Table(
        [
            [company_lines, logo or ""],
            [Paragraph(f"Payslip for the month of {month_label}", month_style), ""],
        ],
        colWidths=[140 * mm, 30 * mm],
        rowHeights=[24 * mm, None],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (1, 1)),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
                ("BACKGROUND", (0, 1), (-1, 1), BRAND_LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("LINEABOVE", (0, 1), (-1, 1), 1, BRAND_COLOR),
                ("ALIGN", (0, 1), (1, 1), "CENTER"),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 6))

    effective_work_days = pick_value(
        row, "effective_work_days", "present_days", "pay_days", "total_working_days"
    )

    def _value_cell(value: object) -> Paragraph:
        return Paragraph(display_value(value), styles["Normal"])

    info_rows = [
        [
            "Name",
            _value_cell(row.get("employee_name")),
            "Employee No",
            _value_cell(row.get("employee_id")),
        ],
        [
            "Joining Date",
            _value_cell(row.get("joining_date")),
            "Bank Name",
            _value_cell(row.get("bank_name")),
        ],
        [
            "Designation",
            _value_cell(row.get("designation")),
            "Bank Account No",
            _value_cell(row.get("account_number")),
        ],
        [
            "Department",
            _value_cell(row.get("department")),
            "PAN Number",
            _value_cell(row.get("pan_number")),
        ],
        [
            "Location",
            _value_cell(row.get("location")),
            "PF No",
            _value_cell(row.get("pf_no")),
        ],
        [
            "Effective Work Days",
            _value_cell(effective_work_days),
            "PF UAN",
            _value_cell(row.get("pf_uan")),
        ],
        ["LOP", _value_cell(row.get("lop_days")), "", ""],
    ]

    info_table = Table(info_rows, colWidths=[35 * mm, 50 * mm, 35 * mm, 50 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 8))

    earnings_total = sum(safe_number(row.get(col)) for col in EARNING_COLUMNS)
    deductions_total = sum(safe_number(row.get(col)) for col in DEDUCTION_COLUMNS)

    gross_salary = safe_number(row.get("gross_salary")) or earnings_total
    total_deductions = safe_number(row.get("total_deductions")) or deductions_total
    net_total = safe_number(row.get("net_payable")) or (gross_salary - total_deductions)

    earnings_rows: list[list[str]] = []
    for col in EARNING_COLUMNS:
        if col in row.index:
            label = col.replace("_", " ").title()
            master_value = row.get(f"{col}_master")
            master_display = format_money(master_value) if safe_number(master_value) else "-"
            earnings_rows.append([label, master_display, format_money(row.get(col))])

    deductions_rows: list[list[str]] = []
    for col in DEDUCTION_COLUMNS:
        if col in row.index:
            label = col.replace("_", " ").title()
            deductions_rows.append([label, format_money(row.get(col))])

    max_rows = max(len(earnings_rows), len(deductions_rows), 1)
    while len(earnings_rows) < max_rows:
        earnings_rows.append(["", "", ""])
    while len(deductions_rows) < max_rows:
        deductions_rows.append(["", ""])

    combined_rows = [["Earnings", "Master", "Actual", "Deductions", "Actual"]]
    for idx in range(max_rows):
        earn_label, earn_master, earn_actual = earnings_rows[idx]
        ded_label, ded_actual = deductions_rows[idx]
        combined_rows.append([earn_label, earn_master, earn_actual, ded_label, ded_actual])

    combined_rows.append(
        [
            "Total Earnings: INR.",
            "",
            format_money(gross_salary),
            "Total Deductions: INR.",
            format_money(total_deductions),
        ]
    )

    combined_table = Table(
        combined_rows,
        colWidths=[55 * mm, 20 * mm, 20 * mm, 55 * mm, 20 * mm],
    )
    combined_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ALIGN", (1, 1), (2, -1), "RIGHT"),
                ("ALIGN", (4, 1), (4, -1), "RIGHT"),
                ("SPAN", (0, -1), (1, -1)),
                ("SPAN", (3, -1), (3, -1)),
            ]
        )
    )
    story.append(combined_table)

    story.append(Spacer(1, 8))
    net_words = number_to_words(net_total)
    net_table = Table(
        [
            [f"Net Pay for the month ( Total Earnings - Total Deductions ):  {format_money(net_total)}"],
            [f"(Rupees {net_words} Only)"],
        ],
        colWidths=[170 * mm],
    )
    net_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    story.append(net_table)
    story.append(Spacer(1, 8))

    footer_label = ParagraphStyle(
        "FooterLabel", parent=styles["Normal"],
        fontSize=7, textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER,
    )
    footer_bar = Table(
        [["This is a computer generated payslip and does not require a signature."],
         [company.name]],
        colWidths=[170 * mm],
    )
    footer_bar.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 1, colors.HexColor("#1e3a5f")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b7280")),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#1e3a5f")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(footer_bar)

    doc.build(story)
    return buffer.getvalue()


def build_zip(file_pairs: Iterable[tuple[str, bytes]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zip_file:
        for filename, content in file_pairs:
            zip_file.writestr(filename, content)
    return buffer.getvalue()


def _add_months_clamped(d: "date", months: int) -> "date":
    """Add `months` to date `d`, clamping day-of-month so 31-Jan + 1 month
    becomes 28/29-Feb instead of overflowing. Pure stdlib — no dateutil."""
    from calendar import monthrange
    from datetime import date as _date

    total = d.month - 1 + months
    new_year = d.year + total // 12
    new_month = total % 12 + 1
    last_day = monthrange(new_year, new_month)[1]
    return _date(new_year, new_month, min(d.day, last_day))


def build_offer_letter_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    letter_style = ParagraphStyle(
        "letter_style",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
    )
    story: list = []

    offer_title = str(
        data.get("offer_type_label") or data.get("offer_type") or "Offer Letter"
    ).upper()
    name = str(data.get("name", "")).strip()
    roll_number = str(data.get("roll_number", "")).strip()
    course = str(data.get("course", "")).strip()
    college_name = str(data.get("college_name", "")).strip()
    college_address = str(data.get("college_address", "")).strip()
    role = str(data.get("internship_role", "")).strip()
    start_date = data.get("start_date")
    duration_months = data.get("duration_months")
    try:
        duration_months = int(duration_months) if duration_months not in (None, "") else None
    except (TypeError, ValueError):
        duration_months = None

    if start_date:
        start_date_label = start_date.strftime("%b. %d, %Y").replace(" 0", " ")
    else:
        start_date_label = "-"

    end_date = None
    end_date_label = "-"
    if start_date and duration_months and duration_months > 0:
        end_date = _add_months_clamped(start_date, duration_months)
        end_date_label = end_date.strftime("%b. %d, %Y").replace(" 0", " ")

    story.append(Paragraph(offer_title, styles["Title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(name, letter_style))
    story.append(Paragraph(f"Roll No- {roll_number}", letter_style))
    story.append(Paragraph(course, letter_style))
    story.append(Paragraph(college_name, letter_style))
    story.append(Paragraph(college_address.replace("\n", "<br />"), letter_style))
    story.append(Spacer(1, 12))

    # Internship Details mini-table — at-a-glance summary of the offer.
    # Rows with empty values are skipped so the table degrades gracefully.
    detail_rows = [
        ("Name", name),
        ("Role", role),
        ("Start Date", start_date_label if start_date else ""),
    ]
    if duration_months:
        month_word = "month" if duration_months == 1 else "months"
        detail_rows.append(("Duration", f"{duration_months} {month_word}"))
        if end_date:
            detail_rows.append(("End Date", end_date_label))
    detail_rows = [(lbl, val) for lbl, val in detail_rows if val]
    if detail_rows:
        details_table = Table(detail_rows, colWidths=[40 * mm, 120 * mm])
        details_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 14))

    story.append(Paragraph(f"Dear {name},", letter_style))
    if duration_months and end_date:
        month_word = "month" if duration_months == 1 else "months"
        body_sentence = (
            "We are pleased to offer you an internship at our company Aveon Infotech Private Limited "
            f"as an {role} for a period of {duration_months} {month_word}, starting on "
            f"{start_date_label} and ending on {end_date_label}."
        )
    else:
        body_sentence = (
            "We are pleased to offer you an internship at our company Aveon Infotech Private Limited "
            f"as an {role}. Your internship starts on {start_date_label}."
        )
    story.append(Paragraph(body_sentence, letter_style))
    story.append(
        Paragraph(
            "The terms and conditions of your Internship with the Company are set forth below:",
            letter_style,
        )
    )
    story.append(
        Paragraph(
            "Subject to your acceptance of the terms and conditions contained herein, your project "
            "and responsibilities during the Term will be determined by the supervisor assigned to "
            "you for the duration of the Internship.",
            letter_style,
        )
    )
    story.append(
        Paragraph(
            "The Internship cannot be construed as an employment offer with Aveon Infotech Private Limited.",
            letter_style,
        )
    )
    story.append(Spacer(1, 24))
    story.append(Paragraph("Sincerely,", letter_style))
    story.append(Paragraph("Ranjith Kumar", letter_style))
    story.append(Paragraph("General Manager", letter_style))

    doc.build(story)
    return buffer.getvalue()


def build_appointment_order_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    letter_style = ParagraphStyle(
        "letter_style",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
    )
    story: list = []

    # Header information
    today = date.today()
    date_str = today.strftime("%b. %d, %Y").replace(" 0", " ")
    serial_no = str(data.get("serial_no", "")).strip()
    employee_name = str(data.get("employee_name", "")).strip()
    addr1 = str(data.get("present_address1", "")).strip()
    addr2 = str(data.get("present_address2", "")).strip()
    addr3 = str(data.get("present_address3", "")).strip()
    city = str(data.get("present_address_city", "")).strip()
    state = str(data.get("present_address_state", "")).strip()
    pin_code = str(data.get("present_address_pin", "")).strip()
    designation = str(data.get("designation", "")).strip()
    join_date = data.get("join_date")
    if join_date:
        join_date_str = join_date.strftime("%b. %d, %Y").replace(" 0", " ")
    else:
        join_date_str = "-"
    probation_period = str(data.get("probation_period", "")).strip()
    ctc = str(data.get("ctc", "")).strip()
    company_name = str(data.get("company_name", "")).strip()
    signatory = str(data.get("signatory", "")).strip()
    signatory_designation = str(data.get("signatory_designation", "")).strip()

    # Date and Ref No
    story.append(Paragraph(f"Date: {date_str}", styles["Normal"]))
    story.append(Paragraph(f"Ref No: {serial_no}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Address
    story.append(Paragraph(employee_name, styles["Normal"]))
    if addr1:
        story.append(Paragraph(addr1, styles["Normal"]))
    if addr2:
        story.append(Paragraph(addr2, styles["Normal"]))
    if addr3:
        story.append(Paragraph(addr3, styles["Normal"]))
    if city or state or pin_code:
        city_state_pin = f"{city}, {state} {pin_code}".strip(", ")
        story.append(Paragraph(city_state_pin, styles["Normal"]))
    story.append(Spacer(1, 12))

    # Title
    story.append(Paragraph("Appointment Order", styles["Title"]))
    story.append(Spacer(1, 12))

    # Body
    story.append(Paragraph(f"Dear {employee_name},", letter_style))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        f"We are pleased to appoint you as {designation} with effect from {join_date_str}.",
        letter_style,
    ))
    story.append(Paragraph(
        "Your employment in our organization shall be governed by the following terms and conditions. "
        "The terms and conditions may be amended from time to time at the discretion of the Management.",
        letter_style,
    ))
    story.append(Spacer(1, 6))

    # Terms and conditions
    terms = [
        f"You shall be initially on probation for a period of {probation_period} days. After the probation period is completed, you will be absorbed as the confirmed employee based on your performance and review. However, the organization reserves the right to extend the probation if required.",
        "During your probation, your services can be terminated without stipulating any reason with one-month notice or gross salary in lieu of notice on either side.",
        "You will continue in probation unless you receive a confirmation in writing from the respective department.",
        "You shall perform all the duties as the position you hold with diligence and such other tasks that may be assigned to you depending on the nature of work.",
        "You are liable for transfer or delegation to any of our office locations at the discretion of the Management.",
        f"You shall be paid a total remuneration (CTC) of Indian Rupees {ctc} /-",
        "Apart from the above, you are also eligible for Paid Offs, Performance Incentives, Food Coupons, Medical Insurance, etc., as per the company set practices.",
        "You shall attain superannuation at the age of 58 years.",
        "Termination of your services by the management without notice would arise in the event of:<br/>a. You are being found medically unfit during a pre-medical test<br/>b. Any contravention of the rules mentioned in standing orders<br/>c. Any other proven misconduct as per standing orders",
        "You shall not disclose any confidential and proprietary information to anyone who is not authorized to obtain the same. You would be required to sign a Non-Disclosure Agreement (NDA) in this regard at the time of your joining the organization.",
        "The organization reserves its right to amend the grade, designation, and salary structure offered to you from time to time.",
        "You shall comply with the rules and regulations of the organization as stipulated in the standing orders, employee handbook, or in any other manners that are currently in force or amended in future from time to time.",
        "The appointment is offered on the understanding that the information given by you is correct/true and complete. If found incorrect, this appointment may be withdrawn before you join service with us, or your services may be terminated at any time after you have taken up employment with us.",
        "If you are absent for a period of 5 consecutive working days without the sanction of leave or overstay, you shall lose your lien on your employment. You shall be assumed to have abandoned employment voluntarily.",
        "You shall take excellent care of and be responsible for the work equipment, official documents, tools, and other items/materials entrusted to you.",
        "This offer is provided in duplicate. Please return the duplicate copy duly signed by you as a token that indicates you have read, understood, and accepted the terms & conditions of this appointment offer.",
    ]
    
    for i, term in enumerate(terms, 1):
        story.append(Paragraph(f"{i}. {term}", letter_style))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"{company_name} welcomes you and offers delightful employment to work and hope that the association will be mutually beneficial and meaningful.",
        letter_style,
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("With best wishes,", letter_style))
    story.append(Paragraph(f"For {company_name},", letter_style))
    story.append(Spacer(1, 24))
    story.append(Paragraph(signatory, letter_style))
    story.append(Paragraph(signatory_designation, letter_style))
    story.append(Spacer(1, 24))

    story.append(Paragraph(
        "I hereby accept the terms and conditions of the employment mentioned in this order.",
        letter_style,
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Name of Employee:", styles["Normal"]))
    story.append(Paragraph("Signature:", styles["Normal"]))
    story.append(Paragraph("Date:", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


def build_employment_offer_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    letter_style = ParagraphStyle(
        "letter_style",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
    )
    story: list = []

    # Extract data
    candidate_name = str(data.get("candidate_name", "")).strip()
    position = str(data.get("position", "")).strip()
    annual_ctc = data.get("annual_ctc", 0)
    ctc_in_words = str(data.get("ctc_in_words", "")).strip()
    joining_date = data.get("joining_date")
    if joining_date:
        joining_date_str = joining_date.strftime("%dth of %b %Y").replace(" 0", " ")
    else:
        joining_date_str = "-"
    employer_name = str(data.get("employer_name", "")).strip()
    employer_designation = str(data.get("employer_designation", "")).strip()

    # Title
    story.append(Paragraph("OFFER LETTER", styles["Title"]))
    story.append(Spacer(1, 12))

    # Body
    story.append(Paragraph(f"Dear {candidate_name},", letter_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"We are pleased to extend this offer of employment for the position of {position} at "
        "iResponsive Offshore Development Center Private Limited. Our company is committed to providing "
        "the best possible work environment for our employees, and we believe that you have the skills, "
        "experience, and dedication needed to be a valuable member of our team.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph("You are offered employment on the following terms:", letter_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"The total base pay (i.e., annual fixed compensation) all-inclusive at your position will be "
        f"Rs. {annual_ctc:,.2f}/- ({ctc_in_words}). The Annual fixed compensation and Annual variable pay "
        "will be subject to deduction of tax at source, in accordance with Income Tax Act, 1961 and all "
        "other central and state legislation applicable to your base location.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "You shall not, during the period of your employment with the Company or at any time thereafter, "
        "use, divulge or disclose, either directly or indirectly to any person, firm or body corporate any "
        "knowledge, information or documents which you may acquire, process or have access to in the course "
        "of your employment, concerning the business and affairs of the Company.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "During your employment you will observe all the rules and regulations of the Company.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "The Company also reserves the right to rescind, revoke, amend or withdraw this Offer Letter or "
        "any of the terms outlined herein without assigning any reason.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        f"We trust that you will find the above in order. Please feel free to contact the undersigned for "
        f"any clarifications/questions that you may have. To confirm your acceptance of this Offer Letter, "
        f"please sign at the bottom of this page, scan and email us the duplicate copy duly signed, and your "
        f"joining date will be the {joining_date_str}.",
        letter_style,
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "We are very excited to welcome you to our team and look forward to your contribution to the growth of our company.",
        letter_style,
    ))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Regards,", letter_style))
    story.append(Spacer(1, 24))
    story.append(Paragraph(employer_name, letter_style))
    story.append(Paragraph(employer_designation, letter_style))
    story.append(Spacer(1, 16))

    # Annexure I
    story.append(Paragraph("<b>Annexure I</b>", styles["Heading2"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Employee Name: {candidate_name}", letter_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>ANNUAL COMPENSATION STRUCTURE: (All components are in Rs.)</b>", letter_style))
    story.append(Spacer(1, 8))

    # Compensation table — `or 0` guards against None from blank optional DecimalFields.
    def _f(key: str) -> float:
        return float(data.get(key) or 0)

    basic_monthly = _f("basic_monthly")
    basic_annual = _f("basic_annual")
    da_monthly = _f("da_monthly")
    da_annual = _f("da_annual")
    hra_monthly = _f("hra_monthly")
    hra_annual = _f("hra_annual")
    ta_monthly = _f("ta_monthly")
    ta_annual = _f("ta_annual")
    food_monthly = _f("food_allowance_monthly")
    food_annual = _f("food_allowance_annual")
    pf_emp_monthly = _f("pf_employee_monthly")
    pf_emp_annual = _f("pf_employee_annual")
    pf_empr_monthly = _f("pf_employer_monthly")
    pf_empr_annual = _f("pf_employer_annual")

    total_monthly = basic_monthly + da_monthly + hra_monthly + ta_monthly + food_monthly
    total_annual = basic_annual + da_annual + hra_annual + ta_annual + food_annual
    net_monthly = total_monthly - pf_emp_monthly
    net_annual = total_annual - pf_emp_annual

    comp_data = [
        ["Elements", "Monthly (Rs.)", "Annual (Rs.)"],
        ["Basic", f"{basic_monthly:,.2f}", f"{basic_annual:,.2f}"],
        ["DA", f"{da_monthly:,.2f}", f"{da_annual:,.2f}"],
        ["HRA", f"{hra_monthly:,.2f}", f"{hra_annual:,.2f}"],
        ["TA", f"{ta_monthly:,.2f}", f"{ta_annual:,.2f}"],
        ["Food Allowance", f"{food_monthly:,.2f}", f"{food_annual:,.2f}"],
        ["Total", f"{total_monthly:,.2f}", f"{total_annual:,.2f}"],
        ["PF (Employee Contribution)", f"{pf_emp_monthly:,.2f}", f"{pf_emp_annual:,.2f}"],
        ["Net Salary", f"{net_monthly:,.2f}", f"{net_annual:,.2f}"],
    ]

    comp_table = Table(comp_data, colWidths=[70 * mm, 50 * mm, 50 * mm])
    comp_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(comp_table)
    story.append(Spacer(1, 12))

    # Benefits
    story.append(Paragraph("<b>Benefits</b>", letter_style))
    benefits_data = [
        ["PF (Employer Contribution)", f"{pf_empr_monthly:,.2f}", f"{pf_empr_annual:,.2f}"],
    ]
    benefits_table = Table(benefits_data, colWidths=[70 * mm, 50 * mm, 50 * mm])
    benefits_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(benefits_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "On receipt of this letter, please send us your confirmation as a token of your acceptance within 2 days. "
        "We look forward to working with you and we are confident you will be able to make a significant contribution "
        "to the growth and success of the organization.",
        letter_style,
    ))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Sincerely,", letter_style))
    story.append(Spacer(1, 24))
    story.append(Paragraph(employer_name, letter_style))
    story.append(Paragraph(employer_designation, letter_style))
    story.append(Spacer(1, 16))

    # Acknowledgement
    story.append(Paragraph("<b>ACKNOWLEDGEMENT</b>", styles["Heading2"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "I have read and understood the terms and conditions stated above and hereby signify my acceptance of the same.",
        letter_style,
    ))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Signature…………………………………………… Date…………………", letter_style))

    doc.build(story)
    return buffer.getvalue()


def build_experience_certificate_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=55 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    letter_style = ParagraphStyle(
        "letter_style",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
    )
    center_style = ParagraphStyle(
        "center_style",
        parent=styles["Normal"],
        fontSize=12,
        alignment=1,  # Center alignment
    )
    story: list = []

    # Extract data
    certificate_type = str(data.get("certificate_type", "employee")).strip() or "employee"
    title = str(data.get("title", "")).strip()
    employee_name = str(data.get("employee_name_exp", "")).strip()
    employee_no = str(data.get("employee_no", "")).strip()
    company_name = str(data.get("company_name_exp", "")).strip()
    join_date = data.get("join_date_exp")
    leaving_date = data.get("leaving_date")
    gender = str(data.get("gender", "male")).strip()
    designation = str(data.get("designation_exp", "")).strip()
    signatory = str(data.get("signatory_exp", "")).strip()
    signatory_designation = str(data.get("signatory_designation_exp", "")).strip()

    intern_name = str(data.get("intern_name", "")).strip()
    internship_domain = str(data.get("internship_domain", "")).strip()
    internship_company = str(data.get("internship_company", "")).strip()
    internship_location = str(data.get("internship_location", "")).strip()
    internship_start_date = data.get("internship_start_date")
    internship_end_date = data.get("internship_end_date")

    # Format dates
    today = date.today()
    date_str = today.strftime("%b. %d, %Y").replace(" 0", " ")
    
    if join_date:
        join_date_str = join_date.strftime("%b. %d, %Y").replace(" 0", " ")
    else:
        join_date_str = "-"
    
    if leaving_date:
        leaving_date_str = leaving_date.strftime("%b. %d, %Y").replace(" 0", " ")
    else:
        leaving_date_str = "-"

    # Gender-based pronouns
    if gender.lower() == "male":
        his_her = "his"
        him_her = "him"
        he_she = "he"
    else:
        his_her = "her"
        him_her = "her"
        he_she = "she"

    # Date
    story.append(Paragraph(f"Date: {date_str}", styles["Normal"]))
    story.append(Spacer(1, 16))

    if certificate_type == "internship":
        # Format internship dates
        if internship_start_date:
            internship_start_str = internship_start_date.strftime("%b. %d, %Y").replace(" 0", " ")
        else:
            internship_start_str = "-"
        if internship_end_date:
            internship_end_str = internship_end_date.strftime("%b. %d, %Y").replace(" 0", " ")
        else:
            internship_end_str = "-"

        story.append(Paragraph("Internship Experience Certificate", styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", center_style))
        story.append(Spacer(1, 16))

        story.append(
            Paragraph(
                f"This is to certify that {intern_name} has done {his_her} internship in "
                f"{internship_domain} at our firm {internship_company} - {internship_location}, "
                f"from {internship_start_str} to {internship_end_str}.",
                letter_style,
            )
        )
        story.append(Spacer(1, 16))
        story.append(
            Paragraph(
                f"During {his_her} internship, {intern_name} demonstrated {his_her} skills with self–motivation to learn "
                f"new skills. {his_her.capitalize()} performance exceeded our expectations, and {he_she} was able to "
                f"complete the internship on time.",
                letter_style,
            )
        )
        story.append(Spacer(1, 16))
        story.append(Paragraph(f"We wish {him_her} all the best in {his_her} future endeavors.", letter_style))
        story.append(Spacer(1, 24))
    else:
        # Employee experience letter
        story.append(Paragraph("Experience Letter", styles["Title"]))
        story.append(Spacer(1, 12))

        story.append(Paragraph("<b>TO WHOMSOEVER IT MAY CONCERN</b>", center_style))
        story.append(Spacer(1, 16))

        story.append(
            Paragraph(
                f"This is to certify that {title} {employee_name} bearing employee ID {employee_no} has worked with "
                f"{company_name} and left our organization on {leaving_date_str}.",
                letter_style,
            )
        )
        story.append(Spacer(1, 8))

        story.append(Paragraph(f"<b>Duration:</b> {join_date_str} to {leaving_date_str}", letter_style))
        story.append(Spacer(1, 8))

        story.append(
            Paragraph(
                f"During {his_her} work tenure, {employee_name} has remained dedicated and loyal to {his_her} work and "
                f"responsibilities with our company. The designation of {employee_name} at the time of leaving the "
                f"organization was {designation}.",
                letter_style,
            )
        )
        story.append(Spacer(1, 8))

        story.append(
            Paragraph(
                f"The employee's performance was outstanding, and we appreciate the services rendered to our organization. "
                f"We wish {him_her} all the best for {his_her} future endeavors.",
                letter_style,
            )
        )
        story.append(Spacer(1, 8))

        story.append(Paragraph("Please feel free to be in touch with us for any additional information.", letter_style))
        story.append(Spacer(1, 24))

    # Signature
    story.append(Paragraph("Authorized Signatory,", letter_style))
    story.append(Spacer(1, 36))
    story.append(Paragraph(signatory, letter_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(signatory_designation, letter_style))

    doc.build(story)
    return buffer.getvalue()


def build_travel_expense_pdf(data: dict) -> bytes:
    import json
    from datetime import datetime

    BRAND      = colors.HexColor("#1e3a5f")
    BRAND_LIGHT = colors.HexColor("#e8f0fe")
    GRAY_TEXT  = colors.HexColor("#6b7280")
    GRAY_LINE  = colors.HexColor("#e5e7eb")
    BLUE_TOTAL = colors.HexColor("#0078d4")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story: list = []

    # ── Extract data ──────────────────────────────────────────────────────────
    company_name      = str(data.get("company_name_travel", "")).strip().upper()
    company_address   = str(data.get("company_address_travel", "")).strip()
    company_city_state = str(data.get("company_city_state", "")).strip()
    company_country   = str(data.get("company_country", "India")).strip()
    report_title      = str(data.get("report_title", "")).strip()
    business_purpose  = str(data.get("business_purpose", "")).strip()
    submitted_by      = str(data.get("submitted_by", "")).strip()
    submitted_on      = data.get("submitted_on")
    report_to         = str(data.get("report_to", "")).strip()
    period_start      = data.get("reporting_period_start")
    period_end        = data.get("reporting_period_end")
    report_number     = str(data.get("report_number", "ER-10001")).strip()
    report_currency   = str(data.get("report_currency", "INR")).strip()

    # ── Currency symbol (ASCII-safe for Helvetica) ────────────────────────────
    currency_symbol = {"INR": "Rs.", "USD": "$", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY"}.get(report_currency, "Rs.")

    # ── Parse expense rows ────────────────────────────────────────────────────
    expense_data_str = data.get("expense_data", "[]")
    try:
        expenses = json.loads(expense_data_str) if expense_data_str else []
    except Exception:
        expenses = []

    # ── Format dates ──────────────────────────────────────────────────────────
    def _fmt(d):
        if not d:
            return "-"
        try:
            return d.strftime("%b. %d, %Y").replace(" 0", " ")
        except Exception:
            return str(d)

    submitted_on_str  = _fmt(submitted_on)
    period_start_str  = _fmt(period_start)
    period_end_str    = _fmt(period_end)

    # ── Styles ────────────────────────────────────────────────────────────────
    lbl = ParagraphStyle("ER_lbl",  parent=styles["Normal"], fontSize=7,
                         fontName="Helvetica", textColor=GRAY_TEXT, spaceAfter=1)
    val = ParagraphStyle("ER_val",  parent=styles["Normal"], fontSize=10,
                         fontName="Helvetica-Bold", spaceAfter=6)
    th  = ParagraphStyle("ER_th",   parent=styles["Normal"], fontSize=9,
                         fontName="Helvetica-Bold", textColor=GRAY_TEXT)
    th_r = ParagraphStyle("ER_thr", parent=styles["Normal"], fontSize=9,
                          fontName="Helvetica-Bold", textColor=GRAY_TEXT, alignment=2)
    amt_r = ParagraphStyle("ER_amtr", parent=styles["Normal"], fontSize=9, alignment=2)
    ttl_lbl = ParagraphStyle("ER_ttllbl", parent=styles["Normal"], fontSize=10,
                              fontName="Helvetica-Bold", alignment=2)
    ttl_val = ParagraphStyle("ER_ttlval", parent=styles["Normal"], fontSize=11,
                              fontName="Helvetica-Bold", textColor=BLUE_TOTAL, alignment=2)
    sig_lbl = ParagraphStyle("ER_sig", parent=styles["Normal"], fontSize=9,
                              fontName="Helvetica-Bold", textColor=BRAND)
    foot    = ParagraphStyle("ER_foot", parent=styles["Normal"], fontSize=7,
                              textColor=GRAY_TEXT, alignment=1)

    # ── Brand accent bar ──────────────────────────────────────────────────────
    accent = Table([[""]], colWidths=[170 * mm], rowHeights=[3 * mm])
    accent.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), BRAND)]))
    story.append(accent)
    story.append(Spacer(1, 10))

    # ── Page header: company left, title right ────────────────────────────────
    city_line = ", ".join(filter(None, [company_city_state, company_country]))
    company_info = Paragraph(
        f"<b>{company_name}</b><br/>"
        f"<font size=9>{company_address}<br/>{city_line}</font>",
        ParagraphStyle("ER_co", parent=styles["Normal"], fontSize=13,
                       fontName="Helvetica-Bold", leading=16),
    )
    title_block = Paragraph(
        f"<font color='#9ca3af'>EXPENSE<br/>REPORT</font><br/>"
        f"<font size=9 color='black'><b>REF: {report_number}</b></font>",
        ParagraphStyle("ER_title", parent=styles["Normal"], fontSize=22,
                       fontName="Helvetica", alignment=2, leading=26),
    )
    hdr = Table([[company_info, title_block]], colWidths=[100 * mm, 70 * mm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN",  (1,0), (1,0),  "RIGHT"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 14))

    # ── Divider ───────────────────────────────────────────────────────────────
    div = Table([[""]], colWidths=[170 * mm], rowHeights=[0.5])
    div.setStyle(TableStyle([("LINEABOVE", (0,0), (-1,-1), 0.8, BRAND)]))
    story.append(div)
    story.append(Spacer(1, 10))

    # ── Report details (3-column) ─────────────────────────────────────────────
    details = Table([
        [Paragraph("REPORT TITLE",    lbl), Paragraph("SUBMITTED BY",  lbl), Paragraph("SUBMITTED ON", lbl)],
        [Paragraph(report_title,      val), Paragraph(submitted_by,    val), Paragraph(submitted_on_str, val)],
        [Paragraph("BUSINESS PURPOSE",lbl), Paragraph("REPORTING PERIOD", lbl), Paragraph("REPORT TO",  lbl)],
        [Paragraph(business_purpose,  val),
         Paragraph(f"{period_start_str} - {period_end_str}", val),
         Paragraph(report_to,         val)],
    ], colWidths=[57 * mm, 70 * mm, 43 * mm])
    details.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
    ]))
    story.append(details)
    story.append(Spacer(1, 16))

    # ── Expense table ─────────────────────────────────────────────────────────
    COL_W = [30 * mm, 72 * mm, 38 * mm, 30 * mm]
    rows = [[Paragraph("DATE", th), Paragraph("DESCRIPTION", th),
             Paragraph("MERCHANT", th), Paragraph("AMOUNT", th_r)]]
    total_amount = 0.0

    for exp in expenses:
        exp_date    = exp.get("date", "-")
        description = exp.get("description", "-")
        merchant    = exp.get("merchant", "-") or "-"
        try:
            amount = float(exp.get("amount", 0))
        except (ValueError, TypeError):
            amount = 0.0

        if exp_date and exp_date != "-":
            try:
                exp_date = datetime.strptime(exp_date, "%Y-%m-%d").strftime("%d %b %Y")
            except Exception:
                pass

        rows.append([
            exp_date, description, merchant,
            Paragraph(f"{currency_symbol} {amount:,.2f}", amt_r),
        ])
        total_amount += amount

    exp_tbl = Table(rows, colWidths=COL_W)
    exp_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  BRAND_LIGHT),
        ("LINEBELOW",    (0,0), (-1,0),  1,   BRAND),
        ("LINEBELOW",    (0,1), (-1,-1), 0.4, GRAY_LINE),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("ALIGN",        (3,0), (3,-1),  "RIGHT"),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(exp_tbl)
    story.append(Spacer(1, 16))

    # ── Totals block (right-aligned, fixed column widths) ─────────────────────
    amt_col = 45 * mm   # wide enough for "Rs. 99,999.00"
    lbl_col = 40 * mm
    gap_col = 170 * mm - lbl_col - amt_col

    totals = Table([
        [Paragraph("Subtotal",   ttl_lbl), Paragraph(f"{currency_symbol} {total_amount:,.2f}", ttl_lbl)],
        [Paragraph("Grand Total", ttl_lbl), Paragraph(f"{currency_symbol} {total_amount:,.2f}", ttl_val)],
    ], colWidths=[lbl_col, amt_col],
       hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN",        (0,0), (-1,-1), "RIGHT"),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("LINEABOVE",    (0,0), (-1,0),  0.5, GRAY_LINE),
        ("LINEABOVE",    (0,1), (-1,1),  1.2, BRAND),
        ("BACKGROUND",   (0,1), (-1,1),  BRAND_LIGHT),
        ("LINEBELOW",    (0,1), (-1,1),  1.2, BRAND),
    ]))
    story.append(totals)
    story.append(Spacer(1, 30))

    # ── Signature section ─────────────────────────────────────────────────────
    sig = Table([
        [Paragraph("EMPLOYEE SIGNATURE", sig_lbl), Paragraph("APPROVER SIGNATURE", sig_lbl)],
        ["", ""],
    ], colWidths=[85 * mm, 85 * mm])
    sig.setStyle(TableStyle([
        ("LINEABOVE",    (0,0), (-1,0),  1,  GRAY_LINE),
        ("TOPPADDING",   (0,0), (-1,0),  28),
        ("BOTTOMPADDING",(0,0), (-1,0),  6),
        ("TOPPADDING",   (0,1), (-1,1),  30),
    ]))
    story.append(sig)
    story.append(Spacer(1, 20))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Paragraph(f"Generated via {company_name} Expense Management System", foot))

    doc.build(story)
    return buffer.getvalue()

