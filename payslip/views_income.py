"""Aveon Income module views - the client payment follow-up sheet.

Org-scoped: every query filters by request.organization (set by
module_required), so each organization only ever sees its own ledger.
Cross-org object access 404s via the organization filter in get_object_or_404.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .decorators import module_required
from .forms_income import (
    AcademicYearForm,
    ClientBillingForm,
    IncomeClientForm,
    IncomeImportForm,
    PaymentReceiptForm,
)
from .models import AcademicYear, ClientBilling, IncomeClient, PaymentReceipt


def _engineer_names(org) -> list[str]:
    """Known engineers + any new names already typed into billing rows."""
    from .models import ENGINEER_CHOICES
    base = {e[0] for e in ENGINEER_CHOICES}
    used = set(
        ClientBilling.objects.filter(client__organization=org).exclude(engineer="")
        .values_list("engineer", flat=True).distinct()
    )
    return sorted(base | used)


def _annotated_billings(org):
    return (
        ClientBilling.objects.filter(client__organization=org)
        .select_related("client")
        .annotate(received_sum=Coalesce(
            Sum("payments__amount"), Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )


@module_required("income")
def income_dashboard(request: HttpRequest) -> HttpResponse:
    from .services.income_analytics import build_analytics

    org = request.organization
    billings = list(_annotated_billings(org))
    today = timezone.localdate()
    analytics = build_analytics(org)

    followups = [b for b in billings if b.next_followup_date and b.next_followup_date <= today]
    followups.sort(key=lambda b: b.next_followup_date)
    waiting = [b for b in billings if b.invoice_status == ClientBilling.InvoiceStatus.WAITING]
    recent_payments = (
        PaymentReceipt.objects.filter(billing__client__organization=org)
        .select_related("billing__client").order_by("-created_at")[:8]
    )

    top_clients = [r for r in analytics["client_outstanding"] if r["balance"] > 0][:8]

    # Implementation alerts: agreement expiry + missing POs (one cheap query).
    from .models import ClientOnboarding
    expiring_count = 0
    po_pending_count = IncomeClient.objects.filter(
        organization=org, is_active=True
    ).exclude(onboarding__po_received=True).count()
    for o in ClientOnboarding.objects.filter(client__organization=org,
                                             agreement_signed=True,
                                             agreement_end__isnull=False):
        if o.agreement_expired or o.agreement_expiring:
            expiring_count += 1

    fy_chart = {
        "labels": [r["year"] for r in analytics["fy_rows"]],
        "billed": [float(r["billed"]) for r in analytics["fy_rows"]],
        "received": [float(r["received"]) for r in analytics["fy_rows"]],
        "outstanding": [float(r["outstanding"]) for r in analytics["fy_rows"]],
    }

    return render(request, "payslip/income/dashboard.html", {
        "fy_rows": analytics["fy_rows"],
        "grand_total": analytics["grand_outstanding"],
        "engineer_table": analytics["engineer_rows"],
        "top_clients": top_clients,
        "fy_chart": fy_chart,
        "followups": followups,
        "waiting": waiting,
        "recent_payments": recent_payments,
        "client_count": IncomeClient.objects.filter(organization=org, is_active=True).count(),
        "expiring_count": expiring_count,
        "po_pending_count": po_pending_count,
        "today": today,
    })


@module_required("income")
def income_analytics(request: HttpRequest) -> HttpResponse:
    from .services.income_analytics import build_analytics, build_forecast

    org = request.organization
    analytics = build_analytics(org)
    forecast = build_forecast(org)

    charts = {
        "fy": {
            "labels": [r["year"] for r in analytics["fy_rows"]],
            "billed": [float(r["billed"]) for r in analytics["fy_rows"]],
            "received": [float(r["received"]) for r in analytics["fy_rows"]],
            "outstanding": [float(r["outstanding"]) for r in analytics["fy_rows"]],
        },
        "clients": {
            "labels": [r["name"] for r in analytics["client_outstanding"] if r["balance"] > 0][:10],
            "balances": [float(r["balance"]) for r in analytics["client_outstanding"] if r["balance"] > 0][:10],
        },
        "engineers": {
            "labels": [r["engineer"] for r in analytics["engineer_rows"]],
            "outstanding": [float(r["outstanding"]) for r in analytics["engineer_rows"]],
        },
        "monthly": {
            "labels": [m["month"] for m in analytics["monthly_trend"]],
            "amounts": [float(m["amount"]) for m in analytics["monthly_trend"]],
        },
        "forecast": {
            "labels": [f"Current {forecast['current_year']}", "Conservative", "Growth-adjusted"],
            "values": [float(forecast["current_billed"]),
                       float(forecast["conservative_total"]),
                       float(forecast["growth_total"])],
        },
    }

    return render(request, "payslip/income/analytics.html", {
        "analytics": analytics,
        "forecast": forecast,
        "charts": charts,
    })


@module_required("income")
def income_client_list(request: HttpRequest) -> HttpResponse:
    org = request.organization
    q = (request.GET.get("q") or "").strip()
    engineer = (request.GET.get("engineer") or "").strip()
    show = (request.GET.get("show") or "all").strip()  # all | balance
    sort = (request.GET.get("sort") or "balance").strip()  # balance | name

    clients = list(IncomeClient.objects.filter(organization=org)
                   .prefetch_related("billings__payments"))
    if q:
        clients = [c for c in clients if q.lower() in c.name.lower()]
    if engineer:
        clients = [c for c in clients if any(b.engineer == engineer for b in c.billings.all())]
    if show == "balance":
        clients = [c for c in clients if c.total_balance > 0]

    def _row(c):
        billed = sum((b.total_due for b in c.billings.all()), Decimal("0"))
        received = sum((b.received_total for b in c.billings.all()), Decimal("0"))
        balance = billed - received
        pct = int(min(max(received / billed * 100, Decimal("0")), Decimal("100"))) if billed > 0 else 0
        return {"c": c, "billed": billed, "received": received,
                "balance": balance, "collection_pct": pct}

    # Split into active vs inactive (discontinued) - two separate sections.
    active_rows, inactive_rows = [], []
    for c in clients:
        (active_rows if c.is_active else inactive_rows).append(_row(c))

    def _totals(rows):
        return {
            "billed": sum((r["billed"] for r in rows), Decimal("0")),
            "received": sum((r["received"] for r in rows), Decimal("0")),
            "balance": sum((r["balance"] for r in rows), Decimal("0")),
        }

    key = (lambda r: r["c"].name.lower()) if sort == "name" else (lambda r: r["balance"])
    reverse = sort != "name"
    active_rows.sort(key=key, reverse=reverse)
    inactive_rows.sort(key=key, reverse=reverse)

    return render(request, "payslip/income/client_list.html", {
        "active_rows": active_rows, "inactive_rows": inactive_rows,
        "total_count": len(active_rows) + len(inactive_rows),
        "active_totals": _totals(active_rows), "inactive_totals": _totals(inactive_rows),
        "q": q, "engineer": engineer, "show": show, "sort": sort,
        "engineers": _engineer_names(org),
    })


@module_required("income")
@require_POST
def income_client_update_engineer(request: HttpRequest, pk: int) -> JsonResponse:
    org = request.organization
    client = get_object_or_404(IncomeClient, pk=pk, organization=org)
    latest = max(client.billings.all(), key=lambda b: b.year_start, default=None)
    if not latest:
        return JsonResponse({"error": "No billing year exists for this client."}, status=400)
    engineer = (request.POST.get("engineer") or "").strip()
    latest.engineer = engineer
    latest.save(update_fields=["engineer", "updated_at"])
    return JsonResponse({"ok": True, "engineer": engineer})


@module_required("income")
def income_client_create(request: HttpRequest) -> HttpResponse:
    org = request.organization
    form = IncomeClientForm(request.POST or None, organization=org)
    if request.method == "POST" and form.is_valid():
        client = form.save(commit=False)
        client.organization = org
        client.save()
        messages.success(request, f"Client '{client.name}' created.")
        return redirect("income_client_detail", pk=client.pk)
    return render(request, "payslip/income/client_form.html",
                  {"form": form, "heading": "Add Client"})


@module_required("income")
def income_client_edit(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    client = get_object_or_404(IncomeClient, pk=pk, organization=org)
    form = IncomeClientForm(request.POST or None, instance=client, organization=org)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client updated.")
        return redirect("income_client_detail", pk=client.pk)
    return render(request, "payslip/income/client_form.html",
                  {"form": form, "heading": f"Edit {client.name}", "client": client})


@module_required("income")
@require_POST
def income_client_toggle_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Quick toggle of a client's active/discontinued status from the list."""
    client = get_object_or_404(IncomeClient, pk=pk, organization=request.organization)
    client.is_active = not client.is_active
    client.save(update_fields=["is_active"])
    if client.is_active:
        messages.success(request, f"'{client.name}' marked active.")
    else:
        messages.success(request, f"'{client.name}' marked inactive (discontinued).")
    return redirect("income_client_list")


@module_required("income")
def income_client_detail(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(
        IncomeClient.objects.prefetch_related("billings__payments"),
        pk=pk, organization=request.organization,
    )
    billings = sorted(client.billings.all(), key=lambda b: b.year_start)
    # Carry-forward mismatch badge: previous_pending vs prior year's balance.
    rows = []
    prev_balance = None
    for b in billings:
        mismatch = (
            prev_balance is not None
            and b.previous_pending is not None
            and abs(b.previous_pending - prev_balance) > Decimal("1")
        )
        received = b.received_total
        pct = int(min(max(received / b.total_due * 100, Decimal("0")), Decimal("100"))) if b.total_due > 0 else 0
        rows.append({"b": b, "mismatch": mismatch, "prior_balance": prev_balance,
                     "payment_form": PaymentReceiptForm(), "received": received,
                     "collection_pct": pct})
        prev_balance = b.balance
    total_billed = sum((b.total_due for b in billings), Decimal("0"))
    total_received = sum((r["received"] for r in rows), Decimal("0"))
    return render(request, "payslip/income/client_detail.html", {
        "client": client, "rows": rows,
        "total_billed": total_billed, "total_received": total_received,
        "total_balance": total_billed - total_received,
    })


@module_required("income")
def income_billing_create(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    client = get_object_or_404(IncomeClient, pk=pk, organization=org)
    initial = {}
    latest = max(client.billings.all(), key=lambda b: b.year_start, default=None)
    if latest:
        initial = {
            "academic_year": f"{latest.year_start + 1}-{latest.year_start + 2}",
            "engineer": latest.engineer,
            "student_count": latest.student_count,
            "rate": latest.rate,
            "previous_pending": latest.balance,  # prefill only - stays editable
        }
    form = ClientBillingForm(request.POST or None, initial=initial, organization=org)
    if request.method == "POST" and form.is_valid():
        billing = form.save(commit=False)
        billing.client = client
        try:
            billing.save()
        except Exception:
            form.add_error("academic_year", "This client already has a row for that year.")
        else:
            messages.success(request, f"{billing.academic_year} added for {client.name}.")
            return redirect("income_client_detail", pk=client.pk)
    year_options = sorted(
        AcademicYear.objects.filter(organization=org).values_list("label", flat=True),
        reverse=True
    )
    return render(request, "payslip/income/billing_form.html",
                  {"form": form, "heading": f"Add year - {client.name}", "client": client,
                   "year_options": year_options, "engineer_options": _engineer_names(org)})


@module_required("income")
def income_billing_edit(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    billing = get_object_or_404(
        ClientBilling.objects.select_related("client"),
        pk=pk, client__organization=org,
    )
    form = ClientBillingForm(request.POST or None, instance=billing, organization=org)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{billing.academic_year} updated.")
        return redirect("income_client_detail", pk=billing.client_id)
    year_options = sorted(
        AcademicYear.objects.filter(organization=org).values_list("label", flat=True),
        reverse=True
    )
    return render(request, "payslip/income/billing_form.html",
                  {"form": form, "heading": f"Edit {billing.client.name} {billing.academic_year}",
                   "client": billing.client, "year_options": year_options, "engineer_options": _engineer_names(org)})


@module_required("income")
@require_POST
def income_payment_add(request: HttpRequest, pk: int) -> HttpResponse:
    billing = get_object_or_404(
        ClientBilling.objects.select_related("client"),
        pk=pk, client__organization=request.organization,
    )
    form = PaymentReceiptForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.billing = billing
        payment.save()
        messages.success(request, f"Payment of Rs.{payment.amount} recorded for "
                                  f"{billing.client.name} {billing.academic_year}.")
    else:
        messages.error(request, "Payment not saved: " +
                       "; ".join(f"{f}: {e[0]}" for f, e in form.errors.items()))
    return redirect("income_client_detail", pk=billing.client_id)


@module_required("income")
@require_POST
def income_payment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        PaymentReceipt.objects.select_related("billing__client"),
        pk=pk, billing__client__organization=request.organization,
    )
    client_pk = payment.billing.client_id
    payment.delete()
    messages.success(request, "Payment entry deleted.")
    return redirect("income_client_detail", pk=client_pk)


@module_required("income")
@require_GET
def income_export(request: HttpRequest) -> HttpResponse:
    from .services.income_export import build_income_workbook
    data = build_income_workbook(request.organization)
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="aveon-income-{timezone.localdate():%Y-%m-%d}.xlsx"'
    )
    return resp


@module_required("income")
def income_import(request: HttpRequest) -> HttpResponse:
    from .services.income_import import apply_import, parse_income_workbook
    result = None
    applied = None
    form = IncomeImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = parse_income_workbook(form.cleaned_data["file"])
        except Exception as exc:
            form.add_error("file", f"Could not read the workbook: {exc}")
        else:
            if not form.cleaned_data.get("dry_run"):
                applied = apply_import(result, request.organization)
                messages.success(
                    request,
                    f"Import complete: {applied['clients_created']} clients created, "
                    f"{applied['billings_created']} billing rows created, "
                    f"{applied['skipped']} skipped (already exist).",
                )
                return redirect("income_dashboard")
    return render(request, "payslip/income/import.html",
                  {"form": form, "result": result})


# ---------------------------------------------------------------------------
# Academic Years
# ---------------------------------------------------------------------------
@module_required("income")
def academic_year_list(request: HttpRequest) -> HttpResponse:
    org = request.organization

    if not AcademicYear.objects.filter(organization=org).exists():
        existing = (
            ClientBilling.objects.filter(client__organization=org)
            .values_list("academic_year", flat=True)
            .distinct()
        )
        created = 0
        for label in existing:
            AcademicYear.objects.get_or_create(
                organization=org, label=label, defaults={"is_active": True}
            )
            created += 1
        if created:
            messages.info(request, f"Auto-imported {created} academic year(s) from existing billings.")

    form = AcademicYearForm(organization=org)

    if request.method == "POST":
        action = request.POST.get("action", "add")

        if action == "toggle":
            pk = request.POST.get("pk")
            year = get_object_or_404(AcademicYear, pk=pk, organization=org)
            year.is_active = not year.is_active
            year.save(update_fields=["is_active"])
            label = "activated" if year.is_active else "deactivated"
            messages.success(request, f"{year.label} {label}.")
            return redirect("academic_year_list")

        form = AcademicYearForm(request.POST, organization=org)
        if form.is_valid():
            year = form.save(commit=False)
            year.organization = org
            year.save()
            messages.success(request, f"Academic year {year.label} added.")
            return redirect("academic_year_list")

    years = AcademicYear.objects.filter(organization=org)
    return render(request, "payslip/income/academic_years.html", {
        "years": years,
        "form": form,
    })
