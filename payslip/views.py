from __future__ import annotations

import re
from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

from .decorators import module_required, org_admin_required
from .forms import (
    OrganizationForm,
    ExperienceCertificateForm,
    OfferLetterForm,
    PayslipUploadForm,
    SignupForm,
    TravelExpenseForm,
    ProposalQuotationForm,
)
from .models import GeneratedFile, Membership, membership_for, org_for
from .pdf_styles import CompanyBranding


def _logo_data_uri(brand: CompanyBranding) -> str:
    """Inline logo as a data URI (browser preview, print-to-PDF, WeasyPrint).
    Prefers the tenant's profile logo; the bundled (Aveon) logo is only used
    for the default company."""
    import base64
    from .pdf_styles import COMPANY_NAME, LOGO_PATH
    try:
        if brand.logo_bytes:
            return "data:image/png;base64," + base64.b64encode(brand.logo_bytes).decode("ascii")
        if brand.name == COMPANY_NAME and LOGO_PATH.exists():
            return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    except Exception:
        pass
    return ""
from .services.payslip_service import generate_payslips
from .utils import (
    CompanyInfo,
    build_appointment_order_pdf,
    build_employment_offer_pdf,
    build_experience_certificate_pdf,
    build_offer_letter_pdf,
    build_travel_expense_pdf,
)

# Generated documents live in the database (GeneratedFile) so preview and
# download work across serverless instances and are scoped to their owner.
_FILE_RETENTION = timedelta(hours=24)


def _save_content(user, content: bytes | str, content_type: str, filename: str) -> str:
    if isinstance(content, str):
        stored = content.encode("utf-8")
    else:
        stored = bytes(content)
    # Opportunistic cleanup - no cron on serverless.
    GeneratedFile.objects.filter(created_at__lt=timezone.now() - _FILE_RETENTION).delete()
    obj = GeneratedFile.objects.create(
        user=user, content=stored, content_type=content_type, filename=filename
    )
    return obj.token


def _get_content(token: str, user) -> tuple[bytes, str, str] | None:
    obj = GeneratedFile.objects.filter(token=token, user=user).first()
    if obj is None:
        return None
    return bytes(obj.content), obj.content_type, obj.filename


# ---------------------------------------------------------------------------
# Auth + company profile
# ---------------------------------------------------------------------------
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("landing")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        membership_for(user)  # provision the organization + admin membership
        login(request, user)
        return redirect(f"{reverse('company_profile')}?welcome=1")
    return render(request, "registration/signup.html", {"form": form})


@org_admin_required
def company_profile(request: HttpRequest) -> HttpResponse:
    org = request.organization
    if request.method == "POST":
        form = OrganizationForm(request.POST, request.FILES, instance=org)
        if form.is_valid():
            form.save()
            return redirect(f"{reverse('company_profile')}?saved=1")
    else:
        form = OrganizationForm(instance=org)
    return render(request, "payslip/profile.html", {
        "form": form,
        "profile": org,
        "welcome": request.GET.get("welcome"),
        "saved": request.GET.get("saved"),
    })


@login_required
@require_GET
def profile_logo(request: HttpRequest) -> HttpResponse:
    org = org_for(request.user)
    if not org.logo:
        return HttpResponse(status=404)
    return HttpResponse(org.logo_bytes, content_type=org.logo_content_type or "image/png")


@module_required("payslips")
def upload_payslips(request: HttpRequest) -> HttpResponse:
    context = {"form": PayslipUploadForm(user=request.user)}
    if request.method != "POST":
        return render(request, "payslip/upload.html", context)

    form = PayslipUploadForm(request.POST, request.FILES, user=request.user)
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
    if logo_bytes is None:
        # Fall back to the saved company logo from the profile.
        logo_bytes = org_for(request.user).logo_bytes

    salary_file = form.cleaned_data["salary_file"]
    try:
        result = generate_payslips(salary_file.read(), company, logo_bytes)
    except ValueError as exc:
        context["form"] = form
        context["error"] = str(exc)
        return render(request, "payslip/upload.html", context)

    preview_token = _save_content(request.user, result.preview_content, "application/pdf", result.preview_filename)
    download_token = _save_content(request.user, result.content, result.content_type, result.filename)

    download_label = "Download PDF" if result.content_type == "application/pdf" else "Download ZIP"
    download_filename = result.filename

    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_token})
    context["download_label"] = download_label
    context["download_filename"] = download_filename
    return render(request, "payslip/preview.html", context)


def landing(request: HttpRequest) -> HttpResponse:
    membership = None
    allowed = {}
    if request.user.is_authenticated:
        membership = membership_for(request.user)
        allowed = {m: membership.has_module(m) for m in Membership.MODULE_FIELDS}
    return render(request, "payslip/landing.html", {
        "membership": membership,
        "allowed": allowed,
    })


@module_required("offer_letters")
def offer_letter(request: HttpRequest) -> HttpResponse:
    context = {"form": OfferLetterForm(user=request.user)}
    if request.method != "POST":
        return render(request, "payslip/offer_letter.html", context)

    form = OfferLetterForm(request.POST, user=request.user)
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
    
    # Generate PDF based on letter type — two versions: full digital
    # letterhead, and plain for pre-printed letterhead paper.
    offer_type = form.cleaned_data.get("offer_type")
    if offer_type == "appointment":
        builder, base = build_appointment_order_pdf, "appointment_order"
    elif offer_type == "employment_offer":
        builder, base = build_employment_offer_pdf, "employment_offer"
    else:
        builder, base = build_offer_letter_pdf, "offer_letter"

    brand = CompanyBranding.from_profile(org_for(request.user))
    pdf_letterhead = builder(pdf_data, letterhead=True, brand=brand)
    pdf_plain = builder(pdf_data, letterhead=False, brand=brand)
    filename_lh = f"{base}.pdf"
    filename_plain = f"{base}_plain.pdf"

    preview_token = _save_content(request.user, pdf_letterhead, "application/pdf", filename_lh)
    download_lh = _save_content(request.user, pdf_letterhead, "application/pdf", filename_lh)
    download_plain = _save_content(request.user, pdf_plain, "application/pdf", filename_plain)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_lh})
    context["download_plain_url"] = reverse("download_file", kwargs={"token": download_plain})
    context["download_label"] = "Download PDF"
    context["download_filename"] = filename_lh
    context["download_plain_name"] = filename_plain
    return render(request, "payslip/offer_letter.html", context)


@login_required
@require_GET
@xframe_options_exempt
def preview_pdf(request: HttpRequest, token: str) -> HttpResponse:
    stored = _get_content(token, request.user)
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


@login_required
@require_GET
def download_file(request: HttpRequest, token: str) -> HttpResponse:
    stored = _get_content(token, request.user)
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


@module_required("experience_certificates")
def experience_certificate(request: HttpRequest) -> HttpResponse:
    context = {"form": ExperienceCertificateForm(user=request.user)}
    if request.method != "POST":
        return render(request, "payslip/experience_certificate.html", context)

    form = ExperienceCertificateForm(request.POST, user=request.user)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/experience_certificate.html", context)

    context["form"] = form
    context["data"] = form.cleaned_data

    data = form.cleaned_data
    # Two versions: full digital letterhead, and plain for pre-printed paper.
    brand = CompanyBranding.from_profile(org_for(request.user))
    pdf_letterhead = build_experience_certificate_pdf(data, letterhead=True, brand=brand)
    pdf_plain = build_experience_certificate_pdf(data, letterhead=False, brand=brand)

    cert_type = (data.get("certificate_type") or "employee").strip() or "employee"
    if cert_type == "internship":
        raw_name = str(data.get("intern_name") or "").strip()
        suffix = "internship_experience_certificate"
    else:
        raw_name = str(data.get("employee_name_exp") or "").strip()
        suffix = "experience_letter"

    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", raw_name).strip("_") or "experience_certificate"
    filename_lh = f"{safe_name}_{suffix}.pdf"
    filename_plain = f"{safe_name}_{suffix}_plain.pdf"

    preview_token = _save_content(request.user, pdf_letterhead, "application/pdf", filename_lh)
    download_lh = _save_content(request.user, pdf_letterhead, "application/pdf", filename_lh)
    download_plain = _save_content(request.user, pdf_plain, "application/pdf", filename_plain)

    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})
    context["download_url"] = reverse("download_file", kwargs={"token": download_lh})
    context["download_plain_url"] = reverse("download_file", kwargs={"token": download_plain})
    context["download_label"] = "Download PDF"
    context["download_filename"] = filename_lh
    context["download_plain_name"] = filename_plain
    return render(request, "payslip/experience_certificate.html", context)





@module_required("travel_expense")
def travel_expense(request: HttpRequest) -> HttpResponse:
    context = {"form": TravelExpenseForm(user=request.user)}
    if request.method != "POST":
        return render(request, "payslip/travel_expense.html", context)

    form = TravelExpenseForm(request.POST, user=request.user)
    if not form.is_valid():
        context["form"] = form
        return render(request, "payslip/travel_expense.html", context)

    context["form"] = form
    context["data"] = form.cleaned_data

    pdf_bytes = build_travel_expense_pdf(form.cleaned_data)
    filename = "travel_expense_report.pdf"

    preview_token = _save_content(request.user, pdf_bytes, "application/pdf", filename)
    download_token = _save_content(request.user, pdf_bytes, "application/pdf", filename)
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
        bundle_code=bundle_code,
        price_per_unit=cd["price_per_unit"],
        minimum_student_commitment=cd["minimum_student_commitment"],
        one_time_implementation_fee=cd["one_time_implementation_fee"],
        waive_one_time=cd.get("waive_one_time_fee", False),
        gst_percent=cd["gst_percent"],
    )

    presentation = build_presentation(
        bundle_code=bundle_code,
        modules=modules,
        client_name=cd["client_name"],
    )

    from .proposal_catalog import (
        BEFORE_AFTER,
        BENEFITS,
        CUSTOM_PRESENTATION,
        FIVE_PILLARS,
        IMPLEMENTATION_COMPONENTS,
        NEXT_STEPS,
        PRESENTATIONS,
        SALUTATION,
        WHY_AVEON,
        WHY_NOW,
    )
    brand = CompanyBranding.from_profile(org_for(request.user)) if request.user.is_authenticated else CompanyBranding()
    logo_data_uri = _logo_data_uri(brand)

    pres = PRESENTATIONS.get(bundle_code or "", CUSTOM_PRESENTATION)
    exec_paragraphs = [
        p.format(client=cd["client_name"]) for p in pres.get("executive_paragraphs", [])
    ]

    return {
        "proposal_title": f"Aveon Proposal - {cd['client_name']}",
        "prepared_by": cd["prepared_by"],
        "proposal_date": cd["proposal_date"],
        "to_address": cd["to_address"],
        "client_name": cd["client_name"],
        "client_address_lines": _split_address_lines(cd["client_address"]),
        "minimum_student_commitment": cd["minimum_student_commitment"],
        "modules": modules,
        "bundle": BUNDLES.get(bundle_code) if bundle_code else None,
        "pricing": pricing,
        "hero": presentation["hero"],
        "hero_stats": presentation["hero_stats"],
        "executive_title": pres.get("executive_title", "Executive Summary"),
        "executive_paragraphs": exec_paragraphs,
        "modules_section_title": pres.get("modules_section_title", f"{len(modules)} Integrated Modules"),
        "modules_section_desc": pres.get("modules_section_desc", "Every capability included in your proposal."),
        "five_pillars": FIVE_PILLARS,
        "benefits": BENEFITS,
        "implementation_components": IMPLEMENTATION_COMPONENTS,
        "why_aveon": WHY_AVEON,
        "why_now": WHY_NOW,
        "before_after": BEFORE_AFTER,
        "next_steps": NEXT_STEPS,
        "salutation": SALUTATION,
        "include_year1_cost": cd.get("include_year1_cost", True),
        "contact_phone": brand.phone,
        "contact_email": brand.email,
        "contact_website": brand.website,
        "logo_data_uri": logo_data_uri,
        "default_phases": DEFAULT_PHASES,
        "default_terms": DEFAULT_TERMS,
        "authorized_signatory_name": cd["authorized_signatory_name"],
        "authorized_signatory_designation": cd["authorized_signatory_designation"],
        "jurisdiction": cd.get("jurisdiction") or "",
    }


def _render_proposal_html(ctx: dict, request: HttpRequest) -> str:
    from django.template.loader import render_to_string
    return render_to_string("payslip/proposals/base.html", ctx, request=request)


def _proposal_form_snapshot(cleaned_data: dict) -> dict:
    """JSON-safe copy of the validated form for the history record.

    Dates and Decimals become strings; the uploaded client_logo is dropped
    (binary, not restorable through a prefill).
    """
    snapshot = {}
    for key, value in cleaned_data.items():
        if key == "client_logo":
            continue
        if isinstance(value, (list, tuple)):
            snapshot[key] = list(value)
        elif value is None or isinstance(value, (str, int, bool)):
            snapshot[key] = value
        else:
            snapshot[key] = str(value)
    return snapshot


def _record_proposal(request: HttpRequest, form, ctx: dict, html: str):
    """Persist this generation in the org's proposal history."""
    from .models import ProposalRecord, next_proposal_revision

    client_name = form.cleaned_data["client_name"].strip()
    bundle = ctx.get("bundle")
    selection_label = (bundle["name"] if bundle
                       else f"Custom ({len(ctx.get('modules') or [])} modules)")
    return ProposalRecord.objects.create(
        organization=request.organization,
        created_by=request.user,
        client_name=client_name,
        revision=next_proposal_revision(request.organization, client_name),
        form_data=_proposal_form_snapshot(form.cleaned_data),
        html=html,
        selection_label=selection_label,
        total_amount=ctx["pricing"]["grand_total"],
    )


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


def _revise_initial(record) -> dict:
    """Turn a history record's form snapshot back into form initials."""
    import datetime
    initial = dict(record.form_data)
    raw_date = initial.get("proposal_date")
    if raw_date:
        try:
            initial["proposal_date"] = datetime.date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            initial.pop("proposal_date", None)
    return initial


@module_required("proposals")
def proposal_quotation(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        # ?from=<pk> - revise a proposal from history: prefill the builder.
        initial = None
        source = request.GET.get("from")
        if source and source.isdigit():
            from .models import ProposalRecord
            from django.shortcuts import get_object_or_404
            record = get_object_or_404(ProposalRecord, pk=int(source),
                                       organization=request.organization)
            initial = _revise_initial(record)
        form = ProposalQuotationForm(user=request.user, initial=initial)
        context = _proposal_form_context(form)
        context["revising"] = bool(initial)
        return render(request, "payslip/proposal_quotation.html", context)

    form = ProposalQuotationForm(request.POST, request.FILES, user=request.user)
    if not form.is_valid():
        return render(request, "payslip/proposal_quotation.html", _proposal_form_context(form))
    context = _proposal_form_context(form)

    proposal_ctx = _build_proposal_context(form, request)
    html = _render_proposal_html(proposal_ctx, request)
    record = _record_proposal(request, form, proposal_ctx, html)
    context["history_record"] = record
    safe_client = re.sub(r"[^A-Za-z0-9_\-]+", "_", form.cleaned_data["client_name"]).strip("_") or "client"
    html_filename = f"aveon_proposal_{safe_client}.html"

    # Preview always serves the HTML — pixel-perfect in any browser.
    preview_token = _save_content(request.user, html.encode("utf-8"), "text/html; charset=utf-8", html_filename)
    context["preview_url"] = reverse("preview_pdf", kwargs={"token": preview_token})

    # Download prefers PDF when WeasyPrint is installed; HTML otherwise.
    pdf = _try_html_to_pdf(html)
    if pdf:
        pdf_filename = f"aveon_proposal_{safe_client}.pdf"
        download_token = _save_content(request.user, pdf, "application/pdf", pdf_filename)
        context["download_url"] = reverse("download_file", kwargs={"token": download_token})
        context["download_label"] = "Download PDF"
        context["download_filename"] = pdf_filename
    else:
        download_token = _save_content(request.user, html.encode("utf-8"), "text/html; charset=utf-8", html_filename)
        context["download_url"] = reverse("download_file", kwargs={"token": download_token})
        context["download_label"] = "Download HTML (Print to PDF from browser)"
        context["download_filename"] = html_filename

    context["form"] = form
    return render(request, "payslip/proposal_quotation.html", context)


@module_required("proposals")
@require_GET
def cms_feature_list(request: HttpRequest) -> HttpResponse:
    """Print-ready CMS ERP product specifications document.

    Renders the complete Product Features & Functional Specifications
    (Version 2026) verbatim from cms_spec.py - 16 chapters, every module's
    full 9-part spec - for demos, tenders and RFP responses.
    """
    from .cms_spec import CMS_SPEC

    brand = CompanyBranding.from_profile(org_for(request.user))
    context = {
        "spec": CMS_SPEC,
        "logo_data_uri": _logo_data_uri(brand),
        "contact_phone": brand.phone,
        "contact_email": brand.email,
        "contact_website": brand.website,
    }
    response = render(request, "payslip/proposals/feature_list.html", context)
    if request.GET.get("download"):
        response["Content-Disposition"] = (
            'attachment; filename="Aveon_CMS_ERP_Product_Specifications_v2026.html"'
        )
    return response
