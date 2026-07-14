"""
Shared PDF styling primitives — the single source of truth for the
"world-class" look across offer letters, appointment orders, employment
offers, and experience certificates.

Why a separate module: each PDF builder used to redefine margins, fonts,
spacers, signature blocks, and date formats locally — producing the same
information at different sizes, alignments, and date formats. Centralising
the look ensures every document Aveon sends looks like it came from the
same company.

`build_payslip_pdf` and `build_travel_expense_pdf` keep their bespoke
headers — they already have well-tuned brand palettes and tabular
layouts; touching them would be churn for no gain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Brand constants
# ---------------------------------------------------------------------------
BRAND_PRIMARY = colors.HexColor("#1565C0")   # deep blue — used in payslip header too
BRAND_ACCENT = colors.HexColor("#2E7D32")    # green accent
BRAND_DARK = colors.HexColor("#1A1A2E")      # near-black for headlines
BRAND_MUTED = colors.HexColor("#475569")     # slate for secondary text
BRAND_DIVIDER = colors.HexColor("#CBD5E1")   # subtle dividers
BRAND_BG_TINT = colors.HexColor("#F8FAFC")   # subtle row backgrounds

# Aveon canonical company details — single source for letterhead generation.
# Override per-call via build_letterhead(company_name=...) when needed.
COMPANY_NAME = "Aveon Infotech Private Limited"
COMPANY_TAGLINE = "Built for Education. Powered by Innovation."
COMPANY_ADDRESS = "Coimbatore, Tamil Nadu, India"
COMPANY_EMAIL = "contact@aveoninfotech.com"
COMPANY_WEBSITE = "www.aveoninfotech.com"
COMPANY_PHONE = "+91 8754006483"

LOGO_PATH = Path(__file__).parent / "static" / "payslip" / "logo.png"


@dataclass(frozen=True)
class CompanyBranding:
    """Per-tenant company identity used to brand generated documents.

    Defaults are the built-in (Aveon) values, so passing no branding - or a
    branding built from an empty profile - produces today's exact output.
    """

    name: str = COMPANY_NAME
    tagline: str = COMPANY_TAGLINE
    address: str = COMPANY_ADDRESS
    email: str = COMPANY_EMAIL
    phone: str = COMPANY_PHONE
    website: str = COMPANY_WEBSITE
    jurisdiction: str = "Coimbatore, Tamil Nadu"
    signatory_name: str = ""
    signatory_designation: str = ""
    logo_bytes: bytes | None = None  # None -> fall back to LOGO_PATH
    brand_primary: str = "#1565C0"
    brand_accent: str = "#2E7D32"

    @classmethod
    def from_profile(cls, profile) -> "CompanyBranding":
        """Build branding from a CompanyProfile; blank fields keep defaults."""
        if profile is None:
            return cls()
        d = cls()
        addr_parts = [p for p in [profile.address, profile.city, profile.state, profile.country] if p]
        return cls(
            name=profile.company_name or d.name,
            tagline=profile.tagline or d.tagline,
            address=", ".join(addr_parts) if profile.address or profile.city else d.address,
            email=profile.email or d.email,
            phone=profile.phone or d.phone,
            website=profile.website or d.website,
            jurisdiction=profile.jurisdiction or d.jurisdiction,
            signatory_name=profile.signatory_name or "",
            signatory_designation=profile.signatory_designation or "",
            logo_bytes=profile.logo_bytes,
            brand_primary=profile.brand_primary or d.brand_primary,
            brand_accent=profile.brand_accent or d.brand_accent,
        )

# ---------------------------------------------------------------------------
# Layout constants — same units everywhere so spacing is predictable
# ---------------------------------------------------------------------------
PAGE_SIZE = A4
MARGIN_SIDE = 20 * mm
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 22 * mm  # +2mm to leave room for the footer line

# Vertical rhythm — every builder uses these instead of arbitrary mm values
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 14
SPACE_LG = 22
SPACE_XL = 32
SPACE_SIGNATURE_GAP = 38  # blank space above the signatory name for the actual signature

FONT_BODY = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


# ---------------------------------------------------------------------------
# Paragraph styles — reused across all four refactored builders
# ---------------------------------------------------------------------------
def get_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "av_title",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=BRAND_DARK,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "av_subtitle",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            textColor=BRAND_MUTED,
            spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "av_h2",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=13,
            leading=17,
            alignment=TA_CENTER,
            textColor=BRAND_PRIMARY,
            spaceAfter=10,
        ),
        "body": ParagraphStyle(
            "av_body",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=11,
            leading=16,
            alignment=TA_JUSTIFY,
            textColor=BRAND_DARK,
            spaceAfter=6,
        ),
        "body_left": ParagraphStyle(
            "av_body_left",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=11,
            leading=16,
            alignment=TA_LEFT,
            textColor=BRAND_DARK,
        ),
        "small": ParagraphStyle(
            "av_small",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=9,
            leading=12,
            textColor=BRAND_MUTED,
        ),
        "small_right": ParagraphStyle(
            "av_small_right",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
            textColor=BRAND_MUTED,
        ),
        "signatory_name": ParagraphStyle(
            "av_signatory_name",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=12,
            leading=15,
            textColor=BRAND_DARK,
        ),
        "signatory_role": ParagraphStyle(
            "av_signatory_role",
            parent=base["Normal"],
            fontName=FONT_BODY,
            fontSize=10.5,
            leading=13,
            textColor=BRAND_MUTED,
        ),
    }


# ---------------------------------------------------------------------------
# Date formatting — one canonical format everywhere
# ---------------------------------------------------------------------------
def format_date(value, fallback: str = "—") -> str:
    """Return 'Jan. 5, 2026' style. Leading zero on the day is stripped."""
    if not value:
        return fallback
    if isinstance(value, str):
        # Best-effort parse — caller may pass an already-formatted string.
        return value
    if not isinstance(value, date):
        return str(value)
    return value.strftime("%b. %d, %Y").replace(" 0", " ")


# ---------------------------------------------------------------------------
# Letterhead — appears at the top of every refactored builder
# ---------------------------------------------------------------------------
def build_letterhead(
    *,
    company_name: str = COMPANY_NAME,
    tagline: str = COMPANY_TAGLINE,
    address: str = COMPANY_ADDRESS,
    contact: str = "",
    include_logo: bool = True,
    brand: "CompanyBranding | None" = None,
) -> list:
    """
    Returns a list of flowables forming a letterhead block:
        [logo + company-block table] + colored divider line + spacer
    Logo is omitted gracefully if the file is missing.

    Pass `brand=` to derive every field (incl. logo bytes and brand color)
    from a tenant's CompanyBranding; explicit kwargs are then ignored.
    """
    if brand is not None:
        company_name = brand.name
        tagline = brand.tagline
        address = brand.address
        contact = " | ".join(p for p in [brand.email, brand.phone] if p)
    brand_primary = brand.brand_primary if brand else "#1565C0"
    logo_bytes = brand.logo_bytes if brand else None

    styles = get_styles()
    flowables: list = []

    # Left cell: logo. Tenant logo bytes win; the bundled (Aveon) file is
    # only used for the default company - a custom company without an
    # uploaded logo gets no logo rather than someone else's.
    left_cell = ""
    if include_logo:
        try:
            if logo_bytes:
                from io import BytesIO
                left_cell = Image(BytesIO(logo_bytes), width=28 * mm, height=28 * mm, kind="proportional")
            elif company_name == COMPANY_NAME and LOGO_PATH.exists():
                left_cell = Image(str(LOGO_PATH), width=28 * mm, height=28 * mm, kind="proportional")
        except Exception:
            left_cell = ""

    # Right cell: company text. ReportLab doesn't allow nesting <para> tags,
    # so we build a single paragraph with <br/> line breaks and inline <font>
    # styling per line.
    company_lines = [
        f'<font name="{FONT_BOLD}" size="14" color="{brand_primary}">{company_name}</font>',
        f'<font name="{FONT_BODY}" size="9" color="#475569"><i>{tagline}</i></font>',
    ]
    if address:
        company_lines.append(
            f'<font name="{FONT_BODY}" size="9" color="#475569">{address}</font>'
        )
    if contact:
        company_lines.append(
            f'<font name="{FONT_BODY}" size="9" color="#475569">{contact}</font>'
        )

    company_para = Paragraph("<br/>".join(company_lines), styles["small_right"])

    header_table = Table(
        [[left_cell, company_para]],
        colWidths=[35 * mm, None],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flowables.append(header_table)

    # Colored divider — the tenant's primary brand colour
    divider = Table([[""]], colWidths=[None], rowHeights=[2.4])
    divider.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(brand_primary)),
        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    flowables.append(divider)
    flowables.append(Spacer(1, SPACE_LG))
    return flowables


# ---------------------------------------------------------------------------
# Signature block — leaves real space for an actual signature
# ---------------------------------------------------------------------------
def build_signature_block(
    *,
    closing: str = "Sincerely,",
    company: str = "",
    name: str = "",
    designation: str = "",
    place: str = "",
    space_gap: int = SPACE_SIGNATURE_GAP,
) -> list:
    """
    Closing → company line → blank gap for ink signature → printed name → designation.
    Every offer / certificate ends with this exact structure.
    """
    styles = get_styles()
    out: list = []
    out.append(Spacer(1, SPACE_LG))
    if closing:
        out.append(Paragraph(closing, styles["body_left"]))
    if company:
        out.append(Spacer(1, SPACE_XS))
        out.append(Paragraph(
            f'<font name="{FONT_BODY}" size="11">For <b>{company}</b>,</font>',
            styles["body_left"],
        ))
    # Real space for an ink signature — this is the part the old builders missed.
    out.append(Spacer(1, space_gap))
    if name:
        out.append(Paragraph(name, styles["signatory_name"]))
    if designation:
        out.append(Paragraph(designation, styles["signatory_role"]))
    if place:
        out.append(Spacer(1, SPACE_SM))
        out.append(Paragraph(f"Place: {place}", styles["small"]))
    return out


# ---------------------------------------------------------------------------
# Footer — drawn directly on the canvas via SimpleDocTemplate callbacks.
# Includes page number + generated-on date + company name.
# ---------------------------------------------------------------------------
def _make_footer_drawer(show_page_number: bool = True, company_name: str = COMPANY_NAME):
    """Return a footer-drawing callback. Page number is optional so a builder
    can keep the company footer line while dropping the 'Page N' text."""
    def _draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(FONT_BODY, 8)
        canvas.setFillColor(BRAND_MUTED)
        page_width = PAGE_SIZE[0]
        y = 12 * mm

        # Left: company name
        canvas.drawString(MARGIN_SIDE, y, company_name)

        # Center: thin divider above the footer text
        canvas.setStrokeColor(BRAND_DIVIDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_SIDE, y + 4 * mm, page_width - MARGIN_SIDE, y + 4 * mm)

        # Right: page number (optional)
        if show_page_number:
            canvas.drawRightString(page_width - MARGIN_SIDE, y, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()
    return _draw


# Backward-compatible default drawer (company footer line + page number).
_draw_footer = _make_footer_drawer(True)


def make_doc(buffer, *, author: str = COMPANY_NAME, title: str = "Document") -> SimpleDocTemplate:
    """A SimpleDocTemplate pre-wired with the shared margins + footer."""
    return SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN_SIDE,
        rightMargin=MARGIN_SIDE,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=title,
        author=author,
    )


def build_with_footer(
    doc: SimpleDocTemplate,
    story: list,
    *,
    footer: bool = True,
    show_page_number: bool = True,
    company_name: str = COMPANY_NAME,
) -> None:
    """Build the doc, optionally drawing the standard footer on every page.

    footer=False  -> no digital footer at all (e.g. plain export for
                     pre-printed letterhead paper).
    show_page_number=False -> keep the company footer line but drop 'Page N'.
    Defaults preserve the original behaviour for all existing builders.
    """
    if not footer:
        doc.build(story)
        return
    drawer = _make_footer_drawer(show_page_number, company_name)
    doc.build(story, onFirstPage=drawer, onLaterPages=drawer)
