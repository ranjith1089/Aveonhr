"""People registry - stored candidates & internship students, with the
letters generated for each of them.

Org-scoped: every query filters by request.organization; cross-org 404.
Stored PDFs are served through the transient GeneratedFile token flow.
"""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import module_required
from .forms_people import PersonForm
from .models import Person, PersonDocument

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


def _quick_generate_actions(kind) -> list[dict]:
    """Blank-form links for one-step generation (no existing person) -
    the same builder pages, minus ?person=, so the standalone
    fill-and-generate-then-auto-capture flow is unchanged."""
    return [
        {"label": label, "url": reverse(url_name)}
        for label, url_name, _type_key in GENERATE_ACTIONS[kind]
    ]


@module_required("people")
def people_list(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()

    base = Person.objects.filter(organization=request.organization).annotate(
        doc_count=Count("documents"), last_doc=Max("documents__created_at")
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
    })


@module_required("people")
def person_create(request: HttpRequest) -> HttpResponse:
    initial = {}
    if request.GET.get("kind") in (Person.Kind.CANDIDATE, Person.Kind.INTERN):
        initial["kind"] = request.GET["kind"]
    form = PersonForm(request.POST or None, organization=request.organization,
                      initial=initial or None)
    if request.method == "POST" and form.is_valid():
        person = form.save(commit=False)
        person.organization = request.organization
        person.created_by = request.user
        person.save()
        messages.success(request, f"Added {person.name}.")
        return redirect("person_detail", pk=person.pk)
    return render(request, "payslip/person_detail.html", {
        "person": None,
        "form": form,
        "heading": "Add Person",
        "documents": [],
        "generate_actions": [],
    })


@module_required("people")
def person_detail(request: HttpRequest, pk: int) -> HttpResponse:
    person = get_object_or_404(Person, pk=pk, organization=request.organization)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "save_person":
            form = PersonForm(request.POST, instance=person,
                              organization=request.organization)
            if form.is_valid():
                form.save()
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
    return render(request, "payslip/person_detail.html", {
        "person": person,
        "form": form,
        "heading": person.name,
        "documents": documents,
        "generate_actions": actions,
    })
