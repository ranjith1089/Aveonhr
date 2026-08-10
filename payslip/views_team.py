"""Team management - org admins add members and grant per-module rights."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import org_admin_required
from .forms import AddMemberForm
from .models import Membership, Person

RIGHT_FIELDS = list(Membership.MODULE_FIELDS.values())

RIGHT_LABELS = {
    "can_offer_letters": "Offer Letters",
    "can_experience_certificates": "Experience Certs",
    "can_travel_expense": "Travel Expense",
    "can_proposals": "Proposals",
    "can_people": "People & Recruitment",
    "can_income": "Income",
    "can_implementation": "Implementation",
    "can_payroll": "Payroll",
}


def _members(org):
    return (Membership.objects.filter(organization=org)
            .select_related("user").order_by("user__date_joined"))


def _team_context(request, org, add_form, add_form_open=False, people=None, prefill_person=None):
    members = list(_members(org))
    rows = [
        {"m": m, "rights": [(f, bool(getattr(m, f))) for f in RIGHT_FIELDS]}
        for m in members
    ]
    return {
        "org": org,
        "rows": rows,
        "right_columns": [(f, RIGHT_LABELS[f]) for f in RIGHT_FIELDS],
        "add_form": add_form,
        "add_form_open": add_form_open,
        "me": request.user,
        "people": people if people is not None else Person.objects.filter(organization=org).order_by("name"),
        "prefill_person": prefill_person,
    }


@org_admin_required
def team(request: HttpRequest) -> HttpResponse:
    org = request.organization
    members = list(_members(org))

    if request.method == "POST":
        # Bulk save: role + rights checkboxes per member row. Apply the POST
        # in memory first; only write if at least one active admin remains.
        active_admins = 0
        for m in members:
            role = request.POST.get(f"role_{m.user_id}", m.role)
            if role in (Membership.Role.ADMIN, Membership.Role.MEMBER):
                m.role = role
            for field in RIGHT_FIELDS:
                setattr(m, field, f"{field}_{m.user_id}" in request.POST)
            if m.role == Membership.Role.ADMIN and m.user.is_active:
                active_admins += 1
        if active_admins == 0:
            messages.error(request, "Not saved: the organization needs at "
                                    "least one active admin.")
        else:
            with transaction.atomic():
                for m in members:
                    m.save()
            messages.success(request, "Team rights updated.")
        return redirect("team")

    prefill_person = None
    person_id = request.GET.get("person")
    if person_id and person_id.isdigit():
        prefill_person = Person.objects.filter(pk=person_id, organization=org).first()

    initial = None
    if prefill_person:
        initial = {"first_name": prefill_person.name, "email": prefill_person.email}

    add_form = AddMemberForm(initial=initial)
    return render(request, "payslip/team.html",
                  _team_context(request, org, add_form,
                                add_form_open=bool(prefill_person),
                                prefill_person=prefill_person))


@org_admin_required
@require_POST
def team_add_member(request: HttpRequest) -> HttpResponse:
    org = request.organization
    form = AddMemberForm(request.POST)
    if not form.is_valid():
        return render(request, "payslip/team.html",
                      _team_context(request, org, form, add_form_open=True))

    data = form.cleaned_data
    user = User.objects.create_user(
        username=data["username"], email=data["email"],
        password=data["password"], first_name=data["first_name"],
    )
    rights = {field: f"new_{field}" in request.POST for field in RIGHT_FIELDS}
    Membership.objects.create(
        user=user, organization=org, role=data["role"], **rights,
    )
    messages.success(
        request,
        f"Account created for {data['first_name'] or data['username']}. "
        f"Share these credentials: username '{data['username']}' with the "
        f"temporary password you set. They can change it after logging in.",
    )
    return redirect("team")


@org_admin_required
@require_POST
def team_toggle_member(request: HttpRequest, user_id: int) -> HttpResponse:
    org = request.organization
    membership = get_object_or_404(
        Membership.objects.select_related("user"),
        user_id=user_id, organization=org,
    )
    user = membership.user
    if user.is_active:
        other_admins = Membership.objects.filter(
            organization=org, role=Membership.Role.ADMIN, user__is_active=True
        ).exclude(user_id=user.pk).exists()
        if membership.is_admin and not other_admins:
            messages.error(request, "Cannot deactivate the last active admin.")
            return redirect("team")
        if user == request.user:
            messages.error(request, "You cannot deactivate your own account.")
            return redirect("team")
        user.is_active = False
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.username} deactivated - they can no "
                                  f"longer sign in.")
    else:
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.username} reactivated.")
    return redirect("team")


@org_admin_required
@require_POST
def team_reset_password(request: HttpRequest, user_id: int) -> HttpResponse:
    org = request.organization
    membership = get_object_or_404(
        Membership.objects.select_related("user"),
        user_id=user_id, organization=org,
    )
    user = membership.user
    new_password = request.POST.get("new_password", "").strip()
    if not new_password:
        messages.error(request, "Password cannot be empty.")
        return redirect("team")
    try:
        user.set_password(new_password)
        user.save(update_fields=["password"])
        messages.success(
            request,
            f"✓ Password reset for {user.username}. New password: {new_password}"
        )
    except Exception as e:
        messages.error(request, f"Error resetting password: {str(e)}")
    return redirect("team")
