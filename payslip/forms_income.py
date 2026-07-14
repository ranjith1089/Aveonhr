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
