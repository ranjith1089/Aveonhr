from django.urls import include, path

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
    path("offer-letter/", offer_letter, name="offer_letter"),
    path("experience-certificate/", experience_certificate, name="experience_certificate"),
    path("travel-expense/", travel_expense, name="travel_expense"),
    path("payslip/", upload_payslips, name="upload_payslips"),
    path("proposal-quotation/", proposal_quotation, name="proposal_quotation"),
    path("proposal-quotation/cms-features/", cms_feature_list, name="cms_feature_list"),
    path("preview/<str:token>/", preview_pdf, name="preview_pdf"),
    path("download/<str:token>/", download_file, name="download_file"),
]

