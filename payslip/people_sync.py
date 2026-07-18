"""Auto-capture and prefill glue between the letter forms and the People
registry.

Every generated offer/appointment/experience letter stores (or updates) the
person - matched by (organization, kind, name) - and logs the exact PDFs
issued. Prefill runs the same field maps in reverse, seeding a letter form
from the person plus their latest snapshot of the same document type.
"""
from __future__ import annotations

import datetime
import re

from .models import Person, PersonDocument

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def form_snapshot(cleaned_data: dict) -> dict:
    """JSON-safe copy of a validated form (dates/decimals become strings,
    uploaded files are dropped)."""
    snapshot = {}
    for key, value in cleaned_data.items():
        if hasattr(value, "read"):  # uploaded file
            continue
        if isinstance(value, (list, tuple)):
            snapshot[key] = list(value)
        elif value is None or isinstance(value, (str, int, bool)):
            snapshot[key] = value
        else:
            snapshot[key] = str(value)
    return snapshot


def _revive_dates(initial: dict) -> dict:
    for key, value in list(initial.items()):
        if isinstance(value, str) and _ISO_DATE.match(value):
            try:
                initial[key] = datetime.date.fromisoformat(value)
            except ValueError:
                pass
    return initial


# person field <- form field, per document type. Also used in reverse for
# prefill (form field <- person field).
_FIELD_MAPS = {
    PersonDocument.DocType.INTERNSHIP_OFFER: {
        "kind": Person.Kind.INTERN,
        "name": "name",
        "fields": {
            "roll_number": "roll_number",
            "course": "course",
            "college_name": "college_name",
            "college_address": "college_address",
            "internship_role": "internship_role",
            "start_date": "start_date",
        },
    },
    PersonDocument.DocType.APPOINTMENT: {
        "kind": Person.Kind.CANDIDATE,
        "name": "employee_name",
        "fields": {
            "designation": "designation",
            "join_date": "join_date",
        },
    },
    PersonDocument.DocType.EMPLOYMENT_OFFER: {
        "kind": Person.Kind.CANDIDATE,
        "name": "candidate_name",
        "fields": {
            "designation": "position",
            "join_date": "joining_date",
        },
    },
    PersonDocument.DocType.EXPERIENCE_EMPLOYEE: {
        "kind": Person.Kind.CANDIDATE,
        "name": "employee_name_exp",
        "fields": {
            "title": "title",
            "gender": "gender",
            "employee_no": "employee_no",
            "designation": "designation_exp",
            "join_date": "join_date_exp",
            "leaving_date": "leaving_date",
        },
    },
    PersonDocument.DocType.EXPERIENCE_INTERNSHIP: {
        "kind": Person.Kind.INTERN,
        "name": "intern_name",
        "fields": {
            "gender": "gender",
            "internship_role": "internship_domain",
            "start_date": "internship_start_date",
            "end_date": "internship_end_date",
        },
    },
}

OFFER_TYPE_TO_DOC = {
    "internship": PersonDocument.DocType.INTERNSHIP_OFFER,
    "appointment": PersonDocument.DocType.APPOINTMENT,
    "employment_offer": PersonDocument.DocType.EMPLOYMENT_OFFER,
}

CERT_TYPE_TO_DOC = {
    "employee": PersonDocument.DocType.EXPERIENCE_EMPLOYEE,
    "internship": PersonDocument.DocType.EXPERIENCE_INTERNSHIP,
}


def _capture(request, doc_type, cleaned_data: dict, *, pdf: bytes,
             pdf_plain: bytes | None, filename: str) -> Person | None:
    spec = _FIELD_MAPS[doc_type]
    name = (cleaned_data.get(spec["name"]) or "").strip()
    if not name:
        return None

    person, _ = Person.objects.get_or_create(
        organization=request.organization, kind=spec["kind"], name=name,
        defaults={"created_by": request.user},
    )
    # Latest non-empty values win; blanks never wipe stored details.
    changed = False
    for person_field, form_field in spec["fields"].items():
        value = cleaned_data.get(form_field)
        if value not in (None, "") and value != getattr(person, person_field):
            setattr(person, person_field, value)
            changed = True
    # Appointment orders carry the address as separate lines.
    if doc_type == PersonDocument.DocType.APPOINTMENT:
        address = "\n".join(p for p in [
            cleaned_data.get("present_address1"), cleaned_data.get("present_address2"),
            cleaned_data.get("present_address3"),
            ", ".join(x for x in [cleaned_data.get("present_address_city"),
                                  cleaned_data.get("present_address_state"),
                                  cleaned_data.get("present_address_pin")] if x),
        ] if p)
        if address and address != person.address:
            person.address = address
            changed = True
    if changed:
        person.save()

    PersonDocument.objects.create(
        organization=request.organization, person=person,
        created_by=request.user, doc_type=doc_type,
        form_data=form_snapshot(cleaned_data),
        pdf=pdf, pdf_plain=pdf_plain, filename=filename,
    )
    return person


def capture_offer_letter(request, form, *, pdf, pdf_plain, filename):
    doc_type = OFFER_TYPE_TO_DOC.get(form.cleaned_data.get("offer_type"))
    if doc_type is None:
        return None
    return _capture(request, doc_type, form.cleaned_data,
                    pdf=pdf, pdf_plain=pdf_plain, filename=filename)


def capture_experience(request, form, *, pdf, pdf_plain, filename):
    doc_type = CERT_TYPE_TO_DOC.get(form.cleaned_data.get("certificate_type"))
    if doc_type is None:
        return None
    return _capture(request, doc_type, form.cleaned_data,
                    pdf=pdf, pdf_plain=pdf_plain, filename=filename)


def person_initial(person: Person, doc_type) -> dict:
    """Form initials for generating `doc_type` for this person.

    The latest snapshot of the same type restores everything (compensation
    breakdown, signatories, ...); the person's current details overlay it so
    edits made on the People page win.
    """
    spec = _FIELD_MAPS[doc_type]
    latest = person.documents.filter(doc_type=doc_type).first()
    initial = dict(latest.form_data) if latest else {}
    initial.pop("offer_type", None)
    initial.pop("certificate_type", None)

    initial[spec["name"]] = person.name
    for person_field, form_field in spec["fields"].items():
        value = getattr(person, person_field)
        if value not in (None, ""):
            initial[form_field] = value

    # Selector value so the right section opens.
    for offer_type, dt in OFFER_TYPE_TO_DOC.items():
        if dt == doc_type:
            initial["offer_type"] = offer_type
    for cert_type, dt in CERT_TYPE_TO_DOC.items():
        if dt == doc_type:
            initial["certificate_type"] = cert_type

    return _revive_dates(initial)
