"""Assign the existing (previously global) income ledger to one organization.

Rule: the org of the earliest is_staff user - the ledger predates
multi-tenancy and belonged to the Aveon team, whose accounts are the staff
ones. Falls back to the earliest membership; fails loudly rather than leave
an orphaned ledger.
"""
from django.db import migrations


def assign_income_org(apps, schema_editor):
    IncomeClient = apps.get_model("payslip", "IncomeClient")
    if not IncomeClient.objects.filter(organization__isnull=True).exists():
        return

    User = apps.get_model("auth", "User")
    Membership = apps.get_model("payslip", "Membership")

    org = None
    staff = User.objects.filter(is_staff=True).order_by("date_joined", "pk").first()
    if staff is not None:
        m = Membership.objects.filter(user=staff).first()
        if m is not None:
            org = m.organization
    if org is None:
        m = Membership.objects.order_by("created_at", "pk").first()
        org = m.organization if m is not None else None
    if org is None:
        raise RuntimeError(
            "Income clients exist but no organization membership was found - "
            "run migration 0006 first."
        )

    IncomeClient.objects.filter(organization__isnull=True).update(organization=org)


class Migration(migrations.Migration):

    dependencies = [
        ("payslip", "0006_copy_profiles_to_orgs"),
        ("payslip", "0007_incomeclient_organization"),
    ]

    operations = [
        migrations.RunPython(assign_income_org, migrations.RunPython.noop),
    ]
