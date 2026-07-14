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
