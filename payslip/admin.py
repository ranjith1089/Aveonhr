from django.contrib import admin

from .models import CompanyProfile, GeneratedFile, Membership, Organization


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


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "email", "phone", "updated_at")
    search_fields = ("user__username", "company_name", "email")
    readonly_fields = ("created_at", "updated_at")
    exclude = ("logo",)  # binary blob - not editable in admin


@admin.register(GeneratedFile)
class GeneratedFileAdmin(admin.ModelAdmin):
    list_display = ("token", "user", "filename", "content_type", "created_at")
    search_fields = ("user__username", "filename")
    readonly_fields = ("token", "user", "content_type", "filename", "created_at")
    exclude = ("content",)

    def has_add_permission(self, request):
        return False


from .models import ClientBilling, IncomeClient, PaymentReceipt


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
