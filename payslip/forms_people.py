"""Forms for the People registry."""
from __future__ import annotations

from django import forms

from .models import Person

_DATE = forms.DateInput(attrs={"type": "date"})


class PersonForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            "kind", "name", "title", "gender", "email", "phone", "address",
            "employee_no", "designation", "join_date", "leaving_date",
            "roll_number", "course", "college_name", "college_address",
            "internship_role", "start_date", "end_date",
            "notes",
        ]
        widgets = {
            "title": forms.Select(choices=[("", "—"), ("Mr.", "Mr."),
                                           ("Ms.", "Ms."), ("Mrs.", "Mrs.")]),
            "gender": forms.Select(choices=[("", "—"), ("male", "Male"),
                                            ("female", "Female")]),
            "address": forms.Textarea(attrs={"rows": 2}),
            "college_address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "join_date": _DATE, "leaving_date": _DATE,
            "start_date": _DATE, "end_date": _DATE,
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        return name

    def clean(self):
        cleaned = super().clean()
        # Per-org uniqueness on (kind, name) - friendly error instead of 500.
        name = cleaned.get("name")
        kind = cleaned.get("kind")
        if name and kind and self.organization is not None:
            qs = Person.objects.filter(organization=self.organization,
                                       kind=kind, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("name", "This person already exists - open their "
                                       "record from the People page instead.")
        return cleaned
