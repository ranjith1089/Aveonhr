"""
SaaS data model: organizations (tenant + branding for every generated
document), memberships with per-module rights, the org-scoped income /
implementation ledger, proposal history, and the database-backed store for
generated files (survives serverless instances).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


def _new_token() -> str:
    return uuid.uuid4().hex


class GeneratedFile(models.Model):
    """A generated document (PDF/HTML/ZIP) addressable by token.

    Owner-scoped: preview/download only serve a file to the user who
    generated it. Rows are transient - old ones are cleaned up
    opportunistically on each save (24h retention).
    """

    token = models.CharField(max_length=32, primary_key=True, default=_new_token)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_files",
    )
    content = models.BinaryField()
    content_type = models.CharField(max_length=100)
    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.filename} ({self.token[:8]})"


# ---------------------------------------------------------------------------
# Organizations - users are grouped under one org; the org owns branding and
# the Income/Implementation ledger; org admins grant per-module rights.
# ---------------------------------------------------------------------------
class Organization(models.Model):
    """A tenant. Field names intentionally mirror CompanyProfile so
    CompanyBranding.from_profile() and ProfilePrefillMixin work unchanged."""

    company_name = models.CharField(max_length=200, blank=True, default="")
    tagline = models.CharField(max_length=200, blank=True, default="")
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="India")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    website = models.CharField(max_length=200, blank=True, default="")
    jurisdiction = models.CharField(max_length=200, blank=True, default="")
    logo = models.BinaryField(null=True, blank=True, editable=True)
    logo_content_type = models.CharField(max_length=50, blank=True, default="")
    brand_primary = models.CharField(max_length=7, default="#1565C0")
    brand_accent = models.CharField(max_length=7, default="#2E7D32")
    signatory_name = models.CharField(max_length=200, blank=True, default="")
    signatory_designation = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.company_name or f"Organization #{self.pk}"

    @property
    def logo_bytes(self) -> bytes | None:
        if not self.logo:
            return None
        return bytes(self.logo)  # psycopg may return memoryview


class Membership(models.Model):
    """A user's place in an organization: role + per-module rights.

    Admins bypass the module toggles and manage the team; members only see
    the modules an admin has switched on for them.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MEMBER = "MEMBER", "Member"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    # Document tools default on; the internal money modules default off.
    can_payslips = models.BooleanField("Payslips", default=True)
    can_offer_letters = models.BooleanField("Offer Letters", default=True)
    can_experience_certificates = models.BooleanField("Experience Certificates", default=True)
    can_travel_expense = models.BooleanField("Travel Expense", default=True)
    can_proposals = models.BooleanField("Proposals", default=True)
    can_income = models.BooleanField("Income", default=False)
    can_implementation = models.BooleanField("Implementation", default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    MODULE_FIELDS = {
        "payslips": "can_payslips",
        "offer_letters": "can_offer_letters",
        "experience_certificates": "can_experience_certificates",
        "travel_expense": "can_travel_expense",
        "proposals": "can_proposals",
        "income": "can_income",
        "implementation": "can_implementation",
    }

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user} @ {self.organization} ({self.role})"

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    def has_module(self, module: str) -> bool:
        if self.is_admin:
            return True
        return bool(getattr(self, self.MODULE_FIELDS[module]))


def membership_for(user) -> Membership:
    """The user's membership, auto-provisioned like profile_for.

    Users created outside signup (createsuperuser, legacy rows, shell) get
    their own single-member org and become its admin.
    """
    try:
        return user.membership
    except Membership.DoesNotExist:
        org = Organization.objects.create(company_name="")
        return Membership.objects.create(
            user=user, organization=org, role=Membership.Role.ADMIN
        )


def org_for(user) -> Organization:
    return membership_for(user).organization


# ---------------------------------------------------------------------------
# Aveon Income module - client payment follow-up (replaces the ODS sheet).
#
# NOTE: unlike GeneratedFile these models are ORG-WIDE, not
# per-user: every staff member sees the same ledger. Access is enforced at
# the view layer (staff-only).
# ---------------------------------------------------------------------------
from decimal import Decimal, ROUND_HALF_UP

TWO_DP = Decimal("0.01")
GST_RATE = Decimal("0.18")

ENGINEER_CHOICES = [(n, n) for n in (
    "Balachandhar", "Kalai", "Mullai", "Naveen Prasath", "Selladurai",
    "Naveen R", "Suresh", "Kariyappan", "Dharun",
)]


class IncomeClient(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT,
        related_name="income_clients",
    )
    name = models.CharField(max_length=200)
    agreement_status = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)  # False = client discontinued
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    @property
    def total_balance(self) -> Decimal:
        return sum((b.balance for b in self.billings.all()), Decimal("0"))

    @property
    def latest_engineer(self) -> str:
        latest = max(self.billings.all(), key=lambda b: b.year_start, default=None)
        return latest.engineer if latest else ""


class ClientBilling(models.Model):
    """One sheet row: a client's billing for one academic year."""

    class InvoiceStatus(models.TextChoices):
        PROFORMA = "PROFORMA", "Proforma invoice generated"
        ALREADY_SENT = "ALREADY_SENT", "Proforma invoice sent"
        TAX_SENT = "TAX_SENT", "Tax invoice sent"
        NOT_NEEDED = "NOT_NEEDED", "Invoice not needed"
        WAITING = "WAITING", "Waiting"

    client = models.ForeignKey(IncomeClient, on_delete=models.CASCADE, related_name="billings")
    academic_year = models.CharField(
        max_length=9,
        validators=[RegexValidator(r"^\d{4}-\d{4}$", "Use the format 2024-2025.")],
    )
    # Derived int for all sorting/FY grouping - string sort breaks on typos.
    year_start = models.PositiveSmallIntegerField(db_index=True, editable=False, default=0)

    student_count = models.PositiveIntegerField(null=True, blank=True)
    rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    one_time_payment = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # Fixed-fee escape hatch: when True the manual amounts below are stored
    # untouched (e.g. "Per Year 850000" clients, GST-inclusive lump sums).
    override_amounts = models.BooleanField(default=False)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    gst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    # Stored + editable, never auto-cascaded (see plan: carry-forward drift
    # stays visible via a mismatch badge instead of silent rewrites).
    previous_pending = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    # Free text with datalist suggestions in the form - new engineers can be
    # added by simply typing a new name (ENGINEER_CHOICES seeds suggestions).
    engineer = models.CharField(max_length=50, blank=True, default="")
    invoice_status = models.CharField(
        max_length=20, choices=InvoiceStatus.choices, blank=True, default=""
    )
    remarks = models.TextField(blank=True, default="")
    next_followup_date = models.DateField(null=True, blank=True, db_index=True)
    followup_note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("client", "academic_year")]
        ordering = ["client__name", "year_start"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.client.name} {self.academic_year}"

    def save(self, *args, **kwargs):
        if not self.override_amounts:
            if self.student_count and self.rate is not None:
                self.taxable_value = (Decimal(self.student_count) * self.rate).quantize(
                    TWO_DP, rounding=ROUND_HALF_UP
                )
            if self.taxable_value is not None:
                self.gst_amount = (self.taxable_value * GST_RATE).quantize(
                    TWO_DP, rounding=ROUND_HALF_UP
                )
                self.net_amount = self.taxable_value + self.gst_amount + self.one_time_payment
        self.year_start = int(self.academic_year[:4]) if self.academic_year[:4].isdigit() else 0
        super().save(*args, **kwargs)

    @property
    def received_total(self) -> Decimal:
        # Fast paths first - avoids an N+1 query per row on list pages:
        # 1) `received_sum` annotation (dashboard/analytics/export querysets)
        received_sum = getattr(self, "received_sum", None)
        if received_sum is not None:
            return received_sum
        # 2) prefetched payments (client list/detail querysets)
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "payments" in cache:
            return sum((p.amount for p in self.payments.all()), Decimal("0"))
        # 3) fallback: single aggregate query
        agg = self.payments.aggregate(total=models.Sum("amount"))
        return agg["total"] or Decimal("0")

    @property
    def total_due(self) -> Decimal:
        return (self.net_amount or Decimal("0")) + (self.previous_pending or Decimal("0"))

    @property
    def balance(self) -> Decimal:
        return self.total_due - self.received_total

    @property
    def followup_overdue(self) -> bool:
        from django.utils import timezone
        return bool(self.next_followup_date and self.next_followup_date <= timezone.localdate())


class PaymentReceipt(models.Model):
    billing = models.ForeignKey(ClientBilling, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    received_on = models.DateField(null=True, blank=True)  # null: imported opening figure
    mode = models.CharField(max_length=50, blank=True, default="")
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.billing} + {self.amount}"


# ---------------------------------------------------------------------------
# Implementation tracking - onboarding, PO, agreement reminders and
# feature-wise delivery status per Income client (staff-only, org-wide).
# ---------------------------------------------------------------------------
class ClientOnboarding(models.Model):
    class Stage(models.TextChoices):
        ONBOARDING = "ONBOARDING", "Onboarding"
        IMPLEMENTATION = "IMPLEMENTATION", "Implementation"
        LIVE = "LIVE", "Live"
        ON_HOLD = "ON_HOLD", "On hold"
        DISCONTINUED = "DISCONTINUED", "Discontinued"

    class InstitutionType(models.TextChoices):
        COLLEGE = "COLLEGE", "College"
        SCHOOL = "SCHOOL", "School"
        UNIVERSITY = "UNIVERSITY", "University"
        POLYTECHNIC = "POLYTECHNIC", "Polytechnic"
        OTHER = "OTHER", "Other"

    client = models.OneToOneField(IncomeClient, on_delete=models.CASCADE,
                                  related_name="onboarding")
    stage = models.CharField(max_length=20, choices=Stage.choices,
                             default=Stage.ONBOARDING)

    # Full client details
    contact_person = models.CharField(max_length=200, blank=True, default="")
    contact_designation = models.CharField(max_length=200, blank=True, default="")
    contact_phone = models.CharField(max_length=30, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    institution_type = models.CharField(max_length=20, choices=InstitutionType.choices,
                                        blank=True, default="")
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    student_strength = models.PositiveIntegerField(null=True, blank=True)
    onboarded_on = models.DateField(null=True, blank=True)
    go_live_date = models.DateField(null=True, blank=True)
    engineer = models.CharField(max_length=50, blank=True, default="")

    # Purchase order
    po_received = models.BooleanField(default=False)
    po_number = models.CharField(max_length=100, blank=True, default="")
    po_date = models.DateField(null=True, blank=True)

    # Agreement
    agreement_signed = models.BooleanField(default=False)
    agreement_years = models.PositiveSmallIntegerField(null=True, blank=True)
    agreement_start = models.DateField(null=True, blank=True)
    agreement_end = models.DateField(null=True, blank=True)
    reminder_days = models.PositiveSmallIntegerField(default=90)

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Onboarding: {self.client.name}"

    def save(self, *args, **kwargs):
        # Auto-compute the agreement end date from start + years when the
        # end is not set explicitly (an explicit end always wins).
        if self.agreement_start and self.agreement_years and not self.agreement_end:
            try:
                self.agreement_end = self.agreement_start.replace(
                    year=self.agreement_start.year + self.agreement_years
                )
            except ValueError:  # Feb 29 -> Feb 28
                self.agreement_end = self.agreement_start.replace(
                    year=self.agreement_start.year + self.agreement_years, day=28
                )
        super().save(*args, **kwargs)

    @property
    def days_to_expiry(self) -> int | None:
        if not self.agreement_end:
            return None
        from django.utils import timezone
        return (self.agreement_end - timezone.localdate()).days

    @property
    def agreement_expired(self) -> bool:
        d = self.days_to_expiry
        return d is not None and d < 0

    @property
    def agreement_expiring(self) -> bool:
        d = self.days_to_expiry
        return d is not None and 0 <= d <= self.reminder_days

    @property
    def agreement_label(self) -> str:
        if not self.agreement_signed:
            return "Agreement pending"
        if self.agreement_expired:
            return f"Expired {abs(self.days_to_expiry)}d ago"
        if self.agreement_expiring:
            return f"Expires in {self.days_to_expiry}d"
        if self.agreement_end:
            return f"Valid till {self.agreement_end:%d %b %Y}"
        return "Signed"


def onboarding_for(client: IncomeClient) -> ClientOnboarding:
    onboarding, _ = ClientOnboarding.objects.get_or_create(client=client)
    return onboarding


class FeatureStatus(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        TESTING = "TESTING", "Testing"
        LIVE = "LIVE", "Live"
        ON_HOLD = "ON_HOLD", "On hold"
        NA = "NA", "N.A."

    client = models.ForeignKey(IncomeClient, on_delete=models.CASCADE,
                               related_name="features")
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.NOT_STARTED)
    engineer = models.CharField(max_length=50, blank=True, default="")
    started_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    remarks = models.CharField(max_length=300, blank=True, default="")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("client", "name")]
        ordering = ["order", "id"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.client.name}: {self.name} ({self.status})"


def feature_progress(features) -> dict:
    """Live percent over applicable (non-N.A.) features."""
    items = list(features)
    applicable = [f for f in items if f.status != FeatureStatus.Status.NA]
    live = [f for f in applicable if f.status == FeatureStatus.Status.LIVE]
    total = len(applicable)
    return {
        "total": len(items),
        "applicable": total,
        "live": len(live),
        "pct": int(len(live) / total * 100) if total else 0,
    }


# ---------------------------------------------------------------------------
# Proposal history - every generated proposal is kept, org-scoped, with a
# revision chain per client (regenerate -> Rev 2, Rev 3, ...). The rendered
# HTML is stored verbatim so history shows exactly what was sent, even after
# the catalog text changes.
# ---------------------------------------------------------------------------
class ProposalRecord(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                     related_name="proposals")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, related_name="+")
    client_name = models.CharField(max_length=200, db_index=True)
    revision = models.PositiveIntegerField(default=1)

    # Snapshot of the validated form (dates/decimals as strings) - prefills
    # the builder for the next revision. client_logo is not restorable.
    form_data = models.JSONField(default=dict, blank=True)
    html = models.TextField()

    # Denormalized for list display.
    selection_label = models.CharField(max_length=200, blank=True, default="")
    total_amount = models.DecimalField(max_digits=14, decimal_places=2,
                                       null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("organization", "client_name", "revision")]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.client_name} (Rev {self.revision})"


def next_proposal_revision(organization, client_name: str) -> int:
    agg = ProposalRecord.objects.filter(
        organization=organization, client_name=client_name
    ).aggregate(max_rev=models.Max("revision"))
    return (agg["max_rev"] or 0) + 1
