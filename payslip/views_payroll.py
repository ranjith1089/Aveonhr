"""Payroll module - employee master, monthly attendance-driven salary runs,
and generated payslips. Org-scoped throughout; cross-org access 404s.
"""
from __future__ import annotations

import calendar
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .decorators import module_required, org_admin_required
from .forms_payroll import EmployeeForm, PayrollSettingsForm, PayrollRunCreateForm
from .models import Employee, PayrollRun, PayrollSettings, PayslipEntry, payroll_settings_for
from .services.payroll_calc import apply_computation, compute_entry


def _decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value or default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _recompute(entry: PayslipEntry, settings: PayrollSettings) -> None:
    computation = compute_entry(
        monthly_package=entry.monthly_package,
        total_working_days=entry.total_working_days,
        emp_leave_days=entry.emp_leave_days,
        lop_days=entry.lop_days,
        internet_allowance=entry.internet_allowance,
        salary_arrear_allowance=entry.salary_arrear_allowance,
        salary_advance=entry.salary_advance,
        tds=entry.tds,
        is_esi_eligible=entry.is_esi_eligible,
        is_pf_applicable=entry.is_pf_applicable,
        settings=settings,
    )
    apply_computation(entry, computation)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@org_admin_required
def payroll_settings(request: HttpRequest) -> HttpResponse:
    settings_obj = payroll_settings_for(request.organization)
    if request.method == "POST":
        form = PayrollSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Payroll settings saved.")
            return redirect("payroll_settings")
    else:
        form = PayrollSettingsForm(instance=settings_obj)
    return render(request, "payslip/payroll/settings.html", {"form": form})


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
@module_required("payroll")
def employee_list(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    employees = Employee.objects.filter(organization=request.organization)
    if q:
        employees = employees.filter(name__icontains=q)
    employees = list(employees)
    return render(request, "payslip/payroll/employee_list.html", {
        "employees": employees,
        "q": q,
        "active_count": sum(1 for e in employees if e.is_active),
    })


def _next_employee_code(org) -> str:
    n = Employee.objects.filter(organization=org).count() + 1
    while Employee.objects.filter(organization=org, employee_code=f"EMP-{n:04d}").exists():
        n += 1
    return f"EMP-{n:04d}"


@module_required("payroll")
def employee_create(request: HttpRequest) -> HttpResponse:
    org = request.organization
    initial = {"employee_code": _next_employee_code(org)}
    form = EmployeeForm(request.POST or None, organization=org, initial=initial)
    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.organization = org
        employee.created_by = request.user
        employee.save()
        messages.success(request, f"Added {employee.name}.")
        return redirect("employee_detail", pk=employee.pk)
    return render(request, "payslip/payroll/employee_detail.html", {
        "employee": None, "form": form, "heading": "Add Employee", "entries": [],
    })


@module_required("payroll")
def employee_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    employee = get_object_or_404(Employee, pk=pk, organization=org)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_employee":
            form = EmployeeForm(request.POST, instance=employee, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, "Employee details saved.")
                return redirect("employee_detail", pk=pk)
            messages.error(request, "Please fix the errors below.")
        else:
            form = EmployeeForm(instance=employee, organization=org)

        if action == "deactivate_employee":
            employee.is_active = False
            employee.save(update_fields=["is_active"])
            messages.success(request, f"{employee.name} deactivated.")
            return redirect("employee_detail", pk=pk)

        if action == "reactivate_employee":
            employee.is_active = True
            employee.save(update_fields=["is_active"])
            messages.success(request, f"{employee.name} reactivated.")
            return redirect("employee_detail", pk=pk)
    else:
        form = EmployeeForm(instance=employee, organization=org)

    entries = list(
        employee.payslip_entries.select_related("run").order_by("-run__period")
    )
    return render(request, "payslip/payroll/employee_detail.html", {
        "employee": employee, "form": form, "heading": employee.name, "entries": entries,
    })


# ---------------------------------------------------------------------------
# Payroll runs
# ---------------------------------------------------------------------------
def _suggest_lop_days(employee: Employee, period) -> Decimal:
    """Smart default only - always editable. Mirrors the source sheet's
    manual convention: no automatic proration beyond LOP entry."""
    days_in_month = calendar.monthrange(period.year, period.month)[1]
    lop = Decimal("0")
    if employee.doj and employee.doj.year == period.year and employee.doj.month == period.month:
        lop += Decimal(employee.doj.day - 1)
    if (employee.relieving_date and employee.relieving_date.year == period.year
            and employee.relieving_date.month == period.month):
        lop += Decimal(days_in_month - employee.relieving_date.day)
    return lop


@module_required("payroll")
def payroll_run_list(request: HttpRequest) -> HttpResponse:
    runs = list(PayrollRun.objects.filter(organization=request.organization))
    form = PayrollRunCreateForm(initial={"period": timezone.localdate().replace(day=1)})
    return render(request, "payslip/payroll/run_list.html", {"runs": runs, "form": form})


@module_required("payroll")
def payroll_run_create(request: HttpRequest) -> HttpResponse:
    org = request.organization
    form = PayrollRunCreateForm(request.POST or None)
    if request.method != "POST" or not form.is_valid():
        messages.error(request, "Pick a valid month.")
        return redirect("payroll_run_list")

    period = form.cleaned_data["period"].replace(day=1)
    run, created = PayrollRun.objects.get_or_create(
        organization=org, period=period, defaults={"created_by": request.user}
    )
    if created:
        settings_obj = payroll_settings_for(org)
        days_in_month = calendar.monthrange(period.year, period.month)[1]
        active = Employee.objects.filter(organization=org, is_active=True)
        new_entries = []
        for employee in active:
            lop = _suggest_lop_days(employee, period)
            entry = PayslipEntry(
                organization=org, run=run, employee=employee,
                monthly_package=employee.current_monthly_package,
                total_working_days=days_in_month,
                lop_days=lop,
                is_esi_eligible=employee.is_esi_eligible,
                is_pf_applicable=employee.is_pf_applicable,
            )
            _recompute(entry, settings_obj)
            new_entries.append(entry)
        PayslipEntry.objects.bulk_create(new_entries)
        messages.success(request, f"Payroll run created for {period:%B %Y} "
                                  f"({len(new_entries)} employees).")
    return redirect("payroll_run_detail", pk=run.pk)


@module_required("payroll")
def payroll_run_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)
    settings_obj = payroll_settings_for(org)

    if request.method == "POST" and not run.is_finalized:
        action = request.POST.get("action", "")
        if action == "save_grid":
            entries = list(run.entries.select_related("employee"))
            with transaction.atomic():
                for entry in entries:
                    pk_str = str(entry.pk)
                    entry.total_working_days = int(
                        request.POST.get(f"twd_{pk_str}") or entry.total_working_days)
                    entry.cl_credit = _decimal(request.POST.get(f"cl_{pk_str}"))
                    entry.emp_leave_days = _decimal(request.POST.get(f"empleave_{pk_str}"))
                    entry.lop_days = _decimal(request.POST.get(f"lop_{pk_str}"))
                    entry.internet_allowance = _decimal(request.POST.get(f"internet_{pk_str}"))
                    entry.salary_arrear_allowance = _decimal(request.POST.get(f"arrear_{pk_str}"))
                    entry.salary_advance = _decimal(request.POST.get(f"advance_{pk_str}"))
                    entry.tds = _decimal(request.POST.get(f"tds_{pk_str}"))
                    entry.remarks = (request.POST.get(f"remarks_{pk_str}") or "").strip()
                    _recompute(entry, settings_obj)
                PayslipEntry.objects.bulk_update(entries, [
                    "total_working_days", "cl_credit", "emp_leave_days", "lop_days",
                    "internet_allowance", "salary_arrear_allowance", "salary_advance",
                    "tds", "remarks", "present_days", "pay_days", "basic", "da", "hra",
                    "transport_allowance", "food_allowance", "gross_salary",
                    "esi_employee", "esi_employer", "pf_employee", "pf_employer",
                    "total_deductions", "net_payable",
                ])
            messages.success(request, "Payroll grid saved and recomputed.")
            return redirect("payroll_run_detail", pk=pk)

    entries = list(run.entries.select_related("employee"))
    negative_count = sum(1 for e in entries if e.net_payable < 0)
    totals = {
        "gross": sum((e.gross_salary for e in entries), Decimal("0")),
        "deductions": sum((e.total_deductions for e in entries), Decimal("0")),
        "net": sum((e.net_payable for e in entries), Decimal("0")),
    }
    missing_pdfs = sum(1 for e in entries if not e.pdf)
    return render(request, "payslip/payroll/run_detail.html", {
        "run": run, "entries": entries, "totals": totals,
        "negative_count": negative_count,
        "missing_pdfs": missing_pdfs,
        "comparison": _build_comparison(org, run, entries),
    })


def _build_comparison(org, run, entries) -> dict | None:
    """This run vs the previous month: totals, joiners/leavers, per-employee
    net-pay movement. Returns None when there's no earlier run to compare."""
    prev_run = (PayrollRun.objects
                .filter(organization=org, period__lt=run.period)
                .order_by("-period").first())
    if prev_run is None:
        return None

    prev_entries = list(prev_run.entries.select_related("employee"))
    prev_net = sum((e.net_payable for e in prev_entries), Decimal("0"))
    curr_net = sum((e.net_payable for e in entries), Decimal("0"))

    unmatched = {e.employee_id: e for e in prev_entries}
    rows, joiners = [], []
    for e in entries:
        prev = unmatched.pop(e.employee_id, None)
        if prev is None:
            joiners.append(e)
            continue
        delta = e.net_payable - prev.net_payable
        if delta:
            rows.append({"employee": e.employee, "prev": prev.net_payable,
                         "curr": e.net_payable, "delta": delta,
                         "lop_delta": e.lop_days - prev.lop_days})
    # Whatever is left was paid last month but has no row this month.
    leavers = sorted(unmatched.values(), key=lambda e: e.employee.name)
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)

    return {
        "prev_run": prev_run,
        "prev_net": prev_net, "curr_net": curr_net,
        "net_delta": curr_net - prev_net,
        "prev_headcount": len(prev_entries), "curr_headcount": len(entries),
        "rows": rows[:15], "more_rows": max(0, len(rows) - 15),
        "joiners": joiners, "leavers": leavers,
        "unchanged": len(entries) - len(joiners) - len(rows),
    }


def _build_pdfs(org, entries) -> None:
    """Render each entry's payslip PDF in place (caller saves)."""
    from .pdf_styles import CompanyBranding
    from .services.payroll_pdf import build_entry_pdf
    from .utils import CompanyInfo

    brand = CompanyBranding.from_profile(org)
    company = CompanyInfo(name=brand.name, address=brand.address or "",
                          email=brand.email, phone=brand.phone)
    logo_bytes = brand.logo_bytes
    for entry in entries:
        entry.pdf = build_entry_pdf(entry, company, logo_bytes)
        entry.pdf_generated_at = timezone.now()


@org_admin_required
def payroll_run_finalize(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)
    if request.method != "POST" or run.is_finalized:
        return redirect("payroll_run_detail", pk=pk)

    settings_obj = payroll_settings_for(org)
    entries = list(run.entries.select_related("employee"))
    for entry in entries:
        _recompute(entry, settings_obj)

    negative = [e for e in entries if e.net_payable < 0]
    if negative and request.POST.get("confirm_negative") != "1":
        names = ", ".join(e.employee.name for e in negative[:5])
        messages.error(
            request,
            f"{len(negative)} employee(s) have a negative net payable "
            f"({names}{'…' if len(negative) > 5 else ''}). Tick the confirmation "
            f"box to finalize anyway.",
        )
        return redirect("payroll_run_detail", pk=pk)

    with transaction.atomic():
        _build_pdfs(org, entries)
        PayslipEntry.objects.bulk_update(entries, [
            "present_days", "pay_days", "basic", "da", "hra", "transport_allowance",
            "food_allowance", "gross_salary", "esi_employee", "esi_employer",
            "pf_employee", "pf_employer", "total_deductions", "net_payable",
            "pdf", "pdf_generated_at",
        ])
        run.status = PayrollRun.Status.FINALIZED
        run.finalized_by = request.user
        run.finalized_at = timezone.now()
        run.save(update_fields=["status", "finalized_by", "finalized_at"])

    messages.success(request, f"Payroll finalized for {run.period:%B %Y} - "
                              f"{len(entries)} payslips generated.")
    return redirect("payroll_run_detail", pk=pk)


@org_admin_required
def payroll_run_reopen(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)
    if request.method != "POST" or not run.is_finalized:
        return redirect("payroll_run_detail", pk=pk)

    with transaction.atomic():
        run.entries.update(pdf=None, pdf_plain=None, pdf_generated_at=None)
        run.status = PayrollRun.Status.DRAFT
        # Imported historical runs land as FINALIZED with no finalized_at/by,
        # so both have to tolerate None here.
        was = (f"{run.finalized_at:%d %b %Y}" if run.finalized_at else "on import")
        note = (f"Reopened by {request.user.username} on "
               f"{timezone.localdate():%d %b %Y} (was finalized {was} by "
               f"{run.finalized_by.username if run.finalized_by else '—'}).")
        run.notes = f"{run.notes}\n{note}".strip()
        run.finalized_by = None
        run.finalized_at = None
        run.save(update_fields=["status", "notes", "finalized_by", "finalized_at"])
    messages.success(request, f"Payroll for {run.period:%B %Y} reopened for editing.")
    return redirect("payroll_run_detail", pk=pk)


@org_admin_required
def payroll_generate_payslips(request: HttpRequest, pk: int) -> HttpResponse:
    """Build payslip PDFs for an already-finalized run.

    Imported historical runs arrive finalized but with no PDFs, so this is
    the only way to get their payslips without reopening (which would
    discard the imported figures' finalized state). Existing PDFs are left
    alone unless ?regenerate=1 is posted.
    """
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)
    if request.method != "POST" or not run.is_finalized:
        return redirect("payroll_run_detail", pk=pk)

    entries = list(run.entries.select_related("employee"))
    if request.POST.get("regenerate") != "1":
        entries = [e for e in entries if not e.pdf]
    if not entries:
        messages.info(request, "Every payslip in this run has already been generated.")
        return redirect("payroll_run_detail", pk=pk)

    with transaction.atomic():
        _build_pdfs(org, entries)
        PayslipEntry.objects.bulk_update(entries, ["pdf", "pdf_generated_at"])

    messages.success(request, f"{len(entries)} payslip{'' if len(entries) == 1 else 's'} "
                              f"generated for {run.period:%B %Y}.")
    return redirect("payroll_run_detail", pk=pk)


@module_required("payroll")
def payroll_entry_pdf(request: HttpRequest, pk: int, action: str) -> HttpResponse:
    entry = get_object_or_404(
        PayslipEntry.objects.select_related("employee", "run"),
        pk=pk, organization=request.organization,
    )
    if not entry.pdf:
        messages.error(request, "This payslip hasn't been generated yet - "
                                "finalize the payroll run first.")
        return redirect("payroll_run_detail", pk=entry.run_id)

    from .views import _save_content
    filename = f"payslip_{entry.employee.employee_code}_{entry.run.period:%Y_%m}.pdf"
    token = _save_content(request.user, bytes(entry.pdf), "application/pdf", filename)
    if action == "download":
        return redirect(reverse("download_file", kwargs={"token": token}))
    return redirect(reverse("preview_pdf", kwargs={"token": token}))


@module_required("payroll")
def payroll_register_export(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(PayrollRun, pk=pk, organization=request.organization)
    from .services.payroll_export import build_payroll_register_workbook
    data = build_payroll_register_workbook(request.organization, run.period)
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = (
        f'attachment; filename="payroll-register-{run.period:%Y-%m}.xlsx"'
    )
    return resp
