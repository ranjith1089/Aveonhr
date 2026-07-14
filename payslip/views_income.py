"""Staff-only Aveon Income module views - the client payment follow-up sheet."""
from __future__ import annotations

from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms_income import (
    ClientBillingForm,
    IncomeClientForm,
    IncomeImportForm,
    PaymentReceiptForm,
)
from .models import ClientBilling, IncomeClient, PaymentReceipt


def income_required(view):
    """Login redirect for anonymous users; 403 for non-staff.

    Not staff_member_required - that redirects to the admin login page
    instead of the app's own login.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            return HttpResponseForbidden("The Income module is restricted to staff users.")
        return view(request, *args, **kwargs)
    return wrapper


def _annotated_billings():
    return (
        ClientBilling.objects.select_related("client")
        .annotate(received_sum=Coalesce(
            Sum("payments__amount"), Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )


@income_required
def income_dashboard(request: HttpRequest) -> HttpResponse:
    billings = list(_annotated_billings())
    today = timezone.localdate()

    fy_totals: dict[str, Decimal] = {}
    engineer_rows: dict[str, dict] = {}
    grand_total = Decimal("0")
    for b in billings:
        outstanding = b.total_due - b.received_sum
        fy_totals[b.academic_year] = fy_totals.get(b.academic_year, Decimal("0")) + outstanding
        grand_total += outstanding
        if b.engineer:
            row = engineer_rows.setdefault(
                b.engineer, {"engineer": b.engineer, "clients": set(), "outstanding": Decimal("0")}
            )
            row["clients"].add(b.client_id)
            row["outstanding"] += outstanding

    engineer_table = sorted(
        ({"engineer": r["engineer"], "client_count": len(r["clients"]), "outstanding": r["outstanding"]}
         for r in engineer_rows.values()),
        key=lambda r: r["outstanding"], reverse=True,
    )
    followups = [b for b in billings if b.next_followup_date and b.next_followup_date <= today]
    followups.sort(key=lambda b: b.next_followup_date)
    waiting = [b for b in billings if b.invoice_status == ClientBilling.InvoiceStatus.WAITING]
    recent_payments = (
        PaymentReceipt.objects.select_related("billing__client").order_by("-created_at")[:10]
    )

    return render(request, "payslip/income/dashboard.html", {
        "fy_totals": sorted(fy_totals.items(), key=lambda kv: kv[0]),
        "grand_total": grand_total,
        "engineer_table": engineer_table,
        "followups": followups,
        "waiting": waiting,
        "recent_payments": recent_payments,
        "client_count": IncomeClient.objects.filter(is_active=True).count(),
        "today": today,
    })


@income_required
def income_client_list(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    clients = IncomeClient.objects.prefetch_related("billings__payments").all()
    if q:
        clients = clients.filter(name__icontains=q)
    return render(request, "payslip/income/client_list.html", {"clients": clients, "q": q})


@income_required
def income_client_create(request: HttpRequest) -> HttpResponse:
    form = IncomeClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client '{client.name}' created.")
        return redirect("income_client_detail", pk=client.pk)
    return render(request, "payslip/income/client_form.html",
                  {"form": form, "heading": "Add Client"})


@income_required
def income_client_edit(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(IncomeClient, pk=pk)
    form = IncomeClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client updated.")
        return redirect("income_client_detail", pk=client.pk)
    return render(request, "payslip/income/client_form.html",
                  {"form": form, "heading": f"Edit {client.name}", "client": client})


@income_required
def income_client_detail(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(IncomeClient.objects.prefetch_related("billings__payments"), pk=pk)
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
        rows.append({"b": b, "mismatch": mismatch, "prior_balance": prev_balance,
                     "payment_form": PaymentReceiptForm()})
        prev_balance = b.balance
    return render(request, "payslip/income/client_detail.html",
                  {"client": client, "rows": rows})


@income_required
def income_billing_create(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(IncomeClient, pk=pk)
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
    form = ClientBillingForm(request.POST or None, initial=initial)
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
    return render(request, "payslip/income/billing_form.html",
                  {"form": form, "heading": f"Add year - {client.name}", "client": client})


@income_required
def income_billing_edit(request: HttpRequest, pk: int) -> HttpResponse:
    billing = get_object_or_404(ClientBilling.objects.select_related("client"), pk=pk)
    form = ClientBillingForm(request.POST or None, instance=billing)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{billing.academic_year} updated.")
        return redirect("income_client_detail", pk=billing.client_id)
    return render(request, "payslip/income/billing_form.html",
                  {"form": form, "heading": f"Edit {billing.client.name} {billing.academic_year}",
                   "client": billing.client})


@income_required
@require_POST
def income_payment_add(request: HttpRequest, pk: int) -> HttpResponse:
    billing = get_object_or_404(ClientBilling.objects.select_related("client"), pk=pk)
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


@income_required
@require_POST
def income_payment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(PaymentReceipt.objects.select_related("billing__client"), pk=pk)
    client_pk = payment.billing.client_id
    payment.delete()
    messages.success(request, "Payment entry deleted.")
    return redirect("income_client_detail", pk=client_pk)


@income_required
@require_GET
def income_export(request: HttpRequest) -> HttpResponse:
    from .services.income_export import build_income_workbook
    data = build_income_workbook()
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="aveon-income-{timezone.localdate():%Y-%m-%d}.xlsx"'
    )
    return resp


@income_required
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
                applied = apply_import(result)
                messages.success(
                    request,
                    f"Import complete: {applied['clients_created']} clients created, "
                    f"{applied['billings_created']} billing rows created, "
                    f"{applied['skipped']} skipped (already exist).",
                )
                return redirect("income_dashboard")
    return render(request, "payslip/income/import.html",
                  {"form": form, "result": result})
