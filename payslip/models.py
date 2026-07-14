"""
SaaS data model: per-user company profile (branding for every generated
document) and the database-backed store for generated files (replaces the
in-memory cache, which does not survive serverless instances).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


def _new_token() -> str:
    return uuid.uuid4().hex


class CompanyProfile(models.Model):
    """One company identity per user - prefills forms and brands PDFs.

    Every field is optional: blank fields fall back to the built-in
    (Aveon) defaults, so a half-filled profile degrades gracefully.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_profile",
    )
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
        return self.company_name or f"Profile of {self.user}"

    @property
    def logo_bytes(self) -> bytes | None:
        if not self.logo:
            return None
        return bytes(self.logo)  # psycopg may return memoryview


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


def profile_for(user) -> CompanyProfile:
    """The user's profile, created on first access (pre-auth users, superusers)."""
    profile, _ = CompanyProfile.objects.get_or_create(user=user)
    return profile


# ---------------------------------------------------------------------------
# Aveon Income module - client payment follow-up (replaces the ODS sheet).
#
# NOTE: unlike CompanyProfile/GeneratedFile these models are ORG-WIDE, not
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
    name = models.CharField(max_length=200, unique=True)
    agreement_status = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)  # False = client discontinued
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

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
