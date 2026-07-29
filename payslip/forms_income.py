"""Forms for the staff-only Aveon Income module."""
from __future__ import annotations

import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .forms import EXCEL_EXTENSIONS, EXECUTABLE_EXTENSIONS, _extension
from .models import AcademicYear, ClientBilling, IncomeClient, PaymentReceipt


class IncomeClientForm(forms.ModelForm):
    class Meta:
        model = IncomeClient
        fields = ["name", "agreement_status", "is_active", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

    def clean_name(self):
        # Uniqueness is per-organization now (composite constraint) - validate
        # here so the user gets a form error instead of an IntegrityError.
        name = (self.cleaned_data.get("name") or "").strip()
        if self.organization is not None:
            qs = IncomeClient.objects.filter(organization=self.organization, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("A client with this name already exists.")
        return name


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["label"]
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "2026-2027"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

    def clean_label(self):
        raw = (self.cleaned_data.get("label") or "").strip()
        m = re.match(r"^(\d{4})\s*-\s*(\d{2,4})$", raw)
        if not m:
            raise ValidationError("Use the format 2025-2026.")
        start = int(m.group(1))
        end_raw = m.group(2)
        end = int(end_raw) if len(end_raw) == 4 else int(str(start)[:2] + end_raw)
        if end != start + 1:
            raise ValidationError("The end year must be the start year + 1.")
        label = f"{start}-{end}"
        if self.organization is not None:
            qs = AcademicYear.objects.filter(organization=self.organization, label=label)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(f"{label} already exists.")
        return label


class ClientBillingForm(forms.ModelForm):
    class Meta:
        model = ClientBilling
        fields = [
            "academic_year", "engineer",
            "student_count", "rate", "one_time_payment",
            "override_amounts", "taxable_value", "gst_amount", "net_amount",
            "previous_pending", "invoice_status", "remarks",
            "next_followup_date", "followup_note",
        ]
        widgets = {
            "academic_year": forms.Select(),
            "engineer": forms.TextInput(attrs={
                "list": "engineer-options",
                "placeholder": "Pick or type a new engineer",
            }),
            "remarks": forms.Textarea(attrs={"rows": 2}),
            "next_followup_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        org = organization or getattr(
            getattr(self.instance, "client", None), "organization", None
        )
        if org is not None:
            if not AcademicYear.objects.filter(organization=org).exists():
                existing = (
                    ClientBilling.objects.filter(client__organization=org)
                    .values_list("academic_year", flat=True)
                    .distinct()
                )
                for label in existing:
                    AcademicYear.objects.get_or_create(
                        organization=org, label=label,
                        defaults={"is_active": True},
                    )
            years = AcademicYear.objects.filter(
                organization=org, is_active=True
            ).values_list("label", flat=True)
            choices = [("", "-- Select academic year --")] + [(y, y) for y in years]
            current = getattr(self.instance, "academic_year", None)
            if current and current not in [c[0] for c in choices]:
                choices.append((current, f"{current} (inactive)"))
            self.fields["academic_year"].choices = choices

    def clean_academic_year(self):
        raw = (self.cleaned_data.get("academic_year") or "").strip()
        m = re.match(r"^(\d{4})\s*-\s*(\d{2,4})$", raw)
        if not m:
            raise ValidationError("Use the format 2025-2026.")
        start = int(m.group(1))
        end_raw = m.group(2)
        end = int(end_raw) if len(end_raw) == 4 else int(str(start)[:2] + end_raw)
        if end != start + 1:
            raise ValidationError("The end year must be the start year + 1.")
        return f"{start}-{end}"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("override_amounts") and not cleaned.get("net_amount"):
            self.add_error("net_amount", "Enter the net amount when overriding.")
        return cleaned


class PaymentReceiptForm(forms.ModelForm):
    class Meta:
        model = PaymentReceipt
        fields = ["amount", "received_on", "mode", "note"]
        widgets = {
            "received_on": forms.DateInput(attrs={"type": "date"}),
            "mode": forms.TextInput(attrs={"placeholder": "NEFT / UPI / Cheque"}),
            "note": forms.TextInput(attrs={"placeholder": "Optional note"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["received_on"].initial = timezone.localdate()


class IncomeImportForm(forms.Form):
    file = forms.FileField(label="Excel file (.xlsx)")
    dry_run = forms.BooleanField(
        label="Preview only (don't save)", required=False, initial=True
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        ext = _extension(f.name or "")
        if ext in EXECUTABLE_EXTENSIONS:
            raise ValidationError("Executable files are not allowed.")
        if ext == ".ods":
            raise ValidationError(
                "Please re-save the sheet as .xlsx (File > Save As in Excel/"
                "LibreOffice) - .ods cannot be read directly."
            )
        if ext not in EXCEL_EXTENSIONS or ext == ".xls":
            raise ValidationError("Please upload a .xlsx file.")
        return f


# ---------------------------------------------------------------------------
# Implementation tracking
# ---------------------------------------------------------------------------
from .models import ClientOnboarding, FeatureStatus


ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}


class ClientOnboardingForm(forms.ModelForm):
    po_upload = forms.FileField(required=False, label="Upload PO document")
    remove_po_document = forms.BooleanField(required=False, label="Remove PO document")
    agreement_upload = forms.FileField(required=False, label="Upload Agreement document")
    remove_agreement_document = forms.BooleanField(required=False, label="Remove Agreement document")

    class Meta:
        model = ClientOnboarding
        fields = [
            "stage",
            "contact_person", "contact_designation", "contact_phone",
            "contact_email", "institution_type", "address", "city",
            "student_strength", "onboarded_on", "go_live_date", "engineer",
            "po_received", "po_number", "po_date",
            "agreement_signed", "agreement_years", "agreement_start",
            "agreement_end", "reminder_days",
            "notes",
        ]
        widgets = {
            "engineer": forms.TextInput(attrs={
                "list": "engineer-options",
                "placeholder": "Pick or type a new engineer",
            }),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "onboarded_on": forms.DateInput(attrs={"type": "date"}),
            "go_live_date": forms.DateInput(attrs={"type": "date"}),
            "po_date": forms.DateInput(attrs={"type": "date"}),
            "agreement_start": forms.DateInput(attrs={"type": "date"}),
            "agreement_end": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "agreement_end": "Leave blank to auto-compute from start date + years.",
            "reminder_days": "Show an expiry reminder this many days before the end date.",
        }

    def clean_po_upload(self):
        f = self.cleaned_data.get("po_upload")
        if f:
            ext = ("." + f.name.rsplit(".", 1)[-1]).lower() if "." in f.name else ""
            if ext not in ALLOWED_DOC_EXTENSIONS:
                raise ValidationError(f"Allowed: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}")
            if f.size > 10 * 1024 * 1024:
                raise ValidationError("File must be under 10 MB.")
        return f

    def clean_agreement_upload(self):
        f = self.cleaned_data.get("agreement_upload")
        if f:
            ext = ("." + f.name.rsplit(".", 1)[-1]).lower() if "." in f.name else ""
            if ext not in ALLOWED_DOC_EXTENSIONS:
                raise ValidationError(f"Allowed: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}")
            if f.size > 10 * 1024 * 1024:
                raise ValidationError("File must be under 10 MB.")
        return f

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("agreement_start")
        end = cleaned.get("agreement_end")
        if start and end and end <= start:
            self.add_error("agreement_end", "End date must be after the start date.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        po_file = self.cleaned_data.get("po_upload")
        if po_file:
            instance.po_document = po_file.read()
            instance.po_filename = po_file.name
        elif self.cleaned_data.get("remove_po_document"):
            instance.po_document = None
            instance.po_filename = ""

        agr_file = self.cleaned_data.get("agreement_upload")
        if agr_file:
            instance.agreement_document = agr_file.read()
            instance.agreement_filename = agr_file.name
        elif self.cleaned_data.get("remove_agreement_document"):
            instance.agreement_document = None
            instance.agreement_filename = ""

        if commit:
            instance.save()
        return instance


class FeatureAddForm(forms.ModelForm):
    class Meta:
        model = FeatureStatus
        fields = ["name", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Feature / module name"}),
        }
