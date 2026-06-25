from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from .proposal_catalog import BUNDLES, bundle_choices, module_choices

EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".sh",
    ".ps1",
    ".vbs",
    ".js",
    ".jar",
    ".msi",
    ".com",
    ".scr",
    ".apk",
    ".app",
    ".bin",
    ".dll",
}

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _extension(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


class PayslipUploadForm(forms.Form):
    company_name = forms.CharField(
        label="Company Name", 
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Enter company name", "class": "form-input"})
    )
    company_address = forms.CharField(
        label="Company Address", 
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Enter full address", "class": "form-input"})
    )
    company_email = forms.EmailField(
        label="Company Email", 
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "company@example.com", "class": "form-input"})
    )
    company_phone = forms.CharField(
        label="Company Phone", 
        required=False, 
        max_length=40,
        widget=forms.TextInput(attrs={"placeholder": "+91 00000 00000", "class": "form-input"})
    )
    company_logo = forms.ImageField(label="Company Logo", required=False)
    salary_file = forms.FileField(label="Salary Statement (Excel)")

    def clean_salary_file(self):
        file = self.cleaned_data.get("salary_file")
        if not file:
            return file
        filename = file.name or ""
        ext = _extension(filename)
        if ext in EXECUTABLE_EXTENSIONS:
            raise ValidationError("Executable files are not allowed.")
        if ext not in EXCEL_EXTENSIONS:
            raise ValidationError("Please upload a valid Excel file (.xlsx or .xls).")
        return file

    def clean_company_logo(self):
        file = self.cleaned_data.get("company_logo")
        if not file:
            return file
        filename = file.name or ""
        ext = _extension(filename)
        if ext in EXECUTABLE_EXTENSIONS:
            raise ValidationError("Executable files are not allowed.")
        if ext not in IMAGE_EXTENSIONS:
            raise ValidationError("Logo must be a PNG or JPG image.")
        return file


class OfferLetterForm(forms.Form):
    OFFER_TYPES = [
        ("", "-- Select Offer Type --"),
        ("internship", "INTERNSHIP OFFER LETTER"),
        ("appointment", "Appointment Order"),
        ("employment_offer", "OFFER LETTER"),
    ]

    offer_type = forms.ChoiceField(
        label="Offer Letter Type", 
        choices=OFFER_TYPES,
        widget=forms.Select(attrs={'class': 'offer-type-select'})
    )
    
    # Internship/Offer Letter fields
    name = forms.CharField(label="Name", max_length=200, required=False)
    roll_number = forms.CharField(label="Roll Number", max_length=100, required=False)
    course = forms.CharField(label="Course", max_length=200, required=False)
    college_name = forms.CharField(label="College Name", max_length=200, required=False)
    college_address = forms.CharField(
        label="College Address", widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    internship_role = forms.CharField(label="Internship Role", max_length=200, required=False)
    start_date = forms.DateField(
        label="Start Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    
    # Appointment Order fields
    serial_no = forms.CharField(label="Ref No", max_length=100, required=False)
    employee_name = forms.CharField(label="Employee Name", max_length=200, required=False)
    present_address1 = forms.CharField(label="Address Line 1", max_length=200, required=False)
    present_address2 = forms.CharField(label="Address Line 2", max_length=200, required=False)
    present_address3 = forms.CharField(label="Address Line 3", max_length=200, required=False)
    present_address_city = forms.CharField(label="City", max_length=100, required=False)
    present_address_state = forms.CharField(label="State", max_length=100, required=False)
    present_address_pin = forms.CharField(label="PIN Code", max_length=20, required=False)
    designation = forms.CharField(label="Designation", max_length=200, required=False)
    join_date = forms.DateField(
        label="Joining Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    probation_period = forms.CharField(label="Probation Period (days)", max_length=50, required=False)
    ctc = forms.CharField(label="CTC (in words)", max_length=500, required=False)
    company_name = forms.CharField(label="Company Name", max_length=200, required=False)
    signatory = forms.CharField(label="Signatory Name", max_length=200, required=False)
    signatory_designation = forms.CharField(label="Signatory Designation", max_length=200, required=False)
    
    # Employment Offer Letter fields
    candidate_name = forms.CharField(label="Candidate Name", max_length=200, required=False)
    position = forms.CharField(label="Position", max_length=200, required=False)
    annual_ctc = forms.DecimalField(label="Annual CTC (Rs.)", max_digits=12, decimal_places=2, required=False)
    ctc_in_words = forms.CharField(label="CTC in Words", max_length=500, required=False)
    joining_date = forms.DateField(
        label="Joining Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    employer_name = forms.CharField(label="Employer Name", max_length=200, required=False)
    employer_designation = forms.CharField(label="Employer Designation", max_length=200, required=False)
    
    # Compensation breakdown
    basic_monthly = forms.DecimalField(label="Basic (Monthly)", max_digits=12, decimal_places=2, required=False)
    basic_annual = forms.DecimalField(label="Basic (Annual)", max_digits=12, decimal_places=2, required=False)
    da_monthly = forms.DecimalField(label="DA (Monthly)", max_digits=12, decimal_places=2, required=False)
    da_annual = forms.DecimalField(label="DA (Annual)", max_digits=12, decimal_places=2, required=False)
    hra_monthly = forms.DecimalField(label="HRA (Monthly)", max_digits=12, decimal_places=2, required=False)
    hra_annual = forms.DecimalField(label="HRA (Annual)", max_digits=12, decimal_places=2, required=False)
    ta_monthly = forms.DecimalField(label="TA (Monthly)", max_digits=12, decimal_places=2, required=False)
    ta_annual = forms.DecimalField(label="TA (Annual)", max_digits=12, decimal_places=2, required=False)
    food_allowance_monthly = forms.DecimalField(label="Food Allowance (Monthly)", max_digits=12, decimal_places=2, required=False)
    food_allowance_annual = forms.DecimalField(label="Food Allowance (Annual)", max_digits=12, decimal_places=2, required=False)
    pf_employee_monthly = forms.DecimalField(label="PF Employee (Monthly)", max_digits=12, decimal_places=2, required=False)
    pf_employee_annual = forms.DecimalField(label="PF Employee (Annual)", max_digits=12, decimal_places=2, required=False)
    pf_employer_monthly = forms.DecimalField(label="PF Employer (Monthly)", max_digits=12, decimal_places=2, required=False)
    pf_employer_annual = forms.DecimalField(label="PF Employer (Annual)", max_digits=12, decimal_places=2, required=False)


class ExperienceCertificateForm(forms.Form):
    CERTIFICATE_TYPES = [
        ("", "-- Select Certificate Type --"),
        ("employee", "Employee Experience Letter"),
        ("internship", "Internship Experience Certificate"),
    ]
    TITLE_CHOICES = [
        ("Mr.", "Mr."),
        ("Ms.", "Ms."),
        ("Mrs.", "Mrs."),
    ]
    
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
    ]
    
    certificate_type = forms.ChoiceField(
        label="Certificate Type",
        choices=CERTIFICATE_TYPES,
        widget=forms.Select(attrs={"id": "certificate_type"}),
    )

    # Shared
    gender = forms.ChoiceField(label="Gender", choices=GENDER_CHOICES, required=False)
    signatory_exp = forms.CharField(label="Signatory Name", max_length=200, required=False)
    signatory_designation_exp = forms.CharField(label="Signatory Designation", max_length=200, required=False)

    # Employee Experience Letter fields
    title = forms.ChoiceField(label="Title", choices=TITLE_CHOICES, required=False)
    employee_name_exp = forms.CharField(label="Employee Name", max_length=200, required=False)
    employee_no = forms.CharField(label="Employee ID", max_length=100, required=False)
    company_name_exp = forms.CharField(label="Company Name", max_length=200, required=False)
    join_date_exp = forms.DateField(
        label="Joining Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    leaving_date = forms.DateField(
        label="Leaving Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    designation_exp = forms.CharField(label="Designation", max_length=200, required=False)

    # Internship Experience Certificate fields
    intern_name = forms.CharField(label="Intern Name", max_length=200, required=False)
    internship_domain = forms.CharField(
        label="Internship Domain / Department",
        max_length=200,
        required=False,
        help_text="Example: HR & Marketing, Development, Testing",
    )
    internship_company = forms.CharField(
        label="Company / Firm",
        max_length=200,
        required=False,
        initial="Aveon Infotech Private Limited",
    )
    internship_location = forms.CharField(
        label="Location",
        max_length=120,
        required=False,
        initial="CBE",
        help_text="Example: CBE, Coimbatore",
    )
    internship_start_date = forms.DateField(
        label="Internship Start Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )
    internship_end_date = forms.DateField(
        label="Internship End Date", widget=forms.DateInput(attrs={"type": "date"}), required=False
    )

    def clean(self):
        cleaned = super().clean()
        cert_type = (cleaned.get("certificate_type") or "").strip()

        def require(field: str, label: str):
            if not cleaned.get(field):
                self.add_error(field, f"{label} is required.")

        # Common requirements
        if cert_type:
            require("gender", "Gender")
            require("signatory_exp", "Signatory Name")
            require("signatory_designation_exp", "Signatory Designation")

        if cert_type == "employee":
            require("title", "Title")
            require("employee_name_exp", "Employee Name")
            require("employee_no", "Employee ID")
            require("company_name_exp", "Company Name")
            require("join_date_exp", "Joining Date")
            require("leaving_date", "Leaving Date")
            require("designation_exp", "Designation")

        if cert_type == "internship":
            require("intern_name", "Intern Name")
            require("internship_domain", "Internship Domain / Department")
            require("internship_company", "Company / Firm")
            require("internship_location", "Location")
            require("internship_start_date", "Internship Start Date")
            require("internship_end_date", "Internship End Date")

        return cleaned


class TravelExpenseForm(forms.Form):
    # Company Information
    company_name_travel = forms.CharField(label="Company Name", max_length=200)
    company_address_travel = forms.CharField(label="Company Address", max_length=300)
    company_city_state = forms.CharField(label="City, State, ZIP", max_length=200)
    company_country = forms.CharField(label="Country", max_length=100, initial="India")
    
    # Report Information
    report_title = forms.CharField(label="Report Title", max_length=200)
    business_purpose = forms.CharField(
        label="Business Purpose",
        widget=forms.Textarea(attrs={"rows": 3}),
        max_length=500
    )
    submitted_by = forms.CharField(label="Submitted By", max_length=200)
    submitted_on = forms.DateField(
        label="Submitted On", widget=forms.DateInput(attrs={"type": "date"})
    )
    report_to = forms.CharField(label="Report To", max_length=200)
    reporting_period_start = forms.DateField(
        label="Reporting Period Start", widget=forms.DateInput(attrs={"type": "date"})
    )
    reporting_period_end = forms.DateField(
        label="Reporting Period End", widget=forms.DateInput(attrs={"type": "date"})
    )
    
    # Report Number (auto-generated)
    report_number = forms.CharField(label="Report Number", max_length=50, required=False)
    
    # Currency
    report_currency = forms.CharField(label="Report Currency", max_length=10, initial="INR")
    
    # Expense Data (JSON format - will be populated via JavaScript)
    expense_data = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10, "placeholder": "Expense data in JSON format"}),
        required=False
    )


class ProposalQuotationForm(forms.Form):
    """
    Module-wise proposal builder.

    Two selection modes:
        BUNDLE — pick one of the pre-built packages from `BUNDLES`.
        CUSTOM — pick any combination of modules from `MODULES`.

    Pricing per module can be overridden via the hidden `pricing_overrides`
    field (JSON: {module_code: price_per_student}). The form populates this
    from inline inputs in the template's "Custom" mode.
    """

    SELECTION_MODES = [
        ("BUNDLE", "Pre-built Bundle"),
        ("CUSTOM", "Pick Individual Modules"),
    ]

    # --- Addressee block (drives the proposal header) ---------------------
    to_address = forms.CharField(
        label="To (Salutation Line)",
        max_length=200,
        initial="The Principal",
    )
    client_name = forms.CharField(
        label="Client / Institution Name",
        max_length=200,
    )
    client_address = forms.CharField(
        label="Client Address",
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Adhiparasakthi Engineering College,\nMelmaruvathur – 603319,\nChengalpet District, Tamil Nadu",
        }),
        help_text="One line per address line. Will be rendered as-is in the proposal header.",
    )

    proposal_date = forms.DateField(
        label="Proposal Date",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    prepared_by = forms.CharField(
        label="Prepared By",
        max_length=200,
        initial="Aveon Infotech Private Limited",
    )

    # --- Selection: bundle vs custom --------------------------------------
    selection_mode = forms.ChoiceField(
        label="Selection Mode",
        choices=SELECTION_MODES,
        initial="BUNDLE",
        widget=forms.RadioSelect,
    )
    bundle = forms.ChoiceField(
        label="Bundle",
        choices=bundle_choices(),
        required=False,
        initial="CMS_FULL",
    )
    selected_modules = forms.MultipleChoiceField(
        label="Modules",
        choices=module_choices(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    # --- Commercial inputs -------------------------------------------------
    # Single negotiated price — the sales team decides the per-student / per-employee
    # rate per customer (₹250, ₹300, ₹500, etc.). No per-module breakdown is shown
    # in the rendered proposal.
    price_per_unit = forms.DecimalField(
        label="Negotiated Price (INR per student/employee per year)",
        max_digits=12,
        decimal_places=2,
        initial=500,
        min_value=0,
    )
    minimum_student_commitment = forms.IntegerField(
        label="Minimum Commitment (students / employees)",
        min_value=1,
        initial=1000,
    )
    one_time_implementation_fee = forms.DecimalField(
        label="One-Time Implementation Fee (INR)",
        max_digits=12,
        decimal_places=2,
        initial=500000,
    )
    waive_one_time_fee = forms.BooleanField(
        label="Show one-time fee as waived",
        required=False,
        initial=True,
    )
    gst_percent = forms.DecimalField(
        label="GST (%)",
        max_digits=5,
        decimal_places=2,
        initial=18,
    )

    # --- Signature block ---------------------------------------------------
    authorized_signatory_name = forms.CharField(
        label="Authorized Signatory Name",
        max_length=200,
        initial="Parvathi G",
    )
    authorized_signatory_designation = forms.CharField(
        label="Authorized Signatory Designation",
        max_length=200,
        initial="Chief Executive Officer",
    )
    jurisdiction = forms.CharField(
        label="Jurisdiction",
        max_length=200,
        initial="Coimbatore, Tamil Nadu",
        required=False,
    )
    client_logo = forms.ImageField(label="Client Logo (Optional)", required=False)

    # ----------------------------------------------------------------------
    def clean_client_logo(self):
        file = self.cleaned_data.get("client_logo")
        if not file:
            return file
        filename = file.name or ""
        ext = _extension(filename)
        if ext in EXECUTABLE_EXTENSIONS:
            raise ValidationError("Executable files are not allowed.")
        if ext not in IMAGE_EXTENSIONS:
            raise ValidationError("Client logo must be a PNG or JPG image.")
        return file

    def clean(self):
        cleaned = super().clean()

        mode = cleaned.get("selection_mode")
        bundle_code = cleaned.get("bundle")
        modules = cleaned.get("selected_modules") or []

        if mode == "BUNDLE":
            if not bundle_code:
                self.add_error("bundle", "Choose a bundle, or switch to Custom mode.")
            elif bundle_code not in BUNDLES:
                self.add_error("bundle", "Unknown bundle.")
            # In BUNDLE mode, individual selections are ignored — clear them so
            # the view doesn't have to second-guess.
            cleaned["selected_modules"] = []
        elif mode == "CUSTOM":
            if not modules:
                self.add_error(
                    "selected_modules",
                    "Pick at least one module, or switch to Bundle mode.",
                )
            cleaned["bundle"] = ""

        def non_negative(field: str, label: str):
            val = cleaned.get(field)
            if val is None:
                return
            try:
                if Decimal(val) < 0:
                    self.add_error(field, f"{label} cannot be negative.")
            except (InvalidOperation, TypeError):
                self.add_error(field, f"{label} is invalid.")

        non_negative("one_time_implementation_fee", "One-Time Implementation Fee")
        non_negative("gst_percent", "GST (%)")
        return cleaned
