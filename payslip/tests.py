from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
        self.staff = User.objects.create_user("inc_staff", "is@x.com", "pass12345", is_staff=True)
        self.plain = User.objects.create_user("inc_plain", "ip@x.com", "pass12345")
        self.client_obj = IncomeClient.objects.create(name="Test College")

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
        # non-staff -> 403
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get("/income/").status_code, 403)
        # staff -> 200
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/income/").status_code, 200)

    def test_seed_totals_match_sheet_footer(self):
        from decimal import Decimal
        from payslip.management.commands.seed_income import _rows
        rows = _rows().rows
        total = sum((r.net_amount + r.previous_pending - r.received for r in rows), Decimal("0"))
        self.assertEqual(total, Decimal("6281796.42"))
