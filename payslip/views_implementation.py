"""Implementation tracking views - onboarding, PO, agreements, feature status.

Lives inside the staff-only Income area and attaches to IncomeClient rows
(no separate project entity - one client, one implementation).
"""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms_income import ClientOnboardingForm, FeatureAddForm
from .models import ClientOnboarding, FeatureStatus, IncomeClient, feature_progress, onboarding_for
from .views_income import income_required, _engineer_names

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


@income_required
def implementation_dashboard(request: HttpRequest) -> HttpResponse:
    clients = list(IncomeClient.objects.prefetch_related("features")
                   .select_related("onboarding"))

    stage_counts = {key: 0 for key, _ in ClientOnboarding.Stage.choices}
    rows = []
    expiring = []
    po_pending = []
    for client in clients:
        onboarding = getattr(client, "onboarding", None)
        stage = onboarding.stage if onboarding else ClientOnboarding.Stage.ONBOARDING
        stage_counts[stage] += 1
        progress = feature_progress(client.features.all())
        rows.append({
            "client": client,
            "onboarding": onboarding,
            "stage": stage,
            "stage_label": dict(ClientOnboarding.Stage.choices)[stage],
            "stage_badge": STAGE_BADGES[stage],
            "progress": progress,
        })
        if onboarding and onboarding.agreement_signed and (
            onboarding.agreement_expired or onboarding.agreement_expiring
        ):
            expiring.append(onboarding)
        if client.is_active and not (onboarding and onboarding.po_received):
            po_pending.append({"client": client, "onboarding": onboarding})

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
        "po_pending": po_pending,
        "today": timezone.localdate(),
    })


@income_required
def client_implementation(request: HttpRequest, pk: int) -> HttpResponse:
    client = get_object_or_404(IncomeClient, pk=pk)
    onboarding = onboarding_for(client)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_onboarding":
            form = ClientOnboardingForm(request.POST, instance=onboarding)
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

    return render(request, "payslip/income/client_implementation.html", {
        "client": client,
        "onboarding": onboarding,
        "form": form,
        "add_form": FeatureAddForm(),
        "feature_rows": feature_rows,
        "progress": progress,
        "status_choices": FeatureStatus.Status.choices,
        "stage_badge": STAGE_BADGES[onboarding.stage],
        "engineer_options": _engineer_names(),
    })
