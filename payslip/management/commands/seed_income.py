"""Load the income seed data (generated from the original ODS sheet).

Dry-run by default; pass --commit to write. Safely re-runnable: existing
(client, academic year) rows are skipped.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from payslip.income_seed import SEED_ROWS
from payslip.services.income_import import ImportResult, ParsedRow, apply_import


def _rows() -> ImportResult:
    result = ImportResult()
    for r in SEED_ROWS:
        result.rows.append(ParsedRow(
            client_name=r["client"],
            academic_year=r["academic_year"],
            student_count=r["student_count"],
            rate=Decimal(r["rate"]) if r["rate"] is not None else None,
            one_time_payment=Decimal(r["one_time_payment"]),
            override_amounts=r["override_amounts"],
            taxable_value=Decimal(r["taxable_value"]) if r["taxable_value"] is not None else None,
            gst_amount=Decimal(r["gst_amount"]),
            net_amount=Decimal(r["net_amount"]),
            previous_pending=Decimal(r["previous_pending"]),
            received=Decimal(r["received"]),
            engineer=r["engineer"],
            invoice_status=r["invoice_status"],
            remarks=r["remarks"],
            agreement_status=r["agreement_status"],
            is_active=r["is_active"],
        ))
    return result


class Command(BaseCommand):
    help = "Seed the income module from the original payment follow-up sheet."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Actually write to the database.")

    def handle(self, *args, **options):
        result = _rows()
        total = sum(
            (r.net_amount + r.previous_pending - r.received for r in result.rows),
            Decimal("0"),
        )
        self.stdout.write(f"Seed rows: {len(result.rows)}; expected outstanding total: {total}")
        if not options["commit"]:
            self.stdout.write("Dry run only - pass --commit to load.")
            return
        stats = apply_import(result)
        self.stdout.write(self.style.SUCCESS(
            f"Done: {stats['clients_created']} clients, "
            f"{stats['billings_created']} billing rows, {stats['skipped']} skipped."
        ))
