from __future__ import annotations

import re
import uuid

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

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
        return HttpResponse("File not found.", status=404)
    content, content_type, filename = stored
    if content_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            snippet = repr(content[:12])
            return HttpResponse(f"Invalid PDF content. Starts with {snippet}.", status=500)
    elif not content_type.startswith("text/html"):
        return HttpResponse("Preview type not supported.", status=415)
    response = HttpResponse(content, content_type=content_type)
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



# =========================================================================
# Proposal & Quotation — module-wise builder
# =========================================================================

def _split_address_lines(address: str) -> list[str]:
    return [line.strip() for line in (address or "").splitlines() if line.strip()]


def _build_proposal_context(form, request: HttpRequest) -> dict:
    """Translate a validated ProposalQuotationForm into a render context."""
    from .proposal_catalog import (
        BUNDLES,
        DEFAULT_PHASES,
        DEFAULT_TERMS,
        build_presentation,
        compute_pricing,
        resolve_selection,
    )

    cd = form.cleaned_data
    bundle_code = cd.get("bundle") or None
    modules = resolve_selection(
        selection_mode=cd["selection_mode"],
        bundle_code=bundle_code,
        module_codes=cd.get("selected_modules") or [],
    )

    pricing = compute_pricing(
        modules=modules,
        bundle_code=bundle_code,
        minimum_student_commitment=cd["minimum_student_commitment"],
        one_time_implementation_fee=cd["one_time_implementation_fee"],
        waive_one_time=cd.get("waive_one_time_fee", False),
        gst_percent=cd["gst_percent"],
        per_module_overrides=cd.get("pricing_overrides") or {},
    )

    presentation = build_presentation(
        bundle_code=bundle_code,
        modules=modules,
        client_name=cd["client_name"],
    )

    return {
        "proposal_title": f"Aveon Proposal — {cd['client_name']}",
        "prepared_by": cd["prepared_by"],
        "proposal_date": cd["proposal_date"],
        "to_address": cd["to_address"],
        "client_name": cd["client_name"],
        "client_address_lines": _split_address_lines(cd["client_address"]),
        "minimum_student_commitment": cd["minimum_student_commitment"],
        "modules": modules,
        "bundle": BUNDLES.get(bundle_code) if bundle_code else None,
        "pricing": pricing,
        "pricing_overrides": cd.get("pricing_overrides") or {},
        "hero": presentation["hero"],
        "hero_stats": presentation["hero_stats"],
        "default_phases": DEFAULT_PHASES,
        "default_terms": DEFAULT_TERMS,
        "authorized_signatory_name": cd["authorized_signatory_name"],
        "authorized_signatory_designation": cd["authorized_signatory_designation"],
        "jurisdiction": cd.get("jurisdiction") or "",
    }


def _render_proposal_html(form, request: HttpRequest) -> str:
    from django.template.loader import render_to_string
    ctx = _build_proposal_context(form, request)
    return render_to_string("payslip/proposals/base.html", ctx, request=request)


def _try_html_to_pdf(html: str) -> bytes | None:
    """Try WeasyPrint; return None if unavailable so caller can fall back."""
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return None
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None


def _proposal_form_context(form: ProposalQuotationForm) -> dict:
    """Catalog data the form template's JS uses to draw module cards & live total."""
    import json as _json
    from .proposal_catalog import BUNDLES, CATEGORIES, MODULES

    js_modules = {
        code: {
            "name": m["name"],
            "category": m["category"],
            "icon": m.get("icon", ""),
            "color": m.get("color", "#1565C0"),
            "short_desc": m.get("short_desc", ""),
            "price": str(m["default_price_per_student"]),
            "tag": m.get("tag", ""),
        }
        for code, m in MODULES.items()
    }
    js_bundles = {
        code: {
            "name": b["name"],
            "tagline": b.get("tagline", ""),
            "modules": b["modules"],
            "price": str(b["bundle_price_per_student"]),
            "standalone_total": str(b["standalone_total"]),
        }
        for code, b in BUNDLES.items()
    }
    return {
        "form": form,
        "catalog_json": _json.dumps({
            "modules": js_modules,
            "bundles": js_bundles,
            "categories": CATEGORIES,
        }),
    }


def proposal_quotation(request: HttpRequest) -> HttpResponse:
    context = _proposal_form_context(ProposalQuotationForm())
    if request.method != "POST":
        return render(request, "payslip/proposal_quotation.html", context)

    form = ProposalQuotationForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "payslip/proposal_quotation.html", _proposal_form_context(form))
    context = _proposal_form_context(form)

    html = _render_proposal_html(form, request)
    safe_client = re.sub(r"[^A-Za-z0-9_\-]+", "_", form.cleaned_data["client_name"]).strip("_") or "client"
    html_filename = f"aveon_proposal_{safe_client}.html"

    # Preview always serves the HTML — pixel-perfect in any browser.
    preview_token = _save_content(html.encode("utf-8"), "text/html; charset=utf-8", html_filename)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})

    # Download prefers PDF when WeasyPrint is installed; HTML otherwise.
    pdf = _try_html_to_pdf(html)
    if pdf:
        pdf_filename = f"aveon_proposal_{safe_client}.pdf"
        download_token = _save_content(pdf, "application/pdf", pdf_filename)
        context["download_url"] = reverse("download_file", kwargs={"token": download_token})
        context["download_label"] = "Download PDF"
        context["download_filename"] = pdf_filename
    else:
        download_token = _save_content(html.encode("utf-8"), "text/html; charset=utf-8", html_filename)
        context["download_url"] = reverse("download_file", kwargs={"token": download_token})
        context["download_label"] = "Download HTML (Print to PDF from browser)"
        context["download_filename"] = html_filename

    context["form"] = form
    return render(request, "payslip/proposal_quotation.html", context)
