from django.contrib import admin

from .models import GeneratedFile, Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("company_name", "email", "phone", "created_at")
    search_fields = ("company_name", "email")
    readonly_fields = ("created_at", "updated_at")
    exclude = ("logo",)  # binary blob - not editable in admin


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "can_income",
                    "can_implementation", "updated_at")
    list_filter = ("role", "can_income", "can_implementation")
    search_fields = ("user__username", "user__email", "organization__company_name")


@admin.register(GeneratedFile)
class GeneratedFileAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "filename", "content_type", "created_at")
    search_fields = ("user__username", "filename")
    readonly_fields = ("token", "user", "content_type", "filename", "created_at")
    exclude = ("content",)

    def has_add_permission(self, request):
        return False


from .models import AcademicYear, ClientBilling, IncomeClient, PaymentReceipt


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("label", "organization", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("label",)


class ClientBillingInline(admin.TabularInline):
    model = ClientBilling
    extra = 0
    fields = ("academic_year", "student_count", "rate", "net_amount",
              "previous_pending", "engineer", "invoice_status")
    readonly_fields = ("net_amount",)


class PaymentReceiptInline(admin.TabularInline):
    model = PaymentReceipt
    extra = 0


@admin.register(IncomeClient)
class IncomeClientAdmin(admin.ModelAdmin):
    list_display = ("name", "agreement_status", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [ClientBillingInline]


@admin.register(ClientBilling)
class ClientBillingAdmin(admin.ModelAdmin):
    list_display = ("client", "academic_year", "net_amount", "previous_pending",
                    "engineer", "invoice_status", "next_followup_date")
    list_filter = ("academic_year", "engineer", "invoice_status")
    search_fields = ("client__name",)
    readonly_fields = ("year_start",)
    inlines = [PaymentReceiptInline]


@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ("billing", "amount", "received_on", "mode")
    search_fields = ("billing__client__name",)


from .models import ClientOnboarding, FeatureStatus


@admin.register(ClientOnboarding)
class ClientOnboardingAdmin(admin.ModelAdmin):
    list_display = ("client", "stage", "engineer", "po_received",
                    "agreement_signed", "agreement_end")
    list_filter = ("stage", "po_received", "agreement_signed")
    search_fields = ("client__name", "contact_person", "city")
    readonly_fields = ("created_at", "updated_at")


@admin.register(FeatureStatus)
class FeatureStatusAdmin(admin.ModelAdmin):
    list_display = ("client", "name", "status", "engineer", "completed_on")
    list_filter = ("status", "engineer")
    search_fields = ("client__name", "name")


from .models import ProposalRecord


@admin.register(ProposalRecord)
class ProposalRecordAdmin(admin.ModelAdmin):
    list_display = ("client_name", "revision", "organization", "selection_label",
                    "total_amount", "created_by", "created_at")
    list_filter = ("organization",)
    search_fields = ("client_name",)
    readonly_fields = ("created_at",)
    exclude = ("html",)  # large blob - viewable via the app's history pages


from .models import Person, PersonDocument


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "designation", "stage",
                    "source", "updated_at")
    list_filter = ("kind", "organization", "stage", "source")
    search_fields = ("name", "email", "employee_no", "roll_number")
    readonly_fields = ("created_at", "updated_at")


from .models import InterviewRound, JobOpening


@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "department", "positions", "status",
                    "created_at")
    list_filter = ("status", "organization")
    search_fields = ("title", "department")


@admin.register(InterviewRound)
class InterviewRoundAdmin(admin.ModelAdmin):
    list_display = ("person", "round_name", "interviewer", "result", "scheduled_at")
    list_filter = ("result",)
    search_fields = ("person__name", "round_name", "interviewer")


@admin.register(PersonDocument)
class PersonDocumentAdmin(admin.ModelAdmin):
    list_display = ("person", "doc_type", "organization", "created_by", "created_at")
    list_filter = ("doc_type", "organization")
    search_fields = ("person__name",)
    readonly_fields = ("created_at",)
    exclude = ("pdf", "pdf_plain")  # binary blobs - download via the app


from .models import Employee, PayrollRun, PayrollSettings, PayslipEntry


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "employee_code", "organization", "department",
                    "designation", "current_monthly_package", "employment_status",
                    "is_active")
    list_filter = ("organization", "is_active", "employment_status", "is_esi_eligible")
    search_fields = ("name", "employee_code", "department", "official_email",
                     "personal_email", "aadhar_no")
    readonly_fields = ("created_at", "updated_at")
    exclude = ("photo",)


@admin.register(PayrollSettings)
class PayrollSettingsAdmin(admin.ModelAdmin):
    list_display = ("organization", "basic_percent_of_package", "esi_wage_ceiling", "pf_wage_cap")


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("organization", "period", "status", "finalized_at")
    list_filter = ("organization", "status")


@admin.register(PayslipEntry)
class PayslipEntryAdmin(admin.ModelAdmin):
    list_display = ("employee", "run", "gross_salary", "net_payable", "ctc")
    list_filter = ("run__organization", "run__status")
    search_fields = ("employee__name",)
    exclude = ("pdf", "pdf_plain")


from .models import (PayslipComponentAmount, SalaryComponent, SalaryStructure,
                     StructureChangeLog)


class SalaryComponentInline(admin.TabularInline):
    model = SalaryComponent
    extra = 0
    fields = ("sequence", "code", "name", "kind", "calc_method", "formula",
              "rounding", "decimals", "include_in_gross", "is_active")


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ("label", "organization", "effective_from", "is_active")
    list_filter = ("organization", "is_active")
    inlines = [SalaryComponentInline]


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "calc_method", "structure", "sequence")
    list_filter = ("kind", "calc_method", "structure__organization")
    search_fields = ("code", "name")


@admin.register(PayslipComponentAmount)
class PayslipComponentAmountAdmin(admin.ModelAdmin):
    list_display = ("entry", "code", "kind", "amount")
    search_fields = ("code", "entry__employee__name")


@admin.register(StructureChangeLog)
class StructureChangeLogAdmin(admin.ModelAdmin):
    list_display = ("action", "organization", "structure", "user", "created_at")
    list_filter = ("organization",)
    readonly_fields = ("created_at",)
