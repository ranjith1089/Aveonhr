"""Parse and import the client payment follow-up workbook (.xlsx).

The source sheet is messy by nature: blank continuation cells for multi-year
clients, currency strings with rupee signs and commas, text amounts like
"Around 3 Lakhs", fixed-fee rows whose figures don't reconcile with
count x rate. The parser absorbs all of that; anything non-numeric lands in
remarks with a warning instead of blocking the import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from ..models import ClientBilling, IncomeClient, PaymentReceipt

_YEAR_RE = re.compile(r"^(\d{4})\s*-\s*(\d{2,4})$")


@dataclass
class ParsedRow:
    client_name: str
    academic_year: str
    student_count: int | None = None
    rate: Decimal | None = None
    one_time_payment: Decimal = Decimal("0")
    override_amounts: bool = False
    taxable_value: Decimal | None = None
    gst_amount: Decimal = Decimal("0")
    net_amount: Decimal = Decimal("0")
    previous_pending: Decimal = Decimal("0")
    received: Decimal = Decimal("0")
    engineer: str = ""
    invoice_status: str = ""
    remarks: str = ""
    agreement_status: str = ""
    is_active: bool = True


@dataclass
class ImportResult:
    rows: list[ParsedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _to_decimal(value) -> Decimal | None:
    """Numbers and currency strings -> Decimal; text/empty -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("₹", "").replace("Rs.", "").replace("Rs", "")
    s = s.replace(",", "").replace(" ", "")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _normalize_year(value) -> str | None:
    if value is None:
        return None
    m = _YEAR_RE.match(str(value).strip())
    if not m:
        return None
    start = int(m.group(1))
    end_raw = m.group(2)
    end = int(end_raw) if len(end_raw) == 4 else int(str(start)[:2] + end_raw)
    return f"{start}-{end}"


_INVOICE_MAP = [
    ("proforma invoice generated", ClientBilling.InvoiceStatus.PROFORMA),
    ("proforma invoice sent", ClientBilling.InvoiceStatus.ALREADY_SENT),
    ("already proforma", ClientBilling.InvoiceStatus.ALREADY_SENT),
    ("tax invoice", ClientBilling.InvoiceStatus.TAX_SENT),
    ("not need", ClientBilling.InvoiceStatus.NOT_NEEDED),
    ("waiting", ClientBilling.InvoiceStatus.WAITING),
]

_ENGINEERS = {"balachandhar", "kalai", "mullai", "naveen prasath", "selladurai",
              "naveen r", "suresh", "kariyappan", "dharun"}


def _map_invoice_status(text: str) -> str:
    low = (text or "").lower()
    for needle, status in _INVOICE_MAP:
        if needle in low:
            return status
    return ""


def parse_income_workbook(file_obj) -> ImportResult:
    import openpyxl

    wb = openpyxl.load_workbook(file_obj, data_only=True)
    ws = wb.active
    result = ImportResult()

    header_idx = None
    headers: list[str] = []
    rows = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows):
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        if "client" in cells:
            header_idx = i
            headers = cells
            break
    if header_idx is None:
        raise ValueError("Could not find a header row containing 'Client'.")

    def col(*names):
        for n in names:
            for j, h in enumerate(headers):
                if n in h:
                    return j
        return None

    c_client = col("client")
    c_year = col("academic year")
    c_count = col("student count")
    c_rate = col("rate")
    c_onetime = col("one time")
    c_taxable = col("taxable")
    c_gst = col("gst")
    c_net = col("net amount")
    c_prev = col("previous pending")
    c_recv = col("received")
    c_engineer = col("implementation engineer", "engineer")
    c_invoice = col("invoice status")
    c_remarks = col("remarks")
    c_agreement = col("agreement")

    def get(row, idx):
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    current_client = ""
    for row in rows[header_idx + 1:]:
        raw_client = get(row, c_client)
        year = _normalize_year(get(row, c_year))
        joined = " ".join(str(c) for c in row if c is not None).lower()
        if "total" in joined and year is None:
            continue  # footer rows
        if raw_client and str(raw_client).strip():
            current_client = str(raw_client).strip()
        if not year:
            # a client line without a parseable year is unusable - warn once
            if raw_client and str(raw_client).strip():
                result.warnings.append(
                    f"Skipped row for '{current_client}': no academic year found."
                )
            continue
        if not current_client:
            continue

        remarks_bits = []
        r = ParsedRow(client_name=current_client, academic_year=year)

        count_val = get(row, c_count)
        try:
            r.student_count = int(count_val) if count_val not in (None, "") else None
        except (TypeError, ValueError):
            r.student_count = None

        r.rate = _to_decimal(get(row, c_rate))

        onetime_raw = get(row, c_onetime)
        onetime = _to_decimal(onetime_raw)
        if onetime is None and onetime_raw not in (None, ""):
            remarks_bits.append(f"One-time payment noted as: {onetime_raw}")
            result.warnings.append(
                f"{current_client} {year}: one-time payment '{onetime_raw}' is not a number - kept in remarks."
            )
        r.one_time_payment = onetime or Decimal("0")

        r.taxable_value = _to_decimal(get(row, c_taxable))
        r.gst_amount = _to_decimal(get(row, c_gst)) or Decimal("0")
        r.net_amount = _to_decimal(get(row, c_net)) or Decimal("0")
        r.previous_pending = _to_decimal(get(row, c_prev)) or Decimal("0")

        recv_raw = get(row, c_recv)
        recv = _to_decimal(recv_raw)
        if recv is None and recv_raw not in (None, ""):
            remarks_bits.append(f"Received noted as: {recv_raw}")
            result.warnings.append(
                f"{current_client} {year}: received '{recv_raw}' is not a number - kept in remarks."
            )
        r.received = recv or Decimal("0")

        # Engineer column sometimes carries status text on continuation rows.
        eng_raw = str(get(row, c_engineer) or "").strip()
        if eng_raw.lower() in _ENGINEERS:
            r.engineer = eng_raw
        elif eng_raw:
            remarks_bits.append(eng_raw)

        inv_raw = str(get(row, c_invoice) or "").strip()
        r.invoice_status = _map_invoice_status(inv_raw)
        if inv_raw and not r.invoice_status:
            remarks_bits.append(inv_raw)

        rem_raw = str(get(row, c_remarks) or "").strip()
        if rem_raw:
            remarks_bits.append(rem_raw)
        agr_raw = str(get(row, c_agreement) or "").strip()
        if agr_raw:
            r.agreement_status = agr_raw

        r.remarks = " | ".join(b for b in remarks_bits if b)
        if "discontinued" in r.remarks.lower():
            r.is_active = False

        # Fixed-fee heuristic: figures that don't reconcile with count x rate
        # (within Rs.1) are stored verbatim via override.
        if r.student_count and r.rate is not None:
            expected_taxable = (Decimal(r.student_count) * r.rate).quantize(Decimal("0.01"))
            if r.taxable_value is None or abs(r.taxable_value - expected_taxable) > 1:
                r.override_amounts = True
        else:
            r.override_amounts = True

        result.rows.append(r)

    return result


def apply_import(result: ImportResult, organization) -> dict:
    """Create clients/billings/opening payments for one organization.
    Re-runnable: existing (client, year) rows are skipped."""
    created_clients = 0
    created_billings = 0
    skipped = 0
    with transaction.atomic():
        for r in result.rows:
            client, was_created = IncomeClient.objects.get_or_create(
                name=r.client_name, organization=organization
            )
            if was_created:
                created_clients += 1
            changed = False
            if r.agreement_status and not client.agreement_status:
                client.agreement_status = r.agreement_status
                changed = True
            if not r.is_active and client.is_active:
                client.is_active = False
                changed = True
            if changed:
                client.save()

            if ClientBilling.objects.filter(client=client, academic_year=r.academic_year).exists():
                skipped += 1
                continue

            billing = ClientBilling(
                client=client,
                academic_year=r.academic_year,
                student_count=r.student_count,
                rate=r.rate,
                one_time_payment=r.one_time_payment,
                override_amounts=r.override_amounts,
                taxable_value=r.taxable_value,
                gst_amount=r.gst_amount,
                net_amount=r.net_amount,
                previous_pending=r.previous_pending,
                engineer=r.engineer,
                invoice_status=r.invoice_status,
                remarks=r.remarks,
            )
            billing.save()
            created_billings += 1

            if r.received:
                PaymentReceipt.objects.create(
                    billing=billing,
                    amount=r.received,
                    received_on=None,
                    note="Imported opening balance from sheet",
                )
    return {
        "clients_created": created_clients,
        "billings_created": created_billings,
        "skipped": skipped,
    }
