"""Payroll module - employee master, monthly attendance-driven salary runs,
and generated payslips. Org-scoped throughout; cross-org access 404s.
"""
from __future__ import annotations

import calendar
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .decorators import module_required, org_admin_required
from .forms_payroll import (EXPORT_FIELD_GROUPS, EmployeeExportForm, EmployeeForm,
                            PayrollSettingsForm, PayrollRunCreateForm,
                            SalaryComponentForm)
from .models import (Employee, PayrollRun, PayslipEntry,
                     payroll_settings_for, salary_structure_for)
from .services.structure_calc import (apply_structure_computation,
                                      compute_entry_from_structure,
                                      save_component_amounts)

# Legacy PayslipEntry columns written by every recompute (kept in sync with
# the configurable engine's output + the new employer/CTC totals).
_COMPUTED_FIELDS = [
    "present_days", "pay_days", "basic", "da", "hra", "transport_allowance",
    "food_allowance", "gross_salary", "esi_employee", "esi_employer",
    "pf_employee", "pf_employer", "total_deductions", "net_payable",
    "employer_contributions", "ctc",
]


def _decimal(value, default="0") -> Decimal:
    try:
        return Decimal(str(value or default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _recompute(entry: PayslipEntry, structure):
    """Compute an entry via the configurable salary structure and copy the
    results onto its legacy columns. Returns the computation so the caller
    can persist the component breakdown (needs entry.pk) after saving."""
    computation = compute_entry_from_structure(
        structure,
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
    )
    apply_structure_computation(entry, computation)
    return computation


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
# Salary structure (configurable component master)
# ---------------------------------------------------------------------------
def _validate_structure(structure) -> str | None:
    """Return a human error if the whole component set can't be resolved
    (bad formula or circular reference), else None."""
    from .services.formula_engine import (FormulaError, component_dependencies,
                                          order_components, validate_formula)
    comps = list(structure.components.filter(is_active=True))
    codes = {c.code for c in comps}
    try:
        for c in comps:
            validate_formula(c.as_expression(), codes)
        order_components({c.code: component_dependencies(c.as_expression(), codes)
                          for c in comps})
    except FormulaError as exc:
        return str(exc)
    return None


@org_admin_required
def salary_structure(request: HttpRequest) -> HttpResponse:
    from .models import SalaryComponent, StructureChangeLog, salary_structure_for
    from .services.structure_seed import default_component_specs, build_components

    org = request.organization
    structure = salary_structure_for(org)  # seeds default on first use

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "reset_default":
            build_components(structure, default_component_specs(payroll_settings_for(org)))
            StructureChangeLog.objects.create(
                organization=org, structure=structure, user=request.user,
                action="Reset to default", detail="Rebuilt from payroll settings.")
            messages.success(request, "Structure reset to the default components.")
            return redirect("salary_structure")

        if action == "delete_component":
            comp = get_object_or_404(SalaryComponent, pk=request.POST.get("component_id"),
                                     structure=structure)
            code = comp.code
            comp.delete()
            err = _validate_structure(structure)
            if err:  # deleting broke a dependency - put it back
                transaction.set_rollback(True)
            StructureChangeLog.objects.create(
                organization=org, structure=structure, user=request.user,
                action="Delete component", detail=code)
            messages.success(request, f"Removed component {code}.")
            return redirect("salary_structure")

        if action == "save_component":
            comp_id = request.POST.get("component_id")
            instance = (get_object_or_404(SalaryComponent, pk=comp_id, structure=structure)
                        if comp_id else SalaryComponent(structure=structure))
            siblings = set(structure.components.exclude(pk=instance.pk or 0)
                           .values_list("code", flat=True))
            form = SalaryComponentForm(request.POST, instance=instance, sibling_codes=siblings)
            if form.is_valid():
                with transaction.atomic():
                    comp = form.save()
                    err = _validate_structure(structure)
                    if err:
                        transaction.set_rollback(True)
                        messages.error(request, f"Not saved - {err}")
                        return redirect("salary_structure")
                StructureChangeLog.objects.create(
                    organization=org, structure=structure, user=request.user,
                    action=("Edit component" if comp_id else "Add component"),
                    detail=f"{comp.code}: {comp.as_expression()}")
                messages.success(request, f"Saved component {comp.code}.")
                return redirect("salary_structure")
            messages.error(request, "Please fix the errors in the component form.")
        else:
            form = SalaryComponentForm()
    else:
        edit_id = request.GET.get("edit")
        editing = (SalaryComponent.objects.filter(pk=edit_id, structure=structure).first()
                   if edit_id else None)
        form = SalaryComponentForm(instance=editing) if editing else SalaryComponentForm()

    components = list(structure.components.all())
    warning = _validate_structure(structure)
    return render(request, "payslip/payroll/structure_edit.html", {
        "structure": structure, "components": components, "form": form,
        "warning": warning,
        "context_vars": sorted(__import__("payslip.services.formula_engine",
                                          fromlist=["CONTEXT_VARS"]).CONTEXT_VARS),
        "change_logs": structure.change_logs.select_related("user")[:10],
        "kinds": SalaryComponent.Kind.choices,
        "methods": SalaryComponent.Method.choices,
        "roundings": SalaryComponent.Rounding.choices,
        "statutory_types": SalaryComponent.Statutory.choices,
    })


@module_required("payroll")
def payroll_entry_breakdown(request: HttpRequest, pk: int) -> HttpResponse:
    """Per-employee salary breakdown / calculation log for one payslip entry."""
    entry = get_object_or_404(
        PayslipEntry.objects.select_related("employee", "run"),
        pk=pk, organization=request.organization)
    lines = list(entry.component_amounts.all())
    return render(request, "payslip/payroll/entry_breakdown.html", {
        "entry": entry, "lines": lines,
    })


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
@module_required("payroll")
def employee_export(request: HttpRequest) -> HttpResponse:
    from .services.employee_export import build_employee_workbook, COLUMN_KEYS
    selected = [c for c in request.GET.getlist("cols") if c in COLUMN_KEYS]
    status = (request.GET.get("status") or "all").lower()
    data = build_employee_workbook(request.organization, selected, status=status)
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="employees.xlsx"'
    return resp


def tenure_label(doj, today=None) -> str:
    """'3 yr 4 mo' / '7 mo' / '< 1 mo' / '' for a joining date, as of today."""
    if not doj:
        return ""
    today = today or timezone.localdate()
    months = (today.year - doj.year) * 12 + (today.month - doj.month)
    if today.day < doj.day:
        months -= 1
    if months < 0:
        return "Joins " + doj.strftime("%d %b %Y")
    years, months = divmod(months, 12)
    if years == 0:
        return f"{months} mo" if months else "< 1 mo"
    if months == 0:
        return f"{years} yr"
    return f"{years} yr {months} mo"


def _financial_year_start(today) -> datetime.date:
    """Indian FY starts 1 April."""
    year = today.year if today.month >= 4 else today.year - 1
    return datetime.date(year, 4, 1)


EMPLOYEE_SORTS = {
    "doj_desc": "newest joiners first",
    "doj_asc": "longest serving first",
    "desig": "designation A to Z",
    "name": "name A to Z",
}


def _sort_employees(employees: list, sort: str) -> list:
    """Stable in-memory ordering. Employees without a joining date go last
    for the DOJ orders; blank designations go last for the designation order."""
    far_past, far_future = datetime.date.min, datetime.date.max
    if sort == "doj_asc":
        return sorted(employees, key=lambda e: (e.doj or far_future, e.name.lower()))
    if sort == "desig":
        return sorted(employees, key=lambda e: (not e.designation, e.designation.lower(),
                                                e.doj or far_future, e.name.lower()))
    if sort == "name":
        return sorted(employees, key=lambda e: (e.name.lower(), e.doj or far_future))
    # doj_desc (default): newest first; undated last.
    return sorted(employees, key=lambda e: (e.doj is None, -(e.doj or far_past).toordinal(),
                                            e.name.lower()))


def _group_by_designation(employees: list) -> list[dict]:
    """[{label, count, employees}] - designations A-Z, DOJ ascending within
    each. Employees without a designation form a trailing 'No designation'
    group. Input must already be in 'desig' order."""
    groups: list[dict] = []
    for e in employees:
        label = e.designation or "No designation"
        if not groups or groups[-1]["label"] != label:
            groups.append({"label": label, "count": 0, "employees": []})
        groups[-1]["employees"].append(e)
        groups[-1]["count"] += 1
    return groups


@module_required("payroll")
def employee_list(request: HttpRequest) -> HttpResponse:
    """Employees master. Query params: q (name/code/designation), status
    (active|inactive|all), sort (doj_desc|doj_asc|desig|name) and
    group=designation for a grouped register."""
    from urllib.parse import urlencode
    from .services.employee_export import EXPORTABLE_COLUMNS

    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "active").lower()
    if status_filter not in ("active", "inactive", "all"):
        status_filter = "active"
    sort = (request.GET.get("sort") or "doj_desc").lower()
    if sort not in EMPLOYEE_SORTS:
        sort = "doj_desc"
    grouped = (request.GET.get("group") or "").lower() == "designation"

    everyone = list(Employee.objects.filter(organization=request.organization))
    active_all = [e for e in everyone if e.is_active]
    inactive_all = [e for e in everyone if not e.is_active]

    employees = everyone
    if status_filter == "active":
        employees = active_all
    elif status_filter == "inactive":
        employees = inactive_all
    if q:
        needle = q.lower()
        employees = [e for e in employees
                     if needle in e.name.lower() or needle in e.employee_code.lower()
                     or needle in (e.designation or "").lower()]

    today = timezone.localdate()
    for i, e in enumerate(sorted(employees, key=lambda e: e.pk)):
        e.tenure_label = tenure_label(e.doj, today)
        e.avatar_class = f"c{(i % 6) + 1}"

    if grouped:
        groups = _group_by_designation(_sort_employees(employees, "desig"))
    else:
        groups = [{"label": "", "count": len(employees),
                   "employees": _sort_employees(employees, sort)}]

    # Links for the toolbar keep the other params intact.
    def link(**changes) -> str:
        params = {"q": q, "status": status_filter, "sort": sort}
        if grouped:
            params["group"] = "designation"
        params.update(changes)
        params = {k: v for k, v in params.items() if v}
        if params.get("sort") == "doj_desc":
            params.pop("sort")
        if params.get("status") == "active":
            params.pop("status")
        return "?" + urlencode(params) if params else "?"

    fy_start = _financial_year_start(today)
    designations = sorted({e.designation for e in active_all if e.designation}, key=str.lower)
    departments = {e.department for e in active_all if e.department}
    return render(request, "payslip/payroll/employee_list.html", {
        "groups": groups,
        "grouped": grouped,
        "shown_count": len(employees),
        "total_count": len(everyone),
        "q": q,
        "status_filter": status_filter,
        "sort": sort,
        "sort_label": EMPLOYEE_SORTS[sort],
        "sort_urls": {key: link(sort=key, group="") for key in EMPLOYEE_SORTS},
        "doj_toggle_url": link(sort="doj_asc" if sort == "doj_desc" else "doj_desc", group=""),
        "group_url": link(group="" if grouped else "designation"),
        "status_urls": {key: link(status=key) for key in ("active", "inactive", "all")},
        "active_count": len(active_all),
        "inactive_count": len(inactive_all),
        "joined_fy_count": sum(1 for e in active_all if e.doj and e.doj >= fy_start),
        "fy_start": fy_start,
        "designation_count": len(designations),
        "department_count": len(departments),
        "monthly_cost": sum((e.current_monthly_package for e in active_all), Decimal("0")),
        "esi_count": sum(1 for e in active_all if e.is_esi_eligible),
        "pf_count": sum(1 for e in active_all if e.is_pf_applicable),
        "export_columns": EXPORTABLE_COLUMNS,
    })


@module_required("payroll")
def employee_export(request: HttpRequest) -> HttpResponse:
    """Export employee master data with field selection."""
    org = request.organization
    form = EmployeeExportForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        from .services.payroll_export import build_employee_workbook

        selected_fields = form.get_selected_fields()
        if not selected_fields:
            messages.error(request, "Select at least one field to export.")
            return render(request, "payslip/payroll/employee_export.html", {"form": form})

        scope = form.cleaned_data["scope"]
        is_active = True if scope == "active" else None

        data = build_employee_workbook(org, selected_fields, is_active=is_active)
        resp = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        scope_label = "active" if scope == "active" else "all"
        resp["Content-Disposition"] = (
            f'attachment; filename="employees-{scope_label}-{timezone.localdate():%Y-%m-%d}.xlsx"'
        )
        return resp

    # GET: render form with current employee counts
    employees = Employee.objects.filter(organization=org)
    active_count = employees.filter(is_active=True).count()
    inactive_count = employees.filter(is_active=False).count()

    return render(request, "payslip/payroll/employee_export.html", {
        "form": form,
        "active_count": active_count,
        "inactive_count": inactive_count,
        "field_groups": EXPORT_FIELD_GROUPS,
    })


def _org_designations(org) -> list[str]:
    """Distinct designations in use - feeds the form's datalist so reusing
    one keeps the Employees report groupable."""
    values = (Employee.objects.filter(organization=org).exclude(designation="")
              .values_list("designation", flat=True).distinct())
    return sorted(set(values), key=str.lower)


def _next_employee_code(org) -> str:
    n = Employee.objects.filter(organization=org).count() + 1
    while Employee.objects.filter(organization=org, employee_code=f"EMP-{n:04d}").exists():
        n += 1
    return f"EMP-{n:04d}"


@module_required("payroll")
def employee_create(request: HttpRequest) -> HttpResponse:
    org = request.organization
    initial = {"employee_code": _next_employee_code(org)}
    form = EmployeeForm(request.POST or None, request.FILES or None,
                        organization=org, initial=initial)
    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.organization = org
        employee.created_by = request.user
        employee.save()
        messages.success(request, f"Added {employee.name}.")
        return redirect("employee_detail", pk=employee.pk)
    return render(request, "payslip/payroll/employee_detail.html", {
        "employee": None, "form": form, "heading": "Add Employee", "entries": [],
        "designations": _org_designations(org),
    })


@module_required("payroll")
def employee_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    employee = get_object_or_404(Employee, pk=pk, organization=org)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_employee":
            form = EmployeeForm(request.POST, request.FILES, instance=employee, organization=org)
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
        "designations": _org_designations(org),
        "tenure": tenure_label(employee.doj),
    })


@module_required("payroll")
def employee_photo(request: HttpRequest, pk: int) -> HttpResponse:
    """Serve an employee's stored photo bytes (org-scoped)."""
    employee = get_object_or_404(Employee, pk=pk, organization=request.organization)
    if not employee.photo:
        return HttpResponse(status=404)
    resp = HttpResponse(employee.photo_bytes,
                        content_type=employee.photo_content_type or "image/jpeg")
    resp["Cache-Control"] = "private, max-age=300"
    return resp


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
    # annotate() drops Meta.ordering (it conflicts with the GROUP BY), so the
    # newest-first order has to be restated explicitly here.
    runs = list(
        PayrollRun.objects.filter(organization=request.organization)
        .annotate(headcount=Count("entries"), net_total=Sum("entries__net_payable"))
        .order_by("-period")
    )
    form = PayrollRunCreateForm(initial={"period": timezone.localdate().replace(day=1)})
    finalized = sum(1 for r in runs if r.is_finalized)
    latest = runs[0] if runs else None
    return render(request, "payslip/payroll/run_list.html", {
        "runs": runs, "form": form,
        "finalized_count": finalized,
        "draft_count": len(runs) - finalized,
        "latest_run": latest,
        "lifetime_net": sum((r.net_total or Decimal("0") for r in runs), Decimal("0")),
    })


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
        structure = salary_structure_for(org, period)
        days_in_month = calendar.monthrange(period.year, period.month)[1]
        active = Employee.objects.filter(organization=org, is_active=True)
        pairs = []  # (entry, computation)
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
            pairs.append((entry, _recompute(entry, structure)))
        with transaction.atomic():
            PayslipEntry.objects.bulk_create([e for e, _ in pairs])
            for entry, computation in pairs:  # bulk_create backfills pks
                save_component_amounts(entry, computation)
        messages.success(request, f"Payroll run created for {period:%B %Y} "
                                  f"({len(pairs)} employees).")
    return redirect("payroll_run_detail", pk=run.pk)


@org_admin_required
def payroll_run_recalculate(request: HttpRequest, pk: int) -> HttpResponse:
    """Re-sync a DRAFT run against the current roster + salary data:
    add rows for newly-active employees, drop rows for now-inactive ones,
    and refresh each kept row's package/flags then recompute - preserving
    any manually-entered attendance. Finalized runs are never touched."""
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)
    if request.method != "POST" or run.is_finalized:
        return redirect("payroll_run_detail", pk=pk)

    structure = salary_structure_for(org, run.period)
    days_in_month = calendar.monthrange(run.period.year, run.period.month)[1]
    entries_by_emp = {e.employee_id: e for e in run.entries.select_related("employee")}
    active = list(Employee.objects.filter(organization=org, is_active=True))
    active_ids = {e.pk for e in active}

    removed = [e for emp_id, e in entries_by_emp.items() if emp_id not in active_ids]
    kept_pairs, new_pairs = [], []
    for employee in active:
        entry = entries_by_emp.get(employee.pk)
        if entry is not None:
            # Refresh master-driven fields; keep manual attendance as entered.
            entry.monthly_package = employee.current_monthly_package
            entry.is_esi_eligible = employee.is_esi_eligible
            entry.is_pf_applicable = employee.is_pf_applicable
            kept_pairs.append((entry, _recompute(entry, structure)))
        else:
            entry = PayslipEntry(
                organization=org, run=run, employee=employee,
                monthly_package=employee.current_monthly_package,
                total_working_days=days_in_month,
                lop_days=_suggest_lop_days(employee, run.period),
                is_esi_eligible=employee.is_esi_eligible,
                is_pf_applicable=employee.is_pf_applicable,
            )
            new_pairs.append((entry, _recompute(entry, structure)))

    with transaction.atomic():
        if removed:
            run.entries.filter(pk__in=[e.pk for e in removed]).delete()
        if new_pairs:
            PayslipEntry.objects.bulk_create([e for e, _ in new_pairs])
        if kept_pairs:
            PayslipEntry.objects.bulk_update(
                [e for e, _ in kept_pairs],
                ["monthly_package", "is_esi_eligible", "is_pf_applicable", *_COMPUTED_FIELDS])
        for entry, computation in (*kept_pairs, *new_pairs):
            save_component_amounts(entry, computation)

    messages.success(
        request,
        f"Recalculated {run.period:%B %Y}: +{len(new_pairs)} added, "
        f"−{len(removed)} removed, {len(kept_pairs)} updated.")
    return redirect("payroll_run_detail", pk=pk)


@module_required("payroll")
def payroll_run_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    run = get_object_or_404(PayrollRun, pk=pk, organization=org)

    if request.method == "POST" and not run.is_finalized:
        action = request.POST.get("action", "")
        if action == "save_grid":
            structure = salary_structure_for(org, run.period)
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
                    computation = _recompute(entry, structure)
                    save_component_amounts(entry, computation)
                PayslipEntry.objects.bulk_update(entries, [
                    "total_working_days", "cl_credit", "emp_leave_days", "lop_days",
                    "internet_allowance", "salary_arrear_allowance", "salary_advance",
                    "tds", "remarks", *_COMPUTED_FIELDS,
                ])
            messages.success(request, "Payroll grid saved and recomputed.")
            return redirect("payroll_run_detail", pk=pk)

    entries = list(run.entries.select_related("employee"))
    negative_count = sum(1 for e in entries if e.net_payable < 0)
    totals = {
        "gross": sum((e.gross_salary for e in entries), Decimal("0")),
        "deductions": sum((e.total_deductions for e in entries), Decimal("0")),
        "net": sum((e.net_payable for e in entries), Decimal("0")),
        "employer": sum((e.employer_contributions for e in entries), Decimal("0")),
        "ctc": sum((e.ctc for e in entries), Decimal("0")),
    }
    generated_pdfs = sum(1 for e in entries if e.pdf)
    comparison = _build_comparison(org, run, entries)
    register = _build_register(request, entries, comparison)
    return render(request, "payslip/payroll/run_detail.html", {
        "run": run, "entries": entries, "totals": totals,
        "negative_count": negative_count,
        "generated_pdfs": generated_pdfs,
        "missing_pdfs": len(entries) - generated_pdfs,
        "comparison": comparison,
        **register,
    })


REGISTER_ORDERS = {
    "desig": "Designation, then joining date",
    "doj_desc": "Joining date (newest)",
    "doj_asc": "Joining date (oldest)",
    "net_desc": "Net payable (high to low)",
    "name": "Name A-Z",
}


def _annotate_change(entry: PayslipEntry, comparison: dict | None) -> None:
    """One pill per register row: what moved since last month. Priority:
    new joiner, LOP, advance recovery, net-pay delta, else 'No change'."""
    prev_net = None
    if comparison:
        if any(j.pk == entry.pk for j in comparison["joiners"]):
            entry.change_label, entry.change_tone = "New this month", "blue"
            return
        for r in comparison["rows"]:
            if r["employee"].pk == entry.employee_id:
                prev_net = r["prev"]
                break
    if entry.lop_days and entry.lop_days > 0:
        days = entry.lop_days.normalize()
        days = int(days) if days == days.to_integral_value() else days
        entry.change_label = f"{days} LOP day{'s' if days != 1 else ''}"
        entry.change_tone = "amber"
        return
    if entry.salary_advance and entry.salary_advance > 0:
        entry.change_label, entry.change_tone = "Advance recovery", "red"
        return
    if prev_net is not None:
        delta = entry.net_payable - prev_net
        if delta > 0:
            entry.change_label, entry.change_tone = f"+\u20b9{delta:,.0f}", "green"
            return
        if delta < 0:
            entry.change_label, entry.change_tone = f"\u2212\u20b9{-delta:,.0f}", "red"
            return
    entry.change_label, entry.change_tone = "No change", "gray"


def _build_register(request: HttpRequest, entries: list, comparison: dict | None) -> dict:
    """Read-only salary register: `dept` filter + `order` param, grouped by
    designation for the default order, with a total row. The editable grid
    stays unfiltered (its POST handler reads every entry)."""
    dept = (request.GET.get("dept") or "").strip()
    order = (request.GET.get("order") or "desig").lower()
    if order not in REGISTER_ORDERS:
        order = "desig"

    rows = [e for e in entries if not dept or e.employee.department == dept]
    far_future = datetime.date.max
    if order == "doj_desc":
        rows.sort(key=lambda e: (e.employee.doj is None,
                                 -(e.employee.doj or datetime.date.min).toordinal(),
                                 e.employee.name.lower()))
    elif order == "doj_asc":
        rows.sort(key=lambda e: (e.employee.doj or far_future, e.employee.name.lower()))
    elif order == "net_desc":
        rows.sort(key=lambda e: (-e.net_payable, e.employee.name.lower()))
    elif order == "name":
        rows.sort(key=lambda e: e.employee.name.lower())
    else:
        rows.sort(key=lambda e: (not e.employee.designation, e.employee.designation.lower(),
                                 e.employee.doj or far_future, e.employee.name.lower()))

    for e in rows:
        _annotate_change(e, comparison)

    if order == "desig":
        groups: list[dict] = []
        for e in rows:
            label = e.employee.designation or "No designation"
            if not groups or groups[-1]["label"] != label:
                groups.append({"label": label, "count": 0, "entries": []})
            groups[-1]["entries"].append(e)
            groups[-1]["count"] += 1
    else:
        groups = [{"label": "", "count": len(rows), "entries": rows}]

    def total(attr):
        return sum((getattr(e, attr) for e in rows), Decimal("0"))

    return {
        "register_groups": groups,
        "register_count": len(rows),
        "register_totals": {
            "gross": total("gross_salary"), "pf": total("pf_employee"),
            "esi": total("esi_employee"), "tds": total("tds"),
            "advance": total("salary_advance"), "net": total("net_payable"),
            "pay_days": total("pay_days"), "twd": sum(e.total_working_days for e in rows),
        },
        "register_order": order,
        "register_orders": REGISTER_ORDERS,
        "register_dept": dept,
        "register_depts": sorted({e.employee.department for e in entries if e.employee.department},
                                 key=str.lower),
        "changed_count": sum(1 for e in rows if e.change_tone != "gray"),
    }


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
        "rows": rows,
        "changed_count": len(rows),
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

    structure = salary_structure_for(org, run.period)
    entries = list(run.entries.select_related("employee"))
    computations = [_recompute(entry, structure) for entry in entries]

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
        for entry, computation in zip(entries, computations):
            save_component_amounts(entry, computation)
        PayslipEntry.objects.bulk_update(entries, [
            *_COMPUTED_FIELDS, "pdf", "pdf_generated_at",
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
