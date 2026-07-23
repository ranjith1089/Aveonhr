"""Forms for the Recruitment module."""
from __future__ import annotations

from django import forms

from .models import JobApplication, JobPosting, Person

_DATE = forms.DateInput(attrs={"type": "date"})


class JobPostingForm(forms.ModelForm):
    class Meta:
        model = JobPosting
        fields = [
            "title", "department", "location", "description", "requirements",
            "employment_type", "experience_range", "salary_range",
            "status", "posted_date", "closing_date", "positions_count",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "requirements": forms.Textarea(attrs={"rows": 4}),
            "posted_date": _DATE,
            "closing_date": _DATE,
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

    def clean(self):
        cleaned = super().clean()
        posted = cleaned.get("posted_date")
        closing = cleaned.get("closing_date")
        if posted and closing and closing < posted:
            self.add_error("closing_date",
                           "Closing date cannot be before the posted date.")
        return cleaned


class JobApplicationForm(forms.ModelForm):
    person = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Link to existing candidate",
        empty_label="— None (new applicant) —",
    )

    class Meta:
        model = JobApplication
        fields = [
            "applicant_name", "applicant_email", "applicant_phone",
            "person", "resume_notes", "cover_letter",
            "stage", "applied_date", "rating", "notes",
        ]
        widgets = {
            "resume_notes": forms.Textarea(attrs={"rows": 4}),
            "cover_letter": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "applied_date": _DATE,
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)
        if self.organization:
            self.fields["person"].queryset = Person.objects.filter(
                organization=self.organization,
                kind=Person.Kind.CANDIDATE,
            ).order_by("name")

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating is not None and not (1 <= rating <= 5):
            raise forms.ValidationError("Rating must be between 1 and 5.")
        return rating
