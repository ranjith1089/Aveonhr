from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


def make_member(username, *, admin=False, org=None, **rights):
    """Create a user with an explicit membership.

    rights: short module keys (income=True, payslips=True, ...) - anything
    not named defaults to False so tests stay precise. Returns the user;
    reach the org via user.membership.organization.
    """
    from payslip.models import Membership, Organization
    user = User.objects.create_user(username, f"{username}@x.com", "pass12345")
    if org is None:
        org = Organization.objects.create(company_name=f"{username} org")
    field_values = {
        field: bool(rights.get(key, False))
        for key, field in Membership.MODULE_FIELDS.items()
    }
    Membership.objects.create(
        user=user, organization=org,
        role=Membership.Role.ADMIN if admin else Membership.Role.MEMBER,
        **field_values,
    )
    return user


class ProposalQuotationViewTests(TestCase):
    def setUp(self):
        # All tools require login since the SaaS transformation.
        self.user = User.objects.create_user("tester", "tester@example.com", "pass12345")
        self.client.force_login(self.user)

    def test_get_proposal_quotation_page(self):
        response = self.client.get(reverse('proposal_quotation'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Proposal Quotation Generator')

    def test_post_generates_complete_proposal_text(self):
        response = self.client.post(
            reverse('proposal_quotation'),
            {
                'client_name': 'ABC College of Arts and Science',
                'client_location': 'Coimbatore, Tamil Nadu',
                'institution_type': 'AUTONOMOUS',
                'proposal_date': '2026-02-13',
                'prepared_by': 'Aveon Infotech Private Limited',
                'per_student_annual_license': '850',
                'minimum_student_commitment': '1000',
                'one_time_implementation_fee': '350000',
                'gst_percent': '18',
                'authorized_signatory_name': 'Parvathi G',
                'authorized_signatory_designation': 'Chief Executive Officer',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ABC College of Arts and Science')
        self.assertContains(response, 'Coimbatore, Tamil Nadu')
        self.assertContains(response, 'AUTONOMOUS')

        required_sections = [
            '1. Executive Summary',
            '2. About Aveon Infotech Private Limited',
            '3. Scope of Work - Module Overview',
            '4. Implementation Methodology',
            '5. Project Timeline',
            '6. Commercial Proposal',
            '7. Support & Maintenance',
            '8. Key Terms & Conditions',
            '9. Why Aveon Infotech',
            '10. Authorization',
        ]

        proposal_text = response.context['proposal_text']
        for section in required_sections:
            self.assertIn(section, proposal_text)

        self.assertIn('GST: 18% Extra', proposal_text)
        self.assertIn('INR 3,50,000', proposal_text)


    def test_post_download_returns_text_file(self):
        response = self.client.post(
            reverse('proposal_quotation'),
            {
                'client_name': 'ABC College of Arts and Science',
                'client_location': 'Coimbatore, Tamil Nadu',
                'institution_type': 'AUTONOMOUS',
                'proposal_date': '2026-02-13',
                'prepared_by': 'Aveon Infotech Private Limited',
                'per_student_annual_license': '850',
                'minimum_student_commitment': '1000',
                'one_time_implementation_fee': '350000',
                'gst_percent': '18',
                'authorized_signatory_name': 'Parvathi G',
                'authorized_signatory_designation': 'Chief Executive Officer',
                'action': 'download',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('attachment; filename="aveon_cms_erp_proposal.txt"', response['Content-Disposition'])
        text = response.content.decode('utf-8')
        self.assertIn('1. Executive Summary', text)
        self.assertIn('10. Authorization', text)


    def test_school_institution_type_is_available(self):
        response = self.client.get(reverse('proposal_quotation'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SCHOOL')

    def test_post_download_returns_pdf_file(self):
        response = self.client.post(
            reverse('proposal_quotation'),
            {
                'client_name': 'ABC School',
                'client_location': 'Coimbatore, Tamil Nadu',
                'institution_type': 'SCHOOL',
                'proposal_date': '2026-02-13',
                'prepared_by': 'Aveon Infotech Private Limited',
                'per_student_annual_license': '850',
                'minimum_student_commitment': '1000',
                'one_time_implementation_fee': '350000',
                'gst_percent': '18',
                'authorized_signatory_name': 'Parvathi G',
                'authorized_signatory_designation': 'Chief Executive Officer',
                'action': 'download_pdf',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="aveon_cms_erp_proposal.pdf"', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF-'))


class IncomeModuleTests(TestCase):
    def setUp(self):
        from .models import IncomeClient
        self.staff = make_member("inc_staff", income=True, implementation=True)
        self.org = self.staff.membership.organization
        # Member of the same org WITHOUT the income right -> 403.
        self.plain = make_member("inc_plain", org=self.org)
        self.client_obj = IncomeClient.objects.create(name="Test College",
                                                      organization=self.org)

    def test_gst_math_and_quantization(self):
        from decimal import Decimal
        from .models import ClientBilling
        b = ClientBilling(client=self.client_obj, academic_year="2025-2026",
                          student_count=1234, rate=Decimal("250"))
        b.save()
        self.assertEqual(b.taxable_value, Decimal("308500.00"))
        self.assertEqual(b.gst_amount, Decimal("55530.00"))
        self.assertEqual(b.net_amount, Decimal("364030.00"))
        self.assertEqual(b.year_start, 2025)

    def test_override_amounts_untouched(self):
        from decimal import Decimal
        from .models import ClientBilling
        b = ClientBilling(client=self.client_obj, academic_year="2024-2025",
                          override_amounts=True, net_amount=Decimal("850000.02"))
        b.save()
        self.assertEqual(b.net_amount, Decimal("850000.02"))
        self.assertEqual(b.gst_amount, Decimal("0"))

    def test_balance_with_part_payments_and_overpayment(self):
        from decimal import Decimal
        from .models import ClientBilling, PaymentReceipt
        b = ClientBilling(client=self.client_obj, academic_year="2025-2026",
                          override_amounts=True, net_amount=Decimal("100000"),
                          previous_pending=Decimal("20000"))
        b.save()
        PaymentReceipt.objects.create(billing=b, amount=Decimal("50000"))
        PaymentReceipt.objects.create(billing=b, amount=Decimal("80000"))
        self.assertEqual(b.received_total, Decimal("130000"))
        self.assertEqual(b.balance, Decimal("-10000"))  # overpaid -> advance

    def test_academic_year_normalization(self):
        from .forms_income import ClientBillingForm
        form = ClientBillingForm(data={"academic_year": "2025-26",
                                       "override_amounts": True, "net_amount": "1000",
                                       "one_time_payment": "0", "gst_amount": "0",
                                       "previous_pending": "0"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["academic_year"], "2025-2026")

    def test_to_decimal_handles_currency_and_text(self):
        from decimal import Decimal
        from .services.income_import import _to_decimal
        self.assertEqual(_to_decimal("₹1,23,456.75"), Decimal("123456.75"))
        self.assertEqual(_to_decimal(1500), Decimal("1500.00"))
        self.assertIsNone(_to_decimal("Around 3 Lakhs"))
        self.assertIsNone(_to_decimal(""))

    def test_access_control(self):
        # anonymous -> login redirect
        r = self.client.get("/income/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        # member without the income right -> friendly 403
        self.client.force_login(self.plain)
        resp = self.client.get("/income/")
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "organization admin", status_code=403)
        # member with the right -> 200
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/income/").status_code, 200)

    def test_seed_totals_match_sheet_footer(self):
        from decimal import Decimal
        from payslip.management.commands.seed_income import _rows
        rows = _rows().rows
        total = sum((r.net_amount + r.previous_pending - r.received for r in rows), Decimal("0"))
        self.assertEqual(total, Decimal("6281796.42"))


class IncomeAnalyticsTests(TestCase):
    """Forecast and analytics math for the Income module."""

    def setUp(self):
        from decimal import Decimal
        from payslip.models import ClientBilling, IncomeClient, PaymentReceipt
        self.staff = make_member("inc_staff2", income=True)
        self.org = self.staff.membership.organization
        self.client.force_login(self.staff)

        # Rate-based client with two consecutive years: 1000 -> 1100 students (10% growth)
        grower = IncomeClient.objects.create(name="Growth College", organization=self.org)
        ClientBilling.objects.create(client=grower, academic_year="2024-2025",
                                     student_count=1000, rate=Decimal("100"))
        b2 = ClientBilling.objects.create(client=grower, academic_year="2025-2026",
                                          student_count=1100, rate=Decimal("100"))
        PaymentReceipt.objects.create(billing=b2, amount=Decimal("50000"))

        # Fixed-fee client
        fixed = IncomeClient.objects.create(name="Fixed School", organization=self.org)
        ClientBilling.objects.create(client=fixed, academic_year="2025-2026",
                                     override_amounts=True, net_amount=Decimal("350000"))

        # Discontinued client - must be excluded from forecast
        gone = IncomeClient.objects.create(name="Gone Institute", is_active=False,
                                           organization=self.org)
        ClientBilling.objects.create(client=gone, academic_year="2025-2026",
                                     override_amounts=True, net_amount=Decimal("99999"))

    def test_forecast_excludes_discontinued(self):
        from payslip.services.income_analytics import build_forecast
        names = [r["name"] for r in build_forecast(self.org)["rows"]]
        self.assertNotIn("Gone Institute", names)
        self.assertIn("Growth College", names)
        self.assertIn("Fixed School", names)

    def test_forecast_growth_projection(self):
        from decimal import Decimal
        from payslip.services.income_analytics import build_forecast
        fc = build_forecast(self.org)
        self.assertEqual(fc["target_year"], "2026-2027")
        grower = next(r for r in fc["rows"] if r["name"] == "Growth College")
        # 1100 * 1.10 growth = 1210 projected students
        self.assertEqual(grower["projected_count"], 1210)
        # 1210 * 100 * 1.18 = 142780
        self.assertEqual(grower["growth"], Decimal("142780.00"))
        # conservative = latest net (1100*100*1.18 = 129800)
        self.assertEqual(grower["conservative"], Decimal("129800.00"))

    def test_forecast_fixed_fee_uses_same_net(self):
        from decimal import Decimal
        from payslip.services.income_analytics import build_forecast
        fixed = next(r for r in build_forecast(self.org)["rows"] if r["name"] == "Fixed School")
        self.assertEqual(fixed["conservative"], Decimal("350000.00"))
        self.assertEqual(fixed["growth"], Decimal("350000.00"))
        self.assertEqual(fixed["note"], "fixed fee")

    def test_analytics_fy_totals(self):
        from decimal import Decimal
        from payslip.services.income_analytics import build_analytics
        a = build_analytics(self.org)
        fy26 = next(r for r in a["fy_rows"] if r["year"] == "2025-2026")
        # billed = 129800 (grower) + 350000 (fixed) + 99999 (gone)
        self.assertEqual(fy26["billed"], Decimal("579799.00"))
        self.assertEqual(fy26["received"], Decimal("50000.00"))

    def test_analytics_page_renders_for_staff(self):
        resp = self.client.get("/income/analytics/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Revenue Forecast")
        self.assertContains(resp, "Growth College")
        self.assertNotContains(resp, 'Gone Institute</a></td>\n              <td class="num">₹')

    def test_analytics_forbidden_without_income_right(self):
        plain = make_member("inc_plain2", org=self.org)
        self.client.force_login(plain)
        self.assertEqual(self.client.get("/income/analytics/").status_code, 403)


class ImplementationTrackingTests(TestCase):
    def setUp(self):
        from .models import IncomeClient
        self.staff = make_member("impl_staff", income=True, implementation=True)
        self.org = self.staff.membership.organization
        self.plain = make_member("impl_plain", org=self.org)
        self.income_client = IncomeClient.objects.create(name="Impl College",
                                                         organization=self.org)
        self.client.force_login(self.staff)

    def test_agreement_end_auto_computes_from_start_plus_years(self):
        import datetime
        from .models import ClientOnboarding
        o = ClientOnboarding.objects.create(
            client=self.income_client,
            agreement_start=datetime.date(2025, 6, 1), agreement_years=3,
        )
        self.assertEqual(o.agreement_end, datetime.date(2028, 6, 1))

    def test_explicit_agreement_end_wins(self):
        import datetime
        from .models import ClientOnboarding
        o = ClientOnboarding.objects.create(
            client=self.income_client,
            agreement_start=datetime.date(2025, 6, 1), agreement_years=3,
            agreement_end=datetime.date(2027, 12, 31),
        )
        self.assertEqual(o.agreement_end, datetime.date(2027, 12, 31))

    def test_expiry_properties_across_boundaries(self):
        import datetime
        from django.utils import timezone
        from .models import ClientOnboarding
        today = timezone.localdate()
        o = ClientOnboarding.objects.create(client=self.income_client,
                                            agreement_signed=True)
        # 89 days out: inside the 90-day window -> expiring, not expired
        o.agreement_end = today + datetime.timedelta(days=89)
        self.assertTrue(o.agreement_expiring)
        self.assertFalse(o.agreement_expired)
        # 91 days out: outside the window
        o.agreement_end = today + datetime.timedelta(days=91)
        self.assertFalse(o.agreement_expiring)
        self.assertFalse(o.agreement_expired)
        # past date: expired, not expiring
        o.agreement_end = today - datetime.timedelta(days=1)
        self.assertTrue(o.agreement_expired)
        self.assertFalse(o.agreement_expiring)
        # no end date at all
        o.agreement_end = None
        self.assertIsNone(o.days_to_expiry)
        self.assertFalse(o.agreement_expired)
        self.assertFalse(o.agreement_expiring)

    def test_seed_cms_creates_25_modules_and_is_idempotent(self):
        url = f"/income/clients/{self.income_client.pk}/implementation/"
        resp = self.client.post(url, {"action": "seed_cms"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.income_client.features.count(), 25)
        self.client.post(url, {"action": "seed_cms"})
        self.assertEqual(self.income_client.features.count(), 25)

    def test_progress_excludes_na(self):
        from .models import FeatureStatus, feature_progress
        S = FeatureStatus.Status
        for i, status in enumerate([S.LIVE, S.LIVE, S.IN_PROGRESS, S.NA]):
            FeatureStatus.objects.create(client=self.income_client,
                                         name=f"F{i}", status=status, order=i)
        p = feature_progress(self.income_client.features.all())
        self.assertEqual(p["total"], 4)
        self.assertEqual(p["applicable"], 3)
        self.assertEqual(p["live"], 2)
        self.assertEqual(p["pct"], 66)

    def test_bulk_save_stamps_completed_on_for_live(self):
        from django.utils import timezone
        from .models import FeatureStatus
        f = FeatureStatus.objects.create(client=self.income_client, name="Fees")
        url = f"/income/clients/{self.income_client.pk}/implementation/"
        resp = self.client.post(url, {
            "action": "save_features",
            f"status_{f.pk}": "LIVE",
            f"engineer_{f.pk}": "Kalai",
            f"remarks_{f.pk}": "done",
        })
        self.assertEqual(resp.status_code, 302)
        f.refresh_from_db()
        self.assertEqual(f.status, "LIVE")
        self.assertEqual(f.completed_on, timezone.localdate())
        self.assertEqual(f.engineer, "Kalai")

    def test_access_control_both_routes(self):
        dash = "/income/implementation/"
        detail = f"/income/clients/{self.income_client.pk}/implementation/"
        self.assertEqual(self.client.get(dash).status_code, 200)
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(dash).status_code, 403)
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(dash).status_code, 302)
        self.assertEqual(self.client.get(detail).status_code, 302)

    def test_dashboard_lists_expiring_and_po_pending(self):
        import datetime
        from django.utils import timezone
        from .models import ClientOnboarding
        ClientOnboarding.objects.create(
            client=self.income_client, agreement_signed=True,
            agreement_end=timezone.localdate() + datetime.timedelta(days=30),
        )
        resp = self.client.get("/income/implementation/")
        self.assertContains(resp, "Impl College")
        self.assertContains(resp, "Agreements needing attention")
        self.assertContains(resp, "PO pending")

    def test_income_dashboard_shows_alert_banner(self):
        resp = self.client.get("/income/")
        self.assertContains(resp, "without a PO")


class MembershipProvisioningTests(TestCase):
    def test_signup_creates_org_and_admin_membership(self):
        from payslip.models import Membership
        resp = self.client.post("/accounts/signup/", {
            "username": "neworg_admin", "email": "neworg@x.com",
            "password1": "str0ng-pass-123", "password2": "str0ng-pass-123",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn("welcome=1", resp["Location"])
        user = User.objects.get(username="neworg_admin")
        m = Membership.objects.get(user=user)
        self.assertEqual(m.role, Membership.Role.ADMIN)
        self.assertIsNotNone(m.organization)

    def test_membership_for_auto_provisions_bare_user(self):
        from payslip.models import Membership, membership_for
        user = User.objects.create_user("bare_user", "bare@x.com", "pass12345")
        m = membership_for(user)
        self.assertEqual(m.role, Membership.Role.ADMIN)
        self.assertEqual(membership_for(user).pk, m.pk)  # stable on re-call


class ModuleRightsTests(TestCase):
    def setUp(self):
        self.admin = make_member("rights_admin", admin=True)
        self.org = self.admin.membership.organization

    def test_member_without_right_gets_friendly_403(self):
        member = make_member("no_payslip", org=self.org, offer_letters=True)
        self.client.force_login(member)
        resp = self.client.get("/payslip/")
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "organization admin", status_code=403)

    def test_member_with_right_gets_200(self):
        member = make_member("has_payslip", org=self.org, payslips=True)
        self.client.force_login(member)
        self.assertEqual(self.client.get("/payslip/").status_code, 200)
        # ...but proposals stays blocked
        self.assertEqual(self.client.get("/proposal-quotation/").status_code, 403)

    def test_admin_bypasses_toggles(self):
        from payslip.models import Membership
        Membership.objects.filter(user=self.admin).update(
            can_payslips=False, can_income=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/payslip/").status_code, 200)
        self.assertEqual(self.client.get("/income/").status_code, 200)

    def test_anonymous_redirects_to_login(self):
        r = self.client.get("/payslip/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])


class OrgIsolationTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from payslip.models import ClientBilling, IncomeClient
        self.user_a = make_member("org_a_user", income=True, implementation=True)
        self.org_a = self.user_a.membership.organization
        self.user_b = make_member("org_b_user", income=True, implementation=True)
        self.org_b = self.user_b.membership.organization
        # Same client name in both orgs - allowed by the composite constraint.
        self.client_a = IncomeClient.objects.create(name="Test College", organization=self.org_a)
        self.client_b = IncomeClient.objects.create(name="Test College", organization=self.org_b)
        ClientBilling.objects.create(client=self.client_a, academic_year="2025-2026",
                                     override_amounts=True, net_amount=Decimal("100000"))
        ClientBilling.objects.create(client=self.client_b, academic_year="2025-2026",
                                     override_amounts=True, net_amount=Decimal("777777"))

    def test_client_list_scoped(self):
        self.client.force_login(self.user_a)
        resp = self.client.get("/income/clients/")
        self.assertContains(resp, "Test College")
        self.assertNotContains(resp, "777,777")

    def test_cross_org_detail_edit_implementation_404(self):
        self.client.force_login(self.user_a)
        for url in (f"/income/clients/{self.client_b.pk}/",
                    f"/income/clients/{self.client_b.pk}/edit/",
                    f"/income/clients/{self.client_b.pk}/implementation/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_analytics_scoped(self):
        from decimal import Decimal
        from payslip.services.income_analytics import build_analytics
        a = build_analytics(self.org_a)
        total_billed = sum(r["billed"] for r in a["fy_rows"])
        self.assertEqual(total_billed, Decimal("100000.00"))

    def test_export_scoped(self):
        from openpyxl import load_workbook
        from io import BytesIO
        from payslip.services.income_export import build_income_workbook
        wb = load_workbook(BytesIO(build_income_workbook(self.org_b)))
        values = [str(c.value) for row in wb.active.iter_rows() for c in row if c.value]
        self.assertTrue(any("777777" in v for v in values))
        self.assertFalse(any(v == "100000" for v in values))


class TeamPageTests(TestCase):
    def setUp(self):
        self.admin = make_member("team_admin", admin=True)
        self.org = self.admin.membership.organization
        self.client.force_login(self.admin)

    def test_member_cannot_open_team_page(self):
        member = make_member("team_member", org=self.org)
        self.client.force_login(member)
        self.assertEqual(self.client.get("/team/").status_code, 403)

    def test_admin_adds_member_and_they_can_log_in(self):
        from payslip.models import Membership
        resp = self.client.post("/team/add/", {
            "first_name": "Priya", "username": "priya", "email": "priya@x.com",
            "password": "temp-pass-9x21", "role": "MEMBER",
            "new_can_payslips": "on",
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="priya")
        m = Membership.objects.get(user=user)
        self.assertEqual(m.organization, self.org)
        self.assertTrue(m.can_payslips)
        self.assertFalse(m.can_income)
        # Temp password works for a real login.
        fresh = self.client_class()
        self.assertTrue(fresh.login(username="priya", password="temp-pass-9x21"))

    def test_deactivate_blocks_next_request(self):
        member = make_member("leaver", org=self.org, payslips=True)
        member_session = self.client_class()
        member_session.force_login(member)
        self.assertEqual(member_session.get("/payslip/").status_code, 200)
        resp = self.client.post(f"/team/{member.pk}/toggle/")
        self.assertEqual(resp.status_code, 302)
        member.refresh_from_db()
        self.assertFalse(member.is_active)
        # Their live session no longer passes module_required.
        self.assertNotEqual(member_session.get("/payslip/").status_code, 200)

    def test_bulk_save_updates_rights(self):
        member = make_member("flipme", org=self.org)
        resp = self.client.post("/team/", {
            f"role_{self.admin.pk}": "ADMIN",
            f"can_payslips_{self.admin.pk}": "on",
            f"role_{member.pk}": "MEMBER",
            f"can_income_{member.pk}": "on",
        })
        self.assertEqual(resp.status_code, 302)
        member.membership.refresh_from_db()
        self.assertTrue(member.membership.can_income)
        self.assertFalse(member.membership.can_payslips)

    def test_last_admin_cannot_be_demoted(self):
        from payslip.models import Membership
        resp = self.client.post("/team/", {f"role_{self.admin.pk}": "MEMBER"})
        self.assertEqual(resp.status_code, 302)
        m = Membership.objects.get(user=self.admin)
        self.assertEqual(m.role, Membership.Role.ADMIN)  # unchanged

    def test_last_admin_cannot_be_deactivated(self):
        # Deactivate the founder via a second admin, then verify the last
        # active admin can be neither demoted nor self-deactivated.
        second_admin = make_member("second_admin", admin=True, org=self.org)
        second_admin_session = self.client_class()
        second_admin_session.force_login(second_admin)
        second_admin_session.post(f"/team/{self.admin.pk}/toggle/")
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_active)
        # Demote via bulk save: blocked by the active-admin count.
        second_admin_session.post("/team/", {f"role_{second_admin.pk}": "MEMBER"})
        second_admin.membership.refresh_from_db()
        self.assertEqual(second_admin.membership.role, "ADMIN")
        # Self-deactivation: blocked by the self-guard.
        second_admin_session.post(f"/team/{second_admin.pk}/toggle/")
        second_admin.refresh_from_db()
        self.assertTrue(second_admin.is_active)
