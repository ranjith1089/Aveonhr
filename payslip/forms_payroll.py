"""Forms for the Payroll module."""
from __future__ import annotations

from django import forms

from .models import Employee, PayrollSettings

_DATE = forms.DateInput(attrs={"type": "date"})


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "employee_code", "name", "designation", "doj", "relieving_date",
            "is_active", "current_monthly_package", "is_esi_eligible", "is_pf_applicable",
            "bank_name", "bank_account_number", "ifsc_code", "pan_number",
            "pf_number", "pf_uan", "esi_number", "notes",
        ]
        widgets = {
            "doj": _DATE, "relieving_date": _DATE,
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(self.instance, "organization", None)

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


class PayrollRunCreateForm(forms.Form):
    # <input type="month"> submits "YYYY-MM" (no day) - accept that format
    # explicitly; strptime defaults the missing day to the 1st.
    period = forms.DateField(
        label="Payroll month",
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        help_text="Only the month/year is used.",
    )
