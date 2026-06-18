import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union
from io import BytesIO
from PIL import Image
import json


@dataclass
class ExtractedField:
    value: Union[str, float]
    confidence: float

    def to_dict(self):
        return {"value": self.value, "confidence": round(self.confidence, 2)}


@dataclass
class BillData:
    merchant: ExtractedField
    date: ExtractedField
    amount: ExtractedField
    currency: ExtractedField
    image_base64: str
    raw_ocr_output: list
    warnings: list

    def to_dict(self):
        return {
            "merchant": self.merchant.to_dict(),
            "date": self.date.to_dict(),
            "amount": self.amount.to_dict(),
            "currency": self.currency.to_dict(),
            "image_base64": self.image_base64,
            "raw_ocr_output": self.raw_ocr_output,
        }


class BillOCRExtractor:
    _paddle_ocr = None  # Lazy-loaded singleton

    DATE_PATTERNS = [
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',  # DD/MM/YYYY or MM/DD/YYYY
        r'\b(?:Date|DATE|Invoice Date|INVOICE DATE|Bill Date|BILL DATE)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b',
    ]

    AMOUNT_PATTERNS = [
        r'(?:Total|TOTAL|Amount Due|AMOUNT DUE|Grand Total|GRAND TOTAL|Net Amount)\s*:?\s*[₹$€£¥]?\s*([0-9,]+\.?[0-9]*)',
        r'[₹$€£¥]\s*([0-9,]+\.?[0-9]*)',
        r'\b([0-9,]+\.[0-9]{2})\b',
    ]

    MERCHANT_PATTERNS = [
        r'(?:Hotel|HOTEL|Restaurant|RESTAURANT|Airline|AIRLINE|Flight|FLIGHT|Taxi|TAXI|Uber|UBER)\s*[:]?\s*(.+?)(?:\n|$)',
    ]

    @classmethod
    def _get_paddle_ocr(cls):
        if cls._paddle_ocr is None:
            from paddleocr import PaddleOCR
            cls._paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en")
        return cls._paddle_ocr

    @classmethod
    def extract_from_image(cls, image_bytes: bytes, currency: str = "INR") -> BillData:
        import base64

        # Convert to PIL Image
        pil_img = Image.open(BytesIO(image_bytes))
        pil_img.load()

        # Encode image for response
        img_b64_buffer = BytesIO()
        pil_img.save(img_b64_buffer, format="PNG")
        image_base64 = base64.b64encode(img_b64_buffer.getvalue()).decode("utf-8")

        # Run OCR
        paddle_ocr = cls._get_paddle_ocr()
        ocr_results = paddle_ocr.ocr(pil_img, cls=True)

        # Parse OCR output into text and confidence list
        ocr_text_blocks = []
        full_ocr_output = []

        if ocr_results:
            for line in ocr_results:
                if line:
                    for word_box in line:
                        text = word_box[1][0] if len(word_box) > 1 else ""
                        conf = float(word_box[1][1]) if len(word_box) > 1 and len(word_box[1]) > 1 else 0
                        ocr_text_blocks.append((text, conf))
                        full_ocr_output.append({"text": text, "confidence": round(conf, 3)})

        # Combine all text for pattern matching
        full_text = " ".join([text for text, _ in ocr_text_blocks])

        # Extract date
        date_extracted = cls._extract_date(full_text, ocr_text_blocks)

        # Extract amount
        amount_extracted = cls._extract_amount(full_text, ocr_text_blocks)

        # Extract merchant (usually first few text blocks)
        merchant_extracted = cls._extract_merchant(ocr_text_blocks)

        # Currency extraction
        currency_extracted = cls._extract_currency(full_text, currency)

        # Warnings for low confidence
        warnings = []
        if date_extracted.confidence < 0.75:
            warnings.append(f"Low confidence on date extraction ({date_extracted.confidence:.0%}) - please verify")
        if amount_extracted.confidence < 0.75:
            warnings.append(f"Low confidence on amount extraction ({amount_extracted.confidence:.0%}) - please verify")
        if merchant_extracted.confidence < 0.70:
            warnings.append(f"Low confidence on merchant extraction ({merchant_extracted.confidence:.0%}) - please verify")

        return BillData(
            merchant=merchant_extracted,
            date=date_extracted,
            amount=amount_extracted,
            currency=currency_extracted,
            image_base64=image_base64,
            raw_ocr_output=full_ocr_output,
            warnings=warnings,
        )

    @classmethod
    def _extract_date(cls, text: str, ocr_blocks: list) -> ExtractedField:
        for pattern in cls.DATE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    # Try parsing as DD/MM/YYYY
                    parsed = datetime.strptime(date_str.replace("-", "/"), "%d/%m/%Y")
                    confidence = 0.92  # High confidence for regex match
                    return ExtractedField(value=parsed.strftime("%Y-%m-%d"), confidence=confidence)
                except ValueError:
                    pass

                try:
                    # Try parsing as MM/DD/YYYY
                    parsed = datetime.strptime(date_str.replace("-", "/"), "%m/%d/%Y")
                    confidence = 0.85  # Slightly lower for US format
                    return ExtractedField(value=parsed.strftime("%Y-%m-%d"), confidence=confidence)
                except ValueError:
                    pass

        # If no date found, return a low-confidence empty date
        return ExtractedField(value="", confidence=0.0)

    @classmethod
    def _extract_amount(cls, text: str, ocr_blocks: list) -> ExtractedField:
        for pattern in cls.AMOUNT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    amount = float(amount_str)
                    if amount > 0:
                        confidence = 0.91
                        return ExtractedField(value=amount, confidence=confidence)
                except ValueError:
                    pass

        return ExtractedField(value=0.0, confidence=0.0)

    @classmethod
    def _extract_merchant(cls, ocr_blocks: list) -> ExtractedField:
        if not ocr_blocks:
            return ExtractedField(value="", confidence=0.0)

        # Check first 3 blocks for merchant patterns
        for i, (text, conf) in enumerate(ocr_blocks[:5]):
            # Look for business names, acronyms, or common merchant patterns
            if cls._is_likely_merchant(text):
                return ExtractedField(value=text, confidence=min(conf * 0.95, 0.95))

        # If no specific pattern, use first non-trivial text block
        if ocr_blocks and ocr_blocks[0][0]:
            return ExtractedField(value=ocr_blocks[0][0], confidence=ocr_blocks[0][1] * 0.80)

        return ExtractedField(value="", confidence=0.0)

    @classmethod
    def _is_likely_merchant(cls, text: str) -> bool:
        keywords = [
            "hotel", "restaurant", "airline", "flight", "taxi", "uber",
            "petrol", "fuel", "gas station", "car rental", "flight", "train",
            "cafe", "bistro", "diner", "grill", "pizza", "burger",
            "indian oil", "bpcl", "hpcl", "shell", "bp",
            "marriott", "hilton", "taj", "oberoi", "hyatt",
        ]
        return any(kw in text.lower() for kw in keywords) or (len(text) > 3 and text[0].isupper())

    @classmethod
    def _extract_currency(cls, text: str, default_currency: str = "INR") -> ExtractedField:
        currency_symbols = {
            "₹": "INR",
            "$": "USD",
            "€": "EUR",
            "£": "GBP",
            "¥": "JPY",
        }

        for symbol, code in currency_symbols.items():
            if symbol in text:
                return ExtractedField(value=code, confidence=0.99)

        return ExtractedField(value=default_currency, confidence=0.85)
