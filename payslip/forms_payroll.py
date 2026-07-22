"""Forms for the Payroll module."""
from __future__ import annotations

import re

from django import forms

from .models import Employee, PayrollSettings, SalaryComponent
from .services.formula_engine import FormulaError, validate_formula

_DATE = forms.DateInput(attrs={"type": "date"})


_BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]
_MARITAL = ["Single", "Married", "Divorced", "Widowed"]


class EmployeeForm(forms.ModelForm):
    # Photo lives in the DB; the ImageField takes the upload, save() writes bytes.
    photo_upload = forms.ImageField(required=False, label="Photo")
    remove_photo = forms.BooleanField(required=False, label="Remove photo")

    class Meta:
        model = Employee
        fields = [
            "employee_code", "name", "designation", "department",
            "doj", "relieving_date", "is_active", "employment_status",
            "current_monthly_package", "is_esi_eligible", "is_pf_applicable",
            # personal
            "date_of_birth", "blood_group", "marital_status",
            "parent_spouse_name", "aadhar_no", "address",
            # contact
            "personal_email", "official_email", "contact_no", "official_no",
            "emergency_no",
            # employment / statutory
            "agreement_signed", "agreement_sign_date", "biometric_id",
            "bank_name", "bank_account_number", "ifsc_code", "pan_number",
            "pf_number", "pf_uan", "esi_number",
            # exit
            "reason_for_leaving", "notes",
        ]
        widgets = {
            "doj": _DATE, "relieving_date": _DATE, "date_of_birth": _DATE,
            "agreement_sign_date": _DATE,
            "notes": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "reason_for_leaving": forms.Textarea(attrs={"rows": 2}),
            "blood_group": forms.Select(choices=[("", "—")] + [(g, g) for g in _BLOOD_GROUPS]),
            "marital_status": forms.Select(choices=[("", "—")] + [(m, m) for m in _MARITAL]),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

    def save(self, commit=True):
        employee = super().save(commit=False)
        if self.cleaned_data.get("remove_photo"):
            employee.photo = None
            employee.photo_content_type = ""
        upload = self.cleaned_data.get("photo_upload")
        if upload:
            from io import BytesIO
            from PIL import Image as PilImage
            img = PilImage.open(upload)
            img.load()
            img = img.convert("RGB")
            img.thumbnail((512, 512), PilImage.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            employee.photo = buf.getvalue()
            employee.photo_content_type = "image/jpeg"
        if commit:
            employee.save()
        return employee

    def clean_employee_code(self):
        code = (self.cleaned_data.get("employee_code") or "").strip()
        return code

    def clean(self):
        cleaned = super().clean()
        code = cleaned.get("employee_code")
        if code and self.organization is not None:
            qs = Employee.objects.filter(organization=self.organization,
                                         employee_code__iexact=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("employee_code", "This employee code is already in use.")
        return cleaned


class ConvertToEmployeeForm(forms.ModelForm):
    """Capture the payroll-only fields when converting a candidate (Person)
    into an Employee. Name comes from the Person; the rest is entered here."""

    class Meta:
        model = Employee
        fields = ["employee_code", "designation", "doj",
                  "current_monthly_package", "is_esi_eligible", "is_pf_applicable"]
        widgets = {"doj": _DATE}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["current_monthly_package"].required = True

    def clean_employee_code(self):
        code = (self.cleaned_data.get("employee_code") or "").strip()
        if code and self.organization is not None:
            if Employee.objects.filter(organization=self.organization,
                                       employee_code__iexact=code).exists():
                raise forms.ValidationError("This employee code is already in use.")
        return code


class PayrollSettingsForm(forms.ModelForm):
    class Meta:
        model = PayrollSettings
        fields = [
            "basic_percent_of_package", "da_percent_of_basic", "hra_percent_of_basic",
            "transport_percent_of_basic", "food_percent_of_basic",
            "esi_employee_percent", "esi_employer_percent", "esi_wage_ceiling",
            "pf_employee_percent", "pf_employer_percent", "pf_wage_cap",
            "pf_wage_factor", "pf_employer_matches_employee",
        ]


class SalaryComponentForm(forms.ModelForm):
    """Add/edit one component. `sibling_codes` are the other component codes
    in the same structure, so the formula validator can resolve references."""

    class Meta:
        model = SalaryComponent
        fields = [
            "code", "name", "kind", "calc_method", "amount", "percent",
            "base_code", "formula", "rounding", "decimals", "include_in_gross",
            "is_esi_base", "is_pf_base", "is_taxable", "statutory_type",
            "sequence", "is_active",
        ]
        widgets = {"formula": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, sibling_codes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sibling_codes = set(sibling_codes or set())

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", code or ""):
            raise forms.ValidationError(
                "Code must start with a letter and use only A-Z, 0-9 and _.")
        # A component code must not shadow a context variable name.
        from .services.formula_engine import CONTEXT_VARS
        if code in CONTEXT_VARS:
            raise forms.ValidationError(
                f"'{code}' is a reserved context variable - pick another code.")
        return code

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("calc_method")
        code = cleaned.get("code")
        known = (self.sibling_codes | ({code} if code else set())) - {None}
        if method == SalaryComponent.Method.PERCENT_OF:
            if not cleaned.get("base_code"):
                self.add_error("base_code", "Choose the component this is a percentage of.")
            elif cleaned["base_code"] not in self.sibling_codes:
                self.add_error("base_code", "Unknown base component.")
        elif method == SalaryComponent.Method.FORMULA:
            formula = (cleaned.get("formula") or "").strip()
            if not formula:
                self.add_error("formula", "Enter a formula expression.")
            else:
                try:
                    validate_formula(formula, known)
                except FormulaError as exc:
                    self.add_error("formula", str(exc))
        return cleaned


class PayrollRunCreateForm(forms.Form):
    # <input type="month"> submits "YYYY-MM" (no day) - accept that format
    # explicitly; strptime defaults the missing day to the 1st.
    period = forms.DateField(
        label="Payroll month",
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        help_text="Only the month/year is used.",
    )
