"""Access-control decorators for the org/rights layer.

module_required replaces both login_required-on-tools and the old
income_required: anonymous users go to login, members without the module
right get a friendly 403 page pointing them to their org admin.

is_staff is no longer an app-level gate - it only matters for /admin/.
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import render

from .models import membership_for

MODULE_LABELS = {
    "offer_letters": "Offer Letters",
    "experience_certificates": "Experience Certificates",
    "travel_expense": "Travel Expense Reports",
    "proposals": "Proposals & Quotations",
    "people": "People (Candidates & Interns)",
    "income": "Income",
    "implementation": "Implementation Tracker",
    "payroll": "Payroll & Salary",
}


def _forbidden(request, label: str):
    return render(
        request, "payslip/403_module.html",
        {"module_label": label}, status=403,
    )


def module_required(module: str):
    assert module in MODULE_LABELS, f"Unknown module {module!r}"

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            membership = membership_for(request.user)
            request.membership = membership
            request.organization = membership.organization
            if not request.user.is_active or not membership.has_module(module):
                return _forbidden(request, MODULE_LABELS[module])
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def org_admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        membership = membership_for(request.user)
        request.membership = membership
        request.organization = membership.organization
        if not request.user.is_active or not membership.is_admin:
            return _forbidden(request, "Team & Company Settings (admins only)")
        return view(request, *args, **kwargs)
    return wrapper
