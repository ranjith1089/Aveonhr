"""Provision an Organization + admin Membership for every existing user,
copying their CompanyProfile branding into the new org.

Idempotent: users that already have a membership are skipped, so re-running
(or running after new signups already created memberships) is safe.
"""
from django.db import migrations


def copy_profiles_to_orgs(apps, schema_editor):
    User = apps.get_model("auth", "User")
    CompanyProfile = apps.get_model("payslip", "CompanyProfile")
    Organization = apps.get_model("payslip", "Organization")
    Membership = apps.get_model("payslip", "Membership")

    BRANDING_FIELDS = [
        "company_name", "tagline", "address", "city", "state", "country",
        "email", "phone", "website", "jurisdiction", "logo_content_type",
        "brand_primary", "brand_accent", "signatory_name",
        "signatory_designation",
    ]

    for user in User.objects.order_by("date_joined", "pk"):
        if Membership.objects.filter(user=user).exists():
            continue
        profile = CompanyProfile.objects.filter(user=user).first()
        org_kwargs = {}
        if profile is not None:
            org_kwargs = {f: getattr(profile, f) for f in BRANDING_FIELDS}
            # psycopg returns memoryview for BinaryField on Postgres.
            org_kwargs["logo"] = bytes(profile.logo) if profile.logo else None
        org_kwargs["company_name"] = org_kwargs.get("company_name") or user.username
        org = Organization.objects.create(**org_kwargs)
        Membership.objects.create(
            user=user, organization=org, role="ADMIN",
            can_payslips=True, can_offer_letters=True,
            can_experience_certificates=True, can_travel_expense=True,
            can_proposals=True, can_income=True, can_implementation=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payslip", "0005_organization_membership"),
    ]

    operations = [
        migrations.RunPython(copy_profiles_to_orgs, migrations.RunPython.noop),
    ]
