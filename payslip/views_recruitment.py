"""Recruitment module - job postings and candidate application tracking.
Org-scoped throughout; cross-org access 404s.
"""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import module_required
from .forms_recruitment import JobApplicationForm, JobPostingForm
from .models import JobApplication, JobPosting

STAGE_ORDER = [
    JobApplication.Stage.APPLIED,
    JobApplication.Stage.SCREENING,
    JobApplication.Stage.INTERVIEW,
    JobApplication.Stage.OFFERED,
    JobApplication.Stage.HIRED,
    JobApplication.Stage.REJECTED,
    JobApplication.Stage.WITHDRAWN,
]

STAGE_BADGES = {
    JobApplication.Stage.APPLIED: "blue",
    JobApplication.Stage.SCREENING: "amber",
    JobApplication.Stage.INTERVIEW: "amber",
    JobApplication.Stage.OFFERED: "green",
    JobApplication.Stage.HIRED: "green",
    JobApplication.Stage.REJECTED: "red",
    JobApplication.Stage.WITHDRAWN: "gray",
}


@module_required("people")
def job_posting_list(request: HttpRequest) -> HttpResponse:
    org = request.organization
    postings = (
        JobPosting.objects.filter(organization=org)
        .annotate(app_count=Count("applications"))
    )

    open_postings = list(postings.filter(status=JobPosting.Status.OPEN))
    on_hold_postings = list(postings.filter(status=JobPosting.Status.ON_HOLD))
    closed_postings = list(postings.filter(status=JobPosting.Status.CLOSED))
    draft_postings = list(postings.filter(status=JobPosting.Status.DRAFT))

    total_count = len(open_postings) + len(on_hold_postings) + len(closed_postings) + len(draft_postings)
    open_positions = sum(p.positions_count for p in open_postings)
    total_applications = sum(p.app_count for p in postings)

    return render(request, "payslip/recruitment/job_posting_list.html", {
        "open_postings": open_postings,
        "on_hold_postings": on_hold_postings,
        "closed_postings": closed_postings,
        "draft_postings": draft_postings,
        "total_count": total_count,
        "open_positions": open_positions,
        "total_applications": total_applications,
    })


@module_required("people")
def job_posting_create(request: HttpRequest) -> HttpResponse:
    org = request.organization
    initial = {"posted_date": timezone.localdate()}
    form = JobPostingForm(request.POST or None, organization=org, initial=initial)
    if request.method == "POST" and form.is_valid():
        posting = form.save(commit=False)
        posting.organization = org
        posting.created_by = request.user
        posting.save()
        messages.success(request, f"Job posting ‘{posting.title}’ created.")
        return redirect("job_posting_detail", pk=posting.pk)
    return render(request, "payslip/recruitment/job_posting_form.html", {
        "form": form,
        "heading": "New Job Posting",
        "posting": None,
    })


@module_required("people")
def job_posting_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    posting = get_object_or_404(JobPosting, pk=pk, organization=org)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_posting":
            form = JobPostingForm(request.POST, instance=posting, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, "Job posting updated.")
                return redirect("job_posting_detail", pk=pk)
            messages.error(request, "Please fix the errors below.")
        elif action == "delete_posting":
            title = posting.title
            posting.delete()
            messages.success(request, f"Deleted posting ‘{title}’ and all its applications.")
            return redirect("job_posting_list")
        else:
            form = JobPostingForm(instance=posting, organization=org)
    else:
        form = JobPostingForm(instance=posting, organization=org)

    app_counts = {}
    for stage_val, stage_label in JobApplication.Stage.choices:
        count = posting.applications.filter(stage=stage_val).count()
        if count:
            app_counts[stage_label] = count
    total_apps = posting.applications.count()

    return render(request, "payslip/recruitment/job_posting_detail.html", {
        "posting": posting,
        "form": form,
        "heading": posting.title,
        "app_counts": app_counts,
        "total_apps": total_apps,
    })


@module_required("people")
def job_application_list(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    posting = get_object_or_404(JobPosting, pk=pk, organization=org)
    applications = posting.applications.select_related("person")

    pipeline = []
    for stage_val in STAGE_ORDER:
        stage_apps = list(applications.filter(stage=stage_val))
        if stage_apps or stage_val in (
            JobApplication.Stage.APPLIED,
            JobApplication.Stage.SCREENING,
            JobApplication.Stage.INTERVIEW,
        ):
            pipeline.append({
                "value": stage_val,
                "label": stage_val.label,
                "badge": STAGE_BADGES.get(stage_val, "gray"),
                "apps": stage_apps,
                "count": len(stage_apps),
            })

    return render(request, "payslip/recruitment/job_application_list.html", {
        "posting": posting,
        "pipeline": pipeline,
        "total_apps": applications.count(),
    })


@module_required("people")
def job_application_create(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    posting = get_object_or_404(JobPosting, pk=pk, organization=org)
    initial = {"applied_date": timezone.localdate()}
    form = JobApplicationForm(request.POST or None, organization=org, initial=initial)
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        application.organization = org
        application.job_posting = posting
        application.created_by = request.user
        application.save()
        messages.success(request, f"Application from {application.applicant_name} added.")
        return redirect("job_application_list", pk=posting.pk)
    return render(request, "payslip/recruitment/job_application_form.html", {
        "form": form,
        "posting": posting,
        "heading": f"Add Application — {posting.title}",
        "application": None,
    })


@module_required("people")
def job_application_detail(request: HttpRequest, pk: int) -> HttpResponse:
    org = request.organization
    application = get_object_or_404(
        JobApplication.objects.select_related("job_posting", "person"),
        pk=pk, organization=org,
    )
    posting = application.job_posting

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_application":
            form = JobApplicationForm(request.POST, instance=application, organization=org)
            if form.is_valid():
                form.save()
                messages.success(request, "Application updated.")
                return redirect("job_application_detail", pk=pk)
            messages.error(request, "Please fix the errors below.")
        elif action == "delete_application":
            name = application.applicant_name
            posting_pk = posting.pk
            application.delete()
            messages.success(request, f"Deleted application from {name}.")
            return redirect("job_application_list", pk=posting_pk)
        else:
            form = JobApplicationForm(instance=application, organization=org)
    else:
        form = JobApplicationForm(instance=application, organization=org)

    can_convert = False
    employee = None
    if (application.stage == JobApplication.Stage.HIRED and application.person
            and application.person.kind == "CANDIDATE"):
        employee = application.person.employee_profile.first()
        can_convert = employee is None and request.membership.has_module("payroll")

    return render(request, "payslip/recruitment/job_application_detail.html", {
        "application": application,
        "posting": posting,
        "form": form,
        "heading": application.applicant_name,
        "can_convert": can_convert,
        "employee": employee,
    })
