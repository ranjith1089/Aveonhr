"""Forms for the staff-only Aveon Income module."""
from __future__ import annotations

import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .forms import EXCEL_EXTENSIONS, EXECUTABLE_EXTENSIONS, _extension
from .models import ClientBilling, IncomeClient, PaymentReceipt


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
            "academic_year": forms.TextInput(attrs={"placeholder": "2025-2026"}),
            # Free text + datalist: pick an existing engineer or type a new name.
            "engineer": forms.TextInput(attrs={
                "list": "engineer-options",
                "placeholder": "Pick or type a new engineer",
            }),
            "remarks": forms.Textarea(attrs={"rows": 2}),
            "next_followup_date": forms.DateInput(attrs={"type": "date"}),
        }

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


class ClientOnboardingForm(forms.ModelForm):
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

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("agreement_start")
        end = cleaned.get("agreement_end")
        if start and end and end <= start:
            self.add_error("agreement_end", "End date must be after the start date.")
        return cleaned


class FeatureAddForm(forms.ModelForm):
    class Meta:
        model = FeatureStatus
        fields = ["name", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Feature / module name"}),
        }
