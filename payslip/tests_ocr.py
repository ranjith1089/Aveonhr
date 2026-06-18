import unittest
from datetime import datetime
from payslip.services.bill_ocr_extractor import BillOCRExtractor, ExtractedField


class TestBillOCRExtractor(unittest.TestCase):
    """Unit tests for BillOCRExtractor date/amount/merchant extraction logic."""

    def test_extract_date_dd_mm_yyyy_format(self):
        """Test date extraction with DD/MM/YYYY format."""
        extractor = BillOCRExtractor()
        text = "Invoice Date: 15/06/2026"
        result = extractor._extract_date(text, [])
        self.assertNotEqual(result.confidence, 0.0)
        self.assertEqual(result.value, "2026-06-15")

    def test_extract_date_dd_mm_yyyy_hyphen_format(self):
        """Test date extraction with DD-MM-YYYY format."""
        extractor = BillOCRExtractor()
        text = "15-06-2026"
        result = extractor._extract_date(text, [])
        self.assertNotEqual(result.confidence, 0.0)
        self.assertEqual(result.value, "2026-06-15")

    def test_extract_date_with_contextual_keyword(self):
        """Test date extraction with contextual keyword 'Date:'."""
        extractor = BillOCRExtractor()
        text = "Date: 10/05/2026"
        result = extractor._extract_date(text, [])
        self.assertGreater(result.confidence, 0.85)

    def test_extract_date_no_date_found(self):
        """Test date extraction when no date is present."""
        extractor = BillOCRExtractor()
        text = "Hotel Grand Plaza Receipt"
        result = extractor._extract_date(text, [])
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.value, "")

    def test_extract_date_invalid_date(self):
        """Test date extraction with invalid date (e.g., 32/13/2026)."""
        extractor = BillOCRExtractor()
        text = "32/13/2026"  # Invalid month and day
        result = extractor._extract_date(text, [])
        # Should not crash, returns low confidence
        self.assertLessEqual(result.confidence, 0.0)

    def test_extract_amount_rupee_symbol(self):
        """Test amount extraction with rupee symbol."""
        extractor = BillOCRExtractor()
        text = "Total: ₹1,234.56"
        result = extractor._extract_amount(text, [])
        self.assertGreater(result.confidence, 0.85)
        self.assertEqual(result.value, 1234.56)

    def test_extract_amount_dollar_symbol(self):
        """Test amount extraction with dollar symbol."""
        extractor = BillOCRExtractor()
        text = "Grand Total: $ 99.99"
        result = extractor._extract_amount(text, [])
        self.assertGreater(result.confidence, 0.85)
        self.assertEqual(result.value, 99.99)

    def test_extract_amount_no_decimals(self):
        """Test amount extraction without decimals."""
        extractor = BillOCRExtractor()
        text = "Amount Due: 5000"
        result = extractor._extract_amount(text, [])
        # Should extract despite no decimal format
        self.assertGreater(result.confidence, 0.0)

    def test_extract_amount_with_commas(self):
        """Test amount extraction with comma separators."""
        extractor = BillOCRExtractor()
        text = "Total Amount: ₹10,000.50"
        result = extractor._extract_amount(text, [])
        self.assertGreater(result.confidence, 0.85)
        self.assertEqual(result.value, 10000.50)

    def test_extract_amount_zero_or_negative_rejected(self):
        """Test that zero or negative amounts are rejected."""
        extractor = BillOCRExtractor()
        text = "Amount: 0"
        result = extractor._extract_amount(text, [])
        self.assertEqual(result.confidence, 0.0)

    def test_extract_amount_no_amount_found(self):
        """Test amount extraction when no amount is present."""
        extractor = BillOCRExtractor()
        text = "Hotel Reception"
        result = extractor._extract_amount(text, [])
        self.assertEqual(result.confidence, 0.0)

    def test_extract_merchant_from_keywords(self):
        """Test merchant extraction with business keywords."""
        extractor = BillOCRExtractor()
        ocr_blocks = [("Hotel Grand Plaza", 0.98), ("Reception", 0.95), ("Room 501", 0.92)]
        result = extractor._extract_merchant(ocr_blocks)
        self.assertGreater(result.confidence, 0.70)
        self.assertEqual(result.value, "Hotel Grand Plaza")

    def test_extract_merchant_empty_blocks(self):
        """Test merchant extraction with empty OCR blocks."""
        extractor = BillOCRExtractor()
        result = extractor._extract_merchant([])
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.value, "")

    def test_extract_merchant_single_block(self):
        """Test merchant extraction with single text block."""
        extractor = BillOCRExtractor()
        ocr_blocks = [("ABC Restaurant", 0.92)]
        result = extractor._extract_merchant(ocr_blocks)
        self.assertGreater(result.confidence, 0.0)

    def test_currency_detection_rupee(self):
        """Test currency extraction with rupee symbol."""
        extractor = BillOCRExtractor()
        text = "Total: ₹5,000"
        result = extractor._extract_currency(text)
        self.assertEqual(result.value, "INR")
        self.assertEqual(result.confidence, 0.99)

    def test_currency_detection_dollar(self):
        """Test currency extraction with dollar symbol."""
        extractor = BillOCRExtractor()
        text = "Amount: $ 100.00"
        result = extractor._extract_currency(text)
        self.assertEqual(result.value, "USD")
        self.assertEqual(result.confidence, 0.99)

    def test_currency_default_when_not_found(self):
        """Test default currency when symbol not found."""
        extractor = BillOCRExtractor()
        text = "5000 without symbol"
        result = extractor._extract_currency(text, default_currency="INR")
        self.assertEqual(result.value, "INR")
        self.assertEqual(result.confidence, 0.85)

    def test_is_likely_merchant_with_keywords(self):
        """Test merchant likelihood detection with keywords."""
        extractor = BillOCRExtractor()
        self.assertTrue(extractor._is_likely_merchant("Hotel Marriott"))
        self.assertTrue(extractor._is_likely_merchant("Uber"))
        self.assertTrue(extractor._is_likely_merchant("Indian Oil"))

    def test_is_likely_merchant_without_keywords(self):
        """Test merchant likelihood detection without keywords."""
        extractor = BillOCRExtractor()
        self.assertTrue(extractor._is_likely_merchant("Business"))  # Starts with capital, > 3 chars
        self.assertFalse(extractor._is_likely_merchant("and"))  # lowercase, no keywords

    def test_extracted_field_to_dict(self):
        """Test ExtractedField serialization to dict."""
        field = ExtractedField(value="Hotel Grand", confidence=0.95)
        result = field.to_dict()
        self.assertEqual(result["value"], "Hotel Grand")
        self.assertEqual(result["confidence"], 0.95)

    def test_extracted_field_confidence_rounding(self):
        """Test confidence rounding in serialization."""
        field = ExtractedField(value="test", confidence=0.9567)
        result = field.to_dict()
        self.assertEqual(result["confidence"], 0.96)


if __name__ == "__main__":
    unittest.main()
