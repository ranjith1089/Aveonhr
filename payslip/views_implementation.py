"""Implementation tracking views - onboarding, PO, agreements, feature status.

Lives inside the staff-only Income area and attaches to IncomeClient rows
(no separate project entity - one client, one implementation).
"""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

import mimetypes

from .decorators import module_required
from .forms_income import ClientOnboardingForm, FeatureAddForm
from .models import ClientOnboarding, FeatureStatus, IncomeClient, feature_progress, onboarding_for
from .views_income import _engineer_names

STAGE_BADGES = {
    ClientOnboarding.Stage.ONBOARDING: "blue",
    ClientOnboarding.Stage.IMPLEMENTATION: "amber",
    ClientOnboarding.Stage.LIVE: "green",
    ClientOnboarding.Stage.ON_HOLD: "gray",
    ClientOnboarding.Stage.DISCONTINUED: "red",
}

FEATURE_BADGES = {
    FeatureStatus.Status.NOT_STARTED: "gray",
    FeatureStatus.Status.IN_PROGRESS: "blue",
    FeatureStatus.Status.TESTING: "amber",
    FeatureStatus.Status.LIVE: "green",
    FeatureStatus.Status.ON_HOLD: "red",
    FeatureStatus.Status.NA: "gray",
}


def _cms_module_names() -> list[str]:
    from .proposal_catalog import CMS_FULL_MODULES, MODULES
    return [MODULES[code]["name"] for code in CMS_FULL_MODULES]


@module_required("implementation")
def implementation_dashboard(request: HttpRequest) -> HttpResponse:
    clients = list(IncomeClient.objects.filter(organization=request.organization)
                   .prefetch_related("features", "billings")
                   .select_related("onboarding"))

    stage_counts = {key: 0 for key, _ in ClientOnboarding.Stage.choices}
    rows = []
    expiring = []
    po_pending_count = 0
    for client in clients:
        onboarding = getattr(client, "onboarding", None)
        stage = onboarding.stage if onboarding else ClientOnboarding.Stage.ONBOARDING
        stage_counts[stage] += 1
        progress = feature_progress(client.features.all())

        po_ok = bool(onboarding and onboarding.po_received)
        po_pending = client.is_active and not po_ok
        po_pending_count += int(po_pending)

        # Agreement chip: pending -> gray, expired -> red, expiring -> amber,
        # otherwise green with the validity label.
        if onboarding and onboarding.agreement_signed:
            if onboarding.agreement_expired:
                agr_badge, agr_label = "red", onboarding.agreement_label
            elif onboarding.agreement_expiring:
                agr_badge, agr_label = "amber", onboarding.agreement_label
            else:
                agr_badge, agr_label = "green", onboarding.agreement_label
            alert = onboarding.agreement_expired or onboarding.agreement_expiring
        else:
            agr_badge, agr_label, alert = "gray", "Pending", False

        rows.append({
            "client": client,
            "onboarding": onboarding,
            "stage": stage,
            "stage_label": dict(ClientOnboarding.Stage.choices)[stage],
            "stage_badge": STAGE_BADGES[stage],
            "progress": progress,
            "po_ok": po_ok,
            "po_pending": po_pending,
            "agr_badge": agr_badge,
            "agr_label": agr_label,
            "alert": alert,
            "engineer": (onboarding.engineer if onboarding else "") or client.latest_engineer,
        })
        if alert:
            expiring.append(onboarding)

    # Expired first (most negative days), then soonest-to-expire.
    expiring.sort(key=lambda o: o.days_to_expiry)
    rows.sort(key=lambda r: (-r["progress"]["pct"], r["client"].name))

    stage_chips = [
        {"key": key, "label": label, "count": stage_counts[key],
         "badge": STAGE_BADGES[key]}
        for key, label in ClientOnboarding.Stage.choices
    ]

    return render(request, "payslip/income/implementation_dashboard.html", {
        "rows": rows,
        "stage_chips": stage_chips,
        "expiring": expiring,
        "po_pending_count": po_pending_count,
        "live_count": stage_counts[ClientOnboarding.Stage.LIVE],
        "client_count": len(rows),
        "today": timezone.localdate(),
    })


@module_required("implementation")
def client_implementation(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(IncomeClient, pk=pk, organization=request.organization)
    onboarding = onboarding_for(client)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_onboarding":
            form = ClientOnboardingForm(request.POST, request.FILES, instance=onboarding)
            if form.is_valid():
                form.save()
                messages.success(request, "Onboarding details saved.")
                return redirect("client_implementation", pk=pk)
            messages.error(request, "Please fix the errors below.")
        else:
            form = ClientOnboardingForm(instance=onboarding)

        if action == "save_features":
            today = timezone.localdate()
            valid_statuses = {s for s, _ in FeatureStatus.Status.choices}
            updated = 0
            for feature in client.features.all():
                status = request.POST.get(f"status_{feature.pk}")
                if status not in valid_statuses:
                    continue
                engineer = request.POST.get(f"engineer_{feature.pk}", feature.engineer)
                remarks = request.POST.get(f"remarks_{feature.pk}", feature.remarks)
                changed = (status != feature.status or engineer != feature.engineer
                           or remarks != feature.remarks)
                feature.status = status
                feature.engineer = engineer.strip()[:50]
                feature.remarks = remarks.strip()[:300]
                if status == FeatureStatus.Status.LIVE and not feature.completed_on:
                    feature.completed_on = today
                    changed = True
                if status in (FeatureStatus.Status.IN_PROGRESS,
                              FeatureStatus.Status.TESTING) and not feature.started_on:
                    feature.started_on = today
                    changed = True
                if changed:
                    feature.save()
                    updated += 1
            messages.success(request, f"Feature statuses saved ({updated} updated).")
            return redirect("client_implementation", pk=pk)

        if action == "add_feature":
            add_form = FeatureAddForm(request.POST)
            if add_form.is_valid():
                name = add_form.cleaned_data["name"].strip()
                if client.features.filter(name__iexact=name).exists():
                    messages.error(request, f'"{name}" is already in the list.')
                else:
                    max_order = max((f.order for f in client.features.all()), default=0)
                    FeatureStatus.objects.create(
                        client=client, name=name,
                        status=add_form.cleaned_data["status"],
                        order=max_order + 1,
                    )
                    messages.success(request, f'Added "{name}".')
            else:
                messages.error(request, "Enter a feature name.")
            return redirect("client_implementation", pk=pk)

        if action == "seed_cms":
            created = 0
            for i, name in enumerate(_cms_module_names(), start=1):
                _, was_created = FeatureStatus.objects.get_or_create(
                    client=client, name=name, defaults={"order": i}
                )
                created += int(was_created)
            if created:
                messages.success(request, f"Added {created} CMS ERP modules.")
            else:
                messages.success(request, "All 25 CMS ERP modules are already listed.")
            return redirect("client_implementation", pk=pk)

        if action == "delete_feature":
            feature = get_object_or_404(FeatureStatus, pk=request.POST.get("feature_id"),
                                        client=client)
            feature.delete()
            messages.success(request, f'Removed "{feature.name}".')
            return redirect("client_implementation", pk=pk)
    else:
        form = ClientOnboardingForm(instance=onboarding)

    features = list(client.features.all())
    progress = feature_progress(features)
    feature_rows = [
        {"feature": f, "badge": FEATURE_BADGES.get(f.status, "gray")}
        for f in features
    ]

    status_counts = {key: 0 for key, _ in FeatureStatus.Status.choices}
    for f in features:
        if f.status in status_counts:
            status_counts[f.status] += 1
    status_filters = [
        {"key": key, "label": label, "count": status_counts[key]}
        for key, label in FeatureStatus.Status.choices
    ]

    # Collapse the big details form once the basics are on file - the
    # feature grid is the page people come back to. Errors force it open.
    details_open = bool(form.errors) or not any([
        onboarding.contact_person, onboarding.po_received,
        onboarding.agreement_signed, onboarding.onboarded_on,
        onboarding.engineer,
    ])

    return render(request, "payslip/income/client_implementation.html", {
        "client": client,
        "onboarding": onboarding,
        "form": form,
        "add_form": FeatureAddForm(),
        "feature_rows": feature_rows,
        "progress": progress,
        "status_choices": FeatureStatus.Status.choices,
        "status_filters": status_filters,
        "stage_badge": STAGE_BADGES[onboarding.stage],
        "engineer_options": _engineer_names(request.organization),
        "details_open": details_open,
        "all_clients": IncomeClient.objects.filter(organization=request.organization)
                       .only("id", "name").order_by("name"),
    })


@module_required("implementation")
def download_po_document(request: HttpRequest, pk: int) -> HttpResponse:
    onboarding = get_object_or_404(
        ClientOnboarding.objects.select_related("client"),
        pk=pk, client__organization=request.organization,
    )
    if not onboarding.po_document:
        return HttpResponse("No PO document uploaded.", status=404)
    content_type = mimetypes.guess_type(onboarding.po_filename)[0] or "application/octet-stream"
    resp = HttpResponse(bytes(onboarding.po_document), content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{onboarding.po_filename}"'
    return resp


@module_required("implementation")
def download_agreement_document(request: HttpRequest, pk: int) -> HttpResponse:
    onboarding = get_object_or_404(
        ClientOnboarding.objects.select_related("client"),
        pk=pk, client__organization=request.organization,
    )
    if not onboarding.agreement_document:
        return HttpResponse("No agreement document uploaded.", status=404)
    content_type = mimetypes.guess_type(onboarding.agreement_filename)[0] or "application/octet-stream"
    resp = HttpResponse(bytes(onboarding.agreement_document), content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{onboarding.agreement_filename}"'
    return resp
