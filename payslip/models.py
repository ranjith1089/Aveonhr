"""
SaaS data model: per-user company profile (branding for every generated
document) and the database-backed store for generated files (replaces the
in-memory cache, which does not survive serverless instances).
"""
from __future__ import annotations

import uuid

from django.conf import settings
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
