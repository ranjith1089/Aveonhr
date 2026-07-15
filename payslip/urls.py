from django.urls import include, path

from . import views_implementation, views_income, views_team
from .views import (
    cms_feature_list,
    company_profile,
    download_file,
    experience_certificate,
    landing,
    offer_letter,
    preview_pdf,
    profile_logo,
    signup,
    travel_expense,
    upload_payslips,
    proposal_quotation,
)

urlpatterns = [
    path("", landing, name="landing"),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("profile/", company_profile, name="company_profile"),
    path("profile/logo/", profile_logo, name="profile_logo"),
    # --- Team management (org admins) ---
    path("team/", views_team.team, name="team"),
    path("team/add/", views_team.team_add_member, name="team_add_member"),
    path("team/<int:user_id>/toggle/", views_team.team_toggle_member, name="team_toggle_member"),
    path("offer-letter/", offer_letter, name="offer_letter"),
    path("experience-certificate/", experience_certificate, name="experience_certificate"),
    path("travel-expense/", travel_expense, name="travel_expense"),
    path("payslip/", upload_payslips, name="upload_payslips"),
    path("proposal-quotation/", proposal_quotation, name="proposal_quotation"),
    path("proposal-quotation/cms-features/", cms_feature_list, name="cms_feature_list"),
    path("preview/<str:token>/", preview_pdf, name="preview_pdf"),
    path("download/<str:token>/", download_file, name="download_file"),
    # --- Income module (staff-only) ---
    path("income/", views_income.income_dashboard, name="income_dashboard"),
    path("income/analytics/", views_income.income_analytics, name="income_analytics"),
    path("income/clients/", views_income.income_client_list, name="income_client_list"),
    path("income/clients/new/", views_income.income_client_create, name="income_client_create"),
    path("income/clients/<int:pk>/", views_income.income_client_detail, name="income_client_detail"),
    path("income/clients/<int:pk>/edit/", views_income.income_client_edit, name="income_client_edit"),
    path("income/clients/<int:pk>/billing/new/", views_income.income_billing_create, name="income_billing_create"),
    path("income/billing/<int:pk>/edit/", views_income.income_billing_edit, name="income_billing_edit"),
    path("income/billing/<int:pk>/payments/add/", views_income.income_payment_add, name="income_payment_add"),
    path("income/payments/<int:pk>/delete/", views_income.income_payment_delete, name="income_payment_delete"),
    path("income/implementation/", views_implementation.implementation_dashboard, name="implementation_dashboard"),
    path("income/clients/<int:pk>/implementation/", views_implementation.client_implementation, name="client_implementation"),
    path("income/export.xlsx", views_income.income_export, name="income_export"),
    path("income/import/", views_income.income_import, name="income_import"),
]

