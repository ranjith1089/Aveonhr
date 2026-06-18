from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from .forms import (
    ExperienceCertificateForm,
    OfferLetterForm,
    PayslipUploadForm,
    TravelExpenseForm,
    ProposalQuotationForm,
)
from .services.payslip_service import generate_payslips
from .utils import (
    CompanyInfo,
    build_appointment_order_pdf,
    build_employment_offer_pdf,
    build_experience_certificate_pdf,
    build_offer_letter_pdf,
    build_travel_expense_pdf,
)

_FILE_CACHE: dict[str, tuple[bytes, str, str]] = {}


def _save_content(content: bytes | str, content_type: str, filename: str) -> str:
    token = uuid.uuid4().hex
    if isinstance(content, str):
        stored = content.encode("utf-8")
    else:
        stored = bytes(content)
    _FILE_CACHE[token] = (stored, content_type, filename)
    return token


def _get_content(token: str) -> tuple[bytes, str, str] | None:
    return _FILE_CACHE.get(token)


def upload_payslips(request: HttpRequest) -> HttpResponse:
    context = {"form": PayslipUploadForm()}
    if request.method != "POST":
        return render(request, "payslip/upload.html", context)

    form = PayslipUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/upload.html", context)

    company = CompanyInfo(
        name=form.cleaned_data["company_name"],
        address=form.cleaned_data["company_address"],
        email=form.cleaned_data.get("company_email"),
        phone=form.cleaned_data.get("company_phone"),
    )
    logo = form.cleaned_data.get("company_logo")
    logo_bytes = logo.read() if logo else None

    salary_file = form.cleaned_data["salary_file"]
    try:
        result = generate_payslips(salary_file.read(), company, logo_bytes)
    except ValueError as exc:
        context["form"] = form
        context["error"] = str(exc)
        return render(request, "payslip/upload.html", context)

    preview_token = _save_content(result.preview_content, "application/pdf", result.preview_filename)
    download_token = _save_content(result.content, result.content_type, result.filename)

    download_label = "Download PDF" if result.content_type == "application/pdf" else "Download ZIP"
    download_filename = result.filename

    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_token})
    context["download_label"] = download_label
    context["download_filename"] = download_filename
    return render(request, "payslip/preview.html", context)


def landing(request: HttpRequest) -> HttpResponse:
    return render(request, "payslip/landing.html")


def offer_letter(request: HttpRequest) -> HttpResponse:
    context = {"form": OfferLetterForm()}
    if request.method != "POST":
        return render(request, "payslip/offer_letter.html", context)

    form = OfferLetterForm(request.POST)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/offer_letter.html", context)

    context["form"] = form
    context["data"] = form.cleaned_data
    context["offer_type_label"] = dict(form.fields["offer_type"].choices).get(
        form.cleaned_data["offer_type"], form.cleaned_data["offer_type"]
    )
    pdf_data = dict(form.cleaned_data)
    pdf_data["offer_type_label"] = context["offer_type_label"]
    
    # Generate PDF based on letter type
    offer_type = form.cleaned_data.get("offer_type")
    if offer_type == "appointment":
        pdf_bytes = build_appointment_order_pdf(pdf_data)
        filename = "appointment_order.pdf"
    elif offer_type == "employment_offer":
        pdf_bytes = build_employment_offer_pdf(pdf_data)
        filename = "employment_offer.pdf"
    else:
        pdf_bytes = build_offer_letter_pdf(pdf_data)
        filename = "offer_letter.pdf"
    
    preview_token = _save_content(pdf_bytes, "application/pdf", filename)
    download_token = _save_content(pdf_bytes, "application/pdf", filename)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_token})
    context["download_label"] = "Download PDF"
    context["download_filename"] = filename
    return render(request, "payslip/offer_letter.html", context)


@require_GET
@xframe_options_exempt
def preview_pdf(request: HttpRequest, token: str) -> HttpResponse:
    stored = _get_content(token)
    if not stored:
        return HttpResponse("PDF not found.", status=404)
    content, content_type, filename = stored
    if content_type != "application/pdf":
        return HttpResponse("Preview is not a PDF.", status=500)
    if not content.startswith(b"%PDF-"):
        snippet = repr(content[:12])
        return HttpResponse(f"Invalid PDF content. Starts with {snippet}.", status=500)
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Content-Length"] = str(len(content))
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def download_file(request: HttpRequest, token: str) -> HttpResponse:
    stored = _get_content(token)
    if not stored:
        return HttpResponse("File not found.", status=404)
    content, content_type, filename = stored
    if content_type == "application/pdf" and not content.startswith(b"%PDF-"):
        return HttpResponse("Invalid PDF content.", status=500)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(content))
    response["Cache-Control"] = "no-store"
    return response


def experience_certificate(request: HttpRequest) -> HttpResponse:
    context = {"form": ExperienceCertificateForm()}
    if request.method != "POST":
        return render(request, "payslip/experience_certificate.html", context)

    form = ExperienceCertificateForm(request.POST)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/experience_certificate.html", context)

    context["form"] = form
    context["data"] = form.cleaned_data

    pdf_bytes = build_experience_certificate_pdf(form.cleaned_data)
    cert_type = (form.cleaned_data.get("certificate_type") or "employee").strip() or "employee"
    raw_name = ""
    if cert_type == "internship":
        raw_name = str(form.cleaned_data.get("intern_name") or "").strip()
        suffix = "internship_experience_certificate"
    else:
        raw_name = str(form.cleaned_data.get("employee_name_exp") or "").strip()
        suffix = "experience_letter"

    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", raw_name).strip("_") or "experience_certificate"
    filename = f"{safe_name}_{suffix}.pdf"

    preview_token = _save_content(pdf_bytes, "application/pdf", filename)
    download_token = _save_content(pdf_bytes, "application/pdf", filename)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_token})
    context["download_label"] = "Download PDF"
    context["download_filename"] = filename
    return render(request, "payslip/experience_certificate.html", context)





def _proposal_system_title(institution_type: str) -> str:
    """
    Map institution type to proposal system title.
    - AUTONOMOUS => Aveon College Management System
    - SCHOOL => Aveon School Management System
    - ARTS & SCIENCE / ENGINEERING / AFFILIATED => Aveon College Management System
    """
    if (institution_type or "").strip().upper() == "SCHOOL":
        return "Aveon School Management System (SMS) ERP"
    return "Aveon College Management System (CMS) ERP"


def _title_case_institution(institution_type: str) -> str:
    v = (institution_type or "").strip().upper()
    if v == "ARTS & SCIENCE":
        return "Arts & Science"
    if v == "AUTONOMOUS":
        return "Autonomous"
    if v == "AFFILIATED":
        return "Affiliated"
    if v == "ENGINEERING":
        return "Engineering"
    if v == "SCHOOL":
        return "School"
    return institution_type


def _format_inr(amount: Decimal) -> str:
    """
    Indian-style comma formatting.
    350000 -> 3,50,000
    """
    try:
        n = int(Decimal(amount).to_integral_value())
    except Exception:
        return str(amount)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return f"{sign}{s}"
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return f"{sign}{','.join(parts)},{last3}"


def _renumber_main_sections(text: str) -> str:
    """
    Renumber only top-level headings (e.g., '2. SUBJECT...' -> '1. SUBJECT...').
    Does NOT touch sub-sections like '5.1 ...' because those don't match 'digit-dot-space'.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            num = int(m.group(1))
            if num >= 2:
                out_lines.append(f"{num - 1}. {m.group(2)}")
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _build_cms_proposal_text(
    client_name: str,
    client_location: str,
    institution_type: str,
    proposal_date: date | None = None,
    prepared_by: str | None = None,
    per_student_annual_license: Decimal | None = None,
    minimum_student_commitment: int | None = None,
    one_time_implementation_fee: Decimal | None = None,
    gst_percent: Decimal | None = None,
    authorized_signatory_name: str | None = None,
    authorized_signatory_designation: str | None = None,
    jurisdiction: str | None = None,
) -> str:
    system_title = _proposal_system_title(institution_type)
    proposal_date_str = proposal_date.strftime("%d/%m/%Y") if proposal_date else "[DD/MM/YYYY]"
    prepared_by = (prepared_by or "Aveon Infotech Private Limited").strip()
    client_line = f"{client_name}, {client_location}".strip().strip(",")
    institution_label = _title_case_institution(institution_type)

    per_student = Decimal(per_student_annual_license or 0)
    min_students = int(minimum_student_commitment or 0)
    impl_fee = Decimal(one_time_implementation_fee or 0)
    gst = Decimal(gst_percent or 0)

    annual_license = (per_student * Decimal(min_students)) if min_students else Decimal(0)
    subtotal = annual_license + impl_fee
    gst_amount = (subtotal * gst / Decimal(100)) if subtotal else Decimal(0)
    total_year1 = subtotal + gst_amount

    aligned_points = [
        "CBCS Framework",
        "Outcome-Based Education (OBE)",
        "NAAC Accreditation Requirements",
        "NIRF Reporting Standards",
        "IQAC Governance",
    ]
    if (institution_type or "").strip().upper() == "AUTONOMOUS":
        aligned_points.append("Autonomous College Regulations")

    jurisdiction = (jurisdiction or "").strip()
    sign_name = (authorized_signatory_name or "").strip()
    sign_desig = (authorized_signatory_designation or "").strip()

    text = f"""{system_title}

Prepared By:
{prepared_by}

Client:
{client_line}

Institution Type: {institution_label}

Date: {proposal_date_str}

1. Executive Summary

{prepared_by} is pleased to submit this proposal for the implementation of the {system_title} at {client_line}.

The proposed ERP platform is designed to digitize, integrate, and streamline the institution’s academic, administrative, financial, and compliance operations into a single secure and scalable system.

The solution is aligned with:
{chr(10).join([f"- {p}" for p in aligned_points])}

This proposal is submitted for evaluation by the Management, Principal, IQAC, Finance Committee, and Purchase Committee.

2. About {prepared_by}

Established: 2012
Core Focus: Educational ERP & Institutional Automation

Core Expertise
- College ERP & University ERP
- Controller of Examination (COE) Automation
- NAAC / NIRF / IQAC Data Systems
- Finance & Payroll Automation
- Hostel & Library Management
- Custom Institutional Software Development

Institutional Strengths
- Deep understanding of Indian Higher Education processes
- Experience with Autonomous & Affiliated institutions
- Governance-driven implementation methodology
- Structured documentation and milestone-based execution

3. Scope of Work - Module Overview

The ERP will cover the following independent modules:

3.1 Admission & Student Lifecycle Management
- Online enquiry, registration, and application
- Merit list generation
- Admission round management
- Document verification tracking
- Fee challan generation
- Digital student record (Admission to Alumni)
- Certificate issuance tracking

3.2 Academic Management (CBCS / OBE Enabled)
- Academic calendar configuration
- Program / Semester / Section structuring
- CBCS curriculum mapping
- Credit tracking
- Open elective management
- CO–PO–PSO mapping
- Attainment analytics
- Attendance & internal marks management
- Assignment workflows

3.3 Learning Management System (LMS)
- Course-wise content upload
- Lesson plan tracking
- Assignment submission & evaluation
- Discussion forums
- Academic audit trails

3.4 Controller of Examination (COE) Module
- Exam timetable planning
- Hall allocation
- Examination application processing
- Mark entry (Internal & External)
- SGPA / CGPA calculation
- Result publication
- Revaluation & arrear management
- Academic history records

3.5 Fees Collection Module
- Program-wise fee configuration
- Installment structure setup
- Scholarship & concession management
- Online payment gateway integration
- Offline fee collection
- Auto receipt generation
- Student ledger & outstanding tracking
- Refund management
- Real-time collection dashboard

3.6 Finance & Accounts Module
- Income & expense tracking
- Cash / Bank reconciliation
- Ledger reports
- Department-wise financial analytics
- GST-ready reporting (if applicable)
- Management financial dashboards

3.7 HR & Payroll Module
- Employee master & service history
- Attendance & leave management
- Payroll processing
- Payslip generation
- Statutory reporting support

3.8 Library Management Module
- Book accession & catalog management
- Issue / return / renewal workflows
- Fine calculation
- Member borrowing limits
- Library usage reports

3.9 Hostel Management Module
- Hostel master setup
- Room allocation & occupancy tracking
- Mess billing support
- Hostel fee integration
- Visitor tracking
- Vacancy reports

3.10 Transport Management Module
- Route & stage configuration
- Vehicle & driver management
- Student route allocation
- Transport fee mapping
- Route occupancy reports

3.11 Inventory & Asset Management Module
- Item & category master
- Purchase request workflow
- Stock entry & issue tracking
- Asset tagging
- Vendor management
- Stock reconciliation reports

3.12 Feedback Management Module
- NAAC-aligned questionnaire templates
- Student → Faculty feedback
- Student → Course feedback
- Alumni feedback
- Employer feedback
- Faculty self-appraisal
- Semester-wise feedback activation
- Department-wise analytics
- NAAC & IQAC report exports

3.13 NAAC / NIRF / IQAC Compliance Module
- NAAC criteria-wise structured data capture
- Evidence document repository
- NIRF data templates
- AQAR report support
- Department KPI dashboards

3.14 Communication & Mobile Application
- Role-based mobile access
- Push notifications
- SMS / WhatsApp / Email integration
- Communication audit logs

4. Implementation Methodology

Phase 1 – Requirement Analysis
- Stakeholder workshops
- Process study
- Scope finalization

Phase 2 – Configuration & Setup
- Academic structure configuration
- Role & workflow setup

Phase 3 – Data Migration
- Template-based data submission
- Validation & reconciliation
- Client sign-off

Phase 4 – Training & UAT
- Role-based training sessions
- UAT execution
- Issue closure

Phase 5 – Go-Live & Stabilization
- Production rollout
- Hypercare support
- Performance review

5. Project Timeline

Estimated Duration: 12 – 16 Weeks

Phase                         Duration
Requirement Study              Week 1–2
Configuration                  Week 3–5
Data Migration                 Week 6–8
Training & UAT                 Week 9–11
Go-Live                        Week 12–16

Timeline subject to timely approvals and data submission.

6. Commercial Proposal

Pricing Model
- Per Student Annual SaaS License: INR {_format_inr(per_student)}
- Minimum Student Commitment: {min_students}
- One-Time Implementation Fee: INR {_format_inr(impl_fee)}
- GST: {gst}% Extra

Year 1 Cost Illustration ({min_students} Students)
Component                     Amount
License                        INR {_format_inr(annual_license)}
Implementation                 INR {_format_inr(impl_fee)}
Subtotal                       INR {_format_inr(subtotal)}
GST ({gst}%)                    INR {_format_inr(gst_amount)}
Total (Year 1)                 INR {_format_inr(total_year1)}

Payment Terms
- 40% Implementation + 100% License – At Work Order
- 40% Implementation – After Configuration & Migration
- 20% Implementation – At Go-Live
- Renewal – Before start of academic year

7. Support & Maintenance
- Business-hour helpdesk support
- Ticket-based issue management
- Minor upgrades included
- Periodic review meetings
- Optional annual system health-check

8. Key Terms & Conditions
- GST applicable as per law
- Scope limited to listed modules
- Additional customization treated as change request
- Data accuracy responsibility rests with client
- Third-party services billed separately
- Intellectual Property remains with Aveon
- Liability limited to fees received
{f"- Jurisdiction: {jurisdiction}" if jurisdiction else ""}

9. Why Aveon Infotech
- 14+ Years ERP Experience
- Autonomous College Expertise
- Accreditation-Ready Architecture
- Governance-Based Implementation
- Scalable & Secure Platform
- Long-Term Institutional Partnership Approach

10. Authorization

For
{prepared_by}

Authorized Signatory
{sign_name}
{sign_desig}

Date: ___________
Place: ___________
"""
    return text
def travel_expense(request: HttpRequest) -> HttpResponse:
    context = {"form": TravelExpenseForm()}
    if request.method != "POST":
        return render(request, "payslip/travel_expense.html", context)

    form = TravelExpenseForm(request.POST)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/travel_expense.html", context)

    context["form"] = form
    context["data"] = form.cleaned_data

    pdf_bytes = build_travel_expense_pdf(form.cleaned_data)
    filename = "travel_expense_report.pdf"

    preview_token = _save_content(pdf_bytes, "application/pdf", filename)
    download_token = _save_content(pdf_bytes, "application/pdf", filename)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_token})
    context["download_label"] = "Download PDF"
    context["download_filename"] = filename
    return render(request, "payslip/travel_expense.html", context)





def _as_text_download_response(content: str, filename: str = "aveon_cms_erp_proposal.txt") -> HttpResponse:
    response = HttpResponse(content, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response



def _build_proposal_pdf_bytes(
    content: str,
    *,
    proposal_title: str | None = None,
    proposal_date: date | None = None,
    client_logo_bytes: bytes | None = None,
) -> bytes:
    """
    Render proposal text into a clean A4 PDF.

    - Uses A4 page size with proper margins
    - Adds Aveon logo (if available) in header
    - Applies basic typography: headings, bullets, and readable spacing
    """
    buffer = BytesIO()

    page_width, page_height = A4
    left_margin = 18 * mm
    right_margin = 18 * mm
    top_margin = 26 * mm
    bottom_margin = 18 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title="Aveon CMS ERP Proposal",
        author="Aveon Infotech Pvt Ltd",
    )

    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "ProposalBase",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=4,
        alignment=TA_JUSTIFY,
    )
    mono = ParagraphStyle(
        "ProposalMono",
        parent=base,
        fontName="Courier",
        alignment=TA_LEFT,
    )
    h1 = ParagraphStyle(
        "ProposalH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=10,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "ProposalH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#111827"),
        spaceBefore=10,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        "ProposalBullet",
        parent=base,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=2,
    )

    section_re = re.compile(r"^\d+\.\s+")
    phase_re = re.compile(r"^(Phase\s+\d+|Milestones|Support Coverage|Review and Governance)\b", re.IGNORECASE)

    def _paragraph_from_line(line: str) -> Paragraph | None:
        raw = line.rstrip("\n")
        if not raw.strip():
            return None

        # Headings like "1. COVER PAGE"
        if section_re.match(raw):
            return Paragraph(escape(raw), h1)

        # Secondary headings like "Phase 1: ..."
        if phase_re.match(raw):
            return Paragraph(escape(raw), h2)

        # Bullets
        stripped = raw.lstrip()
        if stripped.startswith("- "):
            return Paragraph(escape(stripped[2:]), bullet_style, bulletText="•")

        # Key: Value formatting (keep label bold)
        if ":" in raw:
            label, value = raw.split(":", 1)
            if 1 <= len(label.strip()) <= 28 and value.strip():
                return Paragraph(f"<b>{escape(label.strip())}:</b> {escape(value.strip())}", base)

        # Preserve some "code-ish" lines (placeholders, separators)
        if raw.strip().startswith("[") and raw.strip().endswith("]"):
            return Paragraph(escape(raw), mono)

        return Paragraph(escape(raw), base)

    def _header_footer(c, d) -> None:
        c.saveState()
        pw, ph = A4

        header_top = ph - 12 * mm
        x0 = d.leftMargin
        x1 = pw - d.rightMargin

        # Logo (best-effort)
        logo_path = Path(settings.BASE_DIR) / "payslip" / "static" / "payslip" / "logo.png"
        if logo_path.exists():
            logo_h = 12 * mm
            logo_w = 34 * mm
            logo_y = header_top - logo_h + 1 * mm
            c.drawImage(
                str(logo_path),
                x0,
                logo_y,
                width=logo_w,
                height=logo_h,
                preserveAspectRatio=True,
                mask="auto",
            )
            title_x = x0 + logo_w + 8
        else:
            title_x = x0

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.drawString(title_x, header_top - 9 * mm, proposal_title or "Aveon CMS ERP Proposal")

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#475569"))
        right_text = f"Page {d.page}"
        if proposal_date:
            right_text = f"{proposal_date.strftime('%d/%m/%Y')}  •  {right_text}"
        c.drawRightString(x1, header_top - 9 * mm, right_text)

        # Client logo on the right (best-effort)
        if client_logo_bytes:
            try:
                img = ImageReader(BytesIO(client_logo_bytes))
                client_h = 12 * mm
                client_w = 34 * mm
                client_y = header_top - client_h + 1 * mm
                c.drawImage(
                    img,
                    x1 - client_w,
                    client_y,
                    width=client_w,
                    height=client_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                # If logo parsing fails, silently skip.
                pass

        # Divider line
        c.setStrokeColor(colors.HexColor("#e5e7eb"))
        c.setLineWidth(1)
        # Keep the divider just above the content frame,
        # and below the logo so it doesn't look "cut" or overlapped.
        divider_y = ph - d.topMargin + 1 * mm
        c.line(x0, divider_y, x1, divider_y)

        # Footer
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(x0, 10 * mm, "Generated via Aveon HR Suite")
        c.restoreState()

    story: list[object] = []
    # Add a bit of breathing room under the header divider.
    story.append(Spacer(1, 8))
    for line in content.splitlines():
        para = _paragraph_from_line(line)
        if para is None:
            story.append(Spacer(1, 6))
        else:
            story.append(para)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    data = buffer.getvalue()
    buffer.close()
    return data


def _as_pdf_download_response(
    content: str,
    *,
    filename: str = "aveon_cms_erp_proposal.pdf",
    proposal_title: str | None = None,
    proposal_date: date | None = None,
    client_logo_bytes: bytes | None = None,
) -> HttpResponse:
    response = HttpResponse(
        _build_proposal_pdf_bytes(
            content,
            proposal_title=proposal_title,
            proposal_date=proposal_date,
            client_logo_bytes=client_logo_bytes,
        ),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response

def proposal_quotation(request: HttpRequest) -> HttpResponse:
    context = {"form": ProposalQuotationForm()}
    if request.method != "POST":
        return render(request, "payslip/proposal_quotation.html", context)

    form = ProposalQuotationForm(request.POST, request.FILES)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/proposal_quotation.html", context)

    proposal_text = _build_cms_proposal_text(
        form.cleaned_data["client_name"],
        form.cleaned_data["client_location"],
        form.cleaned_data["institution_type"],
        form.cleaned_data.get("proposal_date"),
        form.cleaned_data.get("prepared_by"),
        form.cleaned_data.get("per_student_annual_license"),
        form.cleaned_data.get("minimum_student_commitment"),
        form.cleaned_data.get("one_time_implementation_fee"),
        form.cleaned_data.get("gst_percent"),
        form.cleaned_data.get("authorized_signatory_name"),
        form.cleaned_data.get("authorized_signatory_designation"),
        form.cleaned_data.get("jurisdiction"),
    )

    if request.POST.get("action") == "download":
        return _as_text_download_response(proposal_text)
    if request.POST.get("action") == "download_pdf":
        client_logo = form.cleaned_data.get("client_logo")
        client_logo_bytes = client_logo.read() if client_logo else None
        pdf_header_title = _proposal_system_title(form.cleaned_data["institution_type"])
        return _as_pdf_download_response(
            proposal_text,
            proposal_title=pdf_header_title,
            proposal_date=form.cleaned_data.get("proposal_date"),
            client_logo_bytes=client_logo_bytes,
        )

    context["form"] = form
    context["proposal_text"] = proposal_text
    return render(request, "payslip/proposal_quotation.html", context)
