from django.contrib import admin

from .models import CompanyProfile, GeneratedFile


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
