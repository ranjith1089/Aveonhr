"""Proposal history - list, view, revise and delete generated proposals.

Org-scoped like the income module: every query filters by
request.organization (set by module_required), cross-org access 404s.
Viewing/downloading reuses the transient GeneratedFile token flow
(_save_content + preview_pdf/download_file) - no new file serving.
"""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .decorators import module_required
from .models import ProposalRecord


def _safe_name(client_name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", client_name).strip("_") or "client"


@module_required("proposals")
def proposal_history(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    records = ProposalRecord.objects.filter(organization=request.organization) \
        .select_related("created_by")
    if q:
        records = records.filter(client_name__icontains=q)
    records = list(records.order_by("client_name", "-revision"))

    # Mark the newest revision per client so the list can highlight it.
    rows = []
    seen_clients = set()
    for r in records:
        is_latest = r.client_name not in seen_clients
        seen_clients.add(r.client_name)
        rows.append({"r": r, "is_latest": is_latest})

    return render(request, "payslip/proposal_history.html", {
        "rows": rows,
        "q": q,
        "client_count": len(seen_clients),
        "record_count": len(records),
    })


@module_required("proposals")
def proposal_record(request: HttpRequest, pk: int) -> HttpResponse:
    record = get_object_or_404(ProposalRecord, pk=pk,
                               organization=request.organization)

    if request.method == "POST":
        action = request.POST.get("action", "")
        from .views import _save_content, _try_html_to_pdf

        if action == "view":
            token = _save_content(
                request.user, record.html.encode("utf-8"),
                "text/html; charset=utf-8",
                f"aveon_proposal_{_safe_name(record.client_name)}_rev{record.revision}.html",
            )
            return redirect(reverse("preview_pdf", kwargs={"token": token}))

        if action == "download":
            base = f"aveon_proposal_{_safe_name(record.client_name)}_rev{record.revision}"
            pdf = _try_html_to_pdf(record.html)
            if pdf:
                token = _save_content(request.user, pdf, "application/pdf", f"{base}.pdf")
            else:
                token = _save_content(request.user, record.html.encode("utf-8"),
                                      "text/html; charset=utf-8", f"{base}.html")
            return redirect(reverse("download_file", kwargs={"token": token}))

        if action == "delete":
            label = f"{record.client_name} Rev {record.revision}"
            record.delete()
            messages.success(request, f"Deleted proposal {label} from history.")
            return redirect("proposal_history")

    revisions = list(
        ProposalRecord.objects.filter(
            organization=request.organization, client_name=record.client_name
        ).select_related("created_by").order_by("-revision")
    )
    return render(request, "payslip/proposal_record.html", {
        "record": record,
        "revisions": revisions,
    })
