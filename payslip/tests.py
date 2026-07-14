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
