"""People registry & Recruitment pipeline.

Org-scoped: every query filters by request.organization; cross-org 404.
Stored PDFs are served through the transient GeneratedFile token flow.
"""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import module_required
from .forms_people import InterviewRoundForm, JobOpeningForm, PersonForm
from .models import InterviewRound, JobOpening, Person, PersonDocument

# Which letters each kind of person can generate, with their builder URLs.
GENERATE_ACTIONS = {
    Person.Kind.CANDIDATE: [
        ("📄 Offer Letter", "offer_letter", "employment_offer"),
        ("📋 Appointment Order", "offer_letter", "appointment"),
        ("📜 Experience Letter", "experience_certificate", "employee"),
    ],
    Person.Kind.INTERN: [
        ("📄 Internship Offer Letter", "offer_letter", "internship"),
        ("📜 Internship Experience Certificate", "experience_certificate", "internship"),
    ],
}

DOC_BADGES = {
    PersonDocument.DocType.INTERNSHIP_OFFER: "blue",
    PersonDocument.DocType.APPOINTMENT: "amber",
    PersonDocument.DocType.EMPLOYMENT_OFFER: "blue",
    PersonDocument.DocType.EXPERIENCE_EMPLOYEE: "green",
    PersonDocument.DocType.EXPERIENCE_INTERNSHIP: "green",
}

STAGE_BADGES = {
    "NEW": "gray", "SCREENING": "amber", "SHORTLISTED": "blue",
    "INTERVIEW": "amber", "SELECTED": "green", "OFFERED": "blue",
    "JOINED": "green", "REJECTED": "red", "ON_HOLD": "gray",
}


def _quick_generate_actions(kind) -> list[dict]:
    return [
        {"label": label, "url": reverse(url_name)}
        for label, url_name, _type_key in GENERATE_ACTIONS[kind]
    ]


# ---------------------------------------------------------------------------
# People list
# ---------------------------------------------------------------------------
@module_required("people")
def people_list(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()

    base = Person.objects.filter(organization=request.organization).annotate(
        doc_count=Count("documents", distinct=True),
        last_doc=Max("documents__created_at"),
        employee_links=Count("employee_profile", distinct=True),
    )
    if q:
        base = base.filter(name__icontains=q)

    candidates = list(base.filter(kind=Person.Kind.CANDIDATE))
    interns = list(base.filter(kind=Person.Kind.INTERN))

    return render(request, "payslip/people_list.html", {
        "candidates": candidates,
        "interns": interns,
        "q": q,
        "candidate_quick_actions": _quick_generate_actions(Person.Kind.CANDIDATE),
        "intern_quick_actions": _quick_generate_actions(Person.Kind.INTERN),
        "stage_badges": STAGE_BADGES,
    })


# ---------------------------------------------------------------------------
# Person CRUD
# ---------------------------------------------------------------------------
@module_required("people")
def person_create(request: HttpRequest) -> HttpResponse:
    initial = {}
    if request.GET.get("kind") in (Person.Kind.CANDIDATE, Person.Kind.INTERN):
        initial["kind"] = request.GET["kind"]
    if request.GET.get("job"):
        initial["applied_for"] = request.GET["job"]
        initial["stage"] = Person.Stage.NEW
    form = PersonForm(request.POST or None, organization=request.organization,
                      initial=initial or None)
    if request.method == "POST" and form.is_valid():
        person = form.save(commit=False)
        person.organization = request.organization
        person.created_by = request.user
        if person.stage and not person.stage_updated_at:
            person.stage_updated_at = timezone.now()
        person.save()
        messages.success(request, f"Added {person.name}.")
        return redirect("person_detail", pk=person.pk)
    return render(request, "payslip/person_detail.html", {
        "person": None,
        "form": form,
        "heading": "Add Person",
        "documents": [],
        "generate_actions": [],
        "interviews": [],
        "interview_form": InterviewRoundForm(),
    })


@module_required("people")
def person_detail(request: HttpRequest, pk: int) -> HttpResponse:
    person = get_object_or_404(Person, pk=pk, organization=request.organization)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_person":
            old_stage = person.stage
            form = PersonForm(request.POST, instance=person,
                              organization=request.organization)
            if form.is_valid():
                p = form.save(commit=False)
                if p.stage != old_stage:
                    p.stage_updated_at = timezone.now()
                p.save()
                messages.success(request, "Details saved.")
                return redirect("person_detail", pk=pk)
            messages.error(request, "Please fix the errors below.")
        else:
            form = PersonForm(instance=person, organization=request.organization)

        if action in ("download_doc", "download_doc_plain"):
            doc = get_object_or_404(PersonDocument, pk=request.POST.get("doc_id"),
                                    person=person)
            from .views import _save_content
            content = doc.pdf_plain if action == "download_doc_plain" else doc.pdf
            if not content:
                messages.error(request, "That version is not stored for this letter.")
                return redirect("person_detail", pk=pk)
            suffix = "_plain" if action == "download_doc_plain" else ""
            base = doc.filename.rsplit(".", 1)[0]
            token = _save_content(request.user, bytes(content), "application/pdf",
                                  f"{base}{suffix}.pdf")
            return redirect(reverse("download_file", kwargs={"token": token}))

        if action == "delete_doc":
            doc = get_object_or_404(PersonDocument, pk=request.POST.get("doc_id"),
                                    person=person)
            doc.delete()
            messages.success(request, "Letter removed from the record.")
            return redirect("person_detail", pk=pk)

        if action == "delete_person":
            name = person.name
            person.delete()
            messages.success(request, f"Deleted {name} and their letters.")
            return redirect("people_list")
    else:
        form = PersonForm(instance=person, organization=request.organization)

    documents = [
        {"d": d, "badge": DOC_BADGES.get(d.doc_type, "gray")}
        for d in person.documents.select_related("created_by")
    ]
    actions = [
        {"label": label, "url": f"{reverse(url_name)}?person={person.pk}&type={type_key}"}
        for label, url_name, type_key in GENERATE_ACTIONS[person.kind]
    ]
    employee = person.employee_profile.first()
    interviews = person.interviews.all()
    return render(request, "payslip/person_detail.html", {
        "person": person,
        "form": form,
        "heading": person.name,
        "documents": documents,
        "generate_actions": actions,
        "employee": employee,
        "can_convert": (person.kind == Person.Kind.CANDIDATE and employee is None
                        and request.membership.has_module("payroll")),
        "interviews": interviews,
        "interview_form": InterviewRoundForm(),
        "stage_badges": STAGE_BADGES,
    })


# ---------------------------------------------------------------------------
# Recruitment pipeline
# ---------------------------------------------------------------------------
@module_required("people")
def recruitment_pipeline(request: HttpRequest) -> HttpResponse:
    org = request.organization
    stage_filter = (request.GET.get("stage") or "").strip()
    source_filter = (request.GET.get("source") or "").strip()
    job_filter = (request.GET.get("job") or "").strip()
    q = (request.GET.get("q") or "").strip()

    candidates = Person.objects.filter(
        organization=org, kind=Person.Kind.CANDIDATE,
    ).exclude(stage="").select_related("applied_for")

    if stage_filter:
        candidates = candidates.filter(stage=stage_filter)
    if source_filter:
        candidates = candidates.filter(source=source_filter)
    if job_filter:
        candidates = candidates.filter(applied_for_id=job_filter)
    if q:
        candidates = candidates.filter(name__icontains=q)

    candidates = list(candidates)

    all_in_pipeline = Person.objects.filter(
        organization=org, kind=Person.Kind.CANDIDATE,
    ).exclude(stage="")
    stage_cards = []
    total_pipeline = 0
    for val, label in Person.Stage.choices:
        c = all_in_pipeline.filter(stage=val).count()
        total_pipeline += c
        stage_cards.append({"val": val, "label": label, "count": c})

    jobs = JobOpening.objects.filter(organization=org, status=JobOpening.Status.OPEN)

    return render(request, "payslip/recruitment_pipeline.html", {
        "candidates": candidates,
        "stage_filter": stage_filter,
        "source_filter": source_filter,
        "job_filter": job_filter,
        "q": q,
        "stage_cards": stage_cards,
        "total_pipeline": total_pipeline,
        "stages": Person.Stage.choices,
        "sources": Person.Source.choices,
        "jobs": jobs,
    })


@module_required("people")
@require_POST
def person_update_stage(request: HttpRequest, pk: int) -> JsonResponse:
    person = get_object_or_404(Person, pk=pk, organization=request.organization)
    new_stage = (request.POST.get("stage") or "").strip()
    if new_stage not in Person.Stage.values:
        return JsonResponse({"error": "Invalid stage."}, status=400)
    person.stage = new_stage
    person.stage_updated_at = timezone.now()
    person.save(update_fields=["stage", "stage_updated_at", "updated_at"])
    return JsonResponse({"ok": True, "stage": new_stage,
                         "label": Person.Stage(new_stage).label})


# ---------------------------------------------------------------------------
# Job Openings
# ---------------------------------------------------------------------------
@module_required("people")
def job_opening_list(request: HttpRequest) -> HttpResponse:
    org = request.organization
    show = (request.GET.get("show") or "open").strip()
    openings = JobOpening.objects.filter(organization=org)
    if show == "open":
        openings = openings.filter(status=JobOpening.Status.OPEN)
    elif show == "closed":
        openings = openings.filter(status=JobOpening.Status.CLOSED)
    openings = list(openings)
    return render(request, "payslip/job_opening_list.html", {
        "openings": openings, "show": show,
    })


@module_required("people")
def job_opening_create(request: HttpRequest) -> HttpResponse:
    form = JobOpeningForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        opening = form.save(commit=False)
        opening.organization = request.organization
        opening.save()
        messages.success(request, f"Job opening '{opening.title}' created.")
        return redirect("job_opening_list")
    return render(request, "payslip/job_opening_form.html", {
        "form": form, "heading": "Add Job Opening",
    })


@module_required("people")
def job_opening_edit(request: HttpRequest, pk: int) -> HttpResponse:
    opening = get_object_or_404(JobOpening, pk=pk, organization=request.organization)
    form = JobOpeningForm(request.POST or None, instance=opening)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Job opening updated.")
        return redirect("job_opening_list")
    return render(request, "payslip/job_opening_form.html", {
        "form": form, "heading": f"Edit {opening.title}", "opening": opening,
    })


# ---------------------------------------------------------------------------
# Interview rounds
# ---------------------------------------------------------------------------
@module_required("people")
@require_POST
def interview_add(request: HttpRequest, pk: int) -> HttpResponse:
    person = get_object_or_404(Person, pk=pk, organization=request.organization)
    form = InterviewRoundForm(request.POST)
    if form.is_valid():
        interview = form.save(commit=False)
        interview.person = person
        interview.save()
        messages.success(request, f"Interview round '{interview.round_name}' added.")
    else:
        messages.error(request, "Could not add interview: " +
                       "; ".join(f"{f}: {e[0]}" for f, e in form.errors.items()))
    return redirect("person_detail", pk=pk)


@module_required("people")
@require_POST
def interview_delete(request: HttpRequest, pk: int) -> HttpResponse:
    interview = get_object_or_404(
        InterviewRound.objects.select_related("person"),
        pk=pk, person__organization=request.organization,
    )
    person_pk = interview.person_id
    interview.delete()
    messages.success(request, "Interview round removed.")
    return redirect("person_detail", pk=person_pk)


# ---------------------------------------------------------------------------
# Convert to Employee (unchanged)
# ---------------------------------------------------------------------------
@module_required("people")
def person_convert(request: HttpRequest, pk: int) -> HttpResponse:
    from .decorators import _forbidden
    from .forms_payroll import ConvertToEmployeeForm
    from .views_payroll import _next_employee_code

    org = request.organization
    person = get_object_or_404(Person, pk=pk, organization=org)

    if not request.membership.has_module("payroll"):
        return _forbidden(request, "Payroll & Salary")
    if person.kind != Person.Kind.CANDIDATE:
        messages.error(request, "Only candidates can be converted to employees.")
        return redirect("person_detail", pk=pk)
    existing = person.employee_profile.first()
    if existing is not None:
        messages.info(request, f"{person.name} is already a payroll employee.")
        return redirect("employee_detail", pk=existing.pk)

    if request.method == "POST":
        form = ConvertToEmployeeForm(request.POST, organization=org)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.organization = org
            employee.person = person
            employee.name = person.name
            employee.notes = person.notes
            employee.created_by = request.user
            employee.save()
            messages.success(request, f"{person.name} converted to a payroll "
                                      f"employee. Add bank details to finish the profile.")
            return redirect("employee_detail", pk=employee.pk)
    else:
        form = ConvertToEmployeeForm(organization=org, initial={
            "employee_code": _next_employee_code(org),
            "designation": person.designation,
            "doj": person.join_date,
        })
    return render(request, "payslip/payroll/person_convert.html", {
        "person": person, "form": form,
    })
