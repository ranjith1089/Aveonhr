"""Analytics and revenue forecasting for the Income module.

Everything is Decimal; floats never touch money. Data volumes are tens of
rows, so aggregation happens in Python over one annotated queryset (avoids
the classic double-count when summing across the payments join).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from ..models import ClientBilling, PaymentReceipt

TWO_DP = Decimal("0.01")
GST = Decimal("1.18")


def _annotated_billings():
    return (
        ClientBilling.objects.select_related("client")
        .annotate(received_sum=Coalesce(
            Sum("payments__amount"), Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ))
    )


def _pct(part: Decimal, whole: Decimal) -> int:
    if whole <= 0:
        return 0
    return int(min(max(part / whole * 100, Decimal("0")), Decimal("100")))


def build_analytics() -> dict:
    billings = list(_annotated_billings())

    # ---- Per-FY billed / received / outstanding ----------------------------
    fy: dict[str, dict] = {}
    for b in billings:
        row = fy.setdefault(b.academic_year, {
            "year": b.academic_year, "year_start": b.year_start,
            "billed": Decimal("0"), "received": Decimal("0"), "outstanding": Decimal("0"),
        })
        row["billed"] += b.total_due
        row["received"] += b.received_sum
        row["outstanding"] += b.total_due - b.received_sum
    fy_rows = sorted(fy.values(), key=lambda r: r["year_start"])
    for row in fy_rows:
        row["collection_pct"] = _pct(row["received"], row["billed"])

    grand_outstanding = sum((r["outstanding"] for r in fy_rows), Decimal("0"))

    # ---- Client-wise outstanding (ranked) ----------------------------------
    per_client: dict[int, dict] = {}
    for b in billings:
        row = per_client.setdefault(b.client_id, {
            "client_id": b.client_id, "name": b.client.name,
            "engineer": "", "engineer_year": -1,
            "billed": Decimal("0"), "received": Decimal("0"), "balance": Decimal("0"),
            "is_active": b.client.is_active,
        })
        row["billed"] += b.total_due
        row["received"] += b.received_sum
        row["balance"] += b.total_due - b.received_sum
        if b.engineer and b.year_start > row["engineer_year"]:
            row["engineer"] = b.engineer
            row["engineer_year"] = b.year_start
    client_outstanding = sorted(per_client.values(), key=lambda r: r["balance"], reverse=True)
    positive_total = sum((r["balance"] for r in client_outstanding if r["balance"] > 0), Decimal("0"))
    for row in client_outstanding:
        row["share_pct"] = _pct(row["balance"], positive_total) if row["balance"] > 0 else 0
        row["collection_pct"] = _pct(row["received"], row["billed"])

    # ---- Engineer aggregates ------------------------------------------------
    eng: dict[str, dict] = {}
    for b in billings:
        if not b.engineer:
            continue
        row = eng.setdefault(b.engineer, {
            "engineer": b.engineer, "clients": set(),
            "billed": Decimal("0"), "received": Decimal("0"), "outstanding": Decimal("0"),
        })
        row["clients"].add(b.client_id)
        row["billed"] += b.total_due
        row["received"] += b.received_sum
        row["outstanding"] += b.total_due - b.received_sum
    engineer_rows = sorted(
        ({**r, "client_count": len(r.pop("clients"))} for r in eng.values()),
        key=lambda r: r["outstanding"], reverse=True,
    )

    # ---- Monthly received trend (dated payments only) ----------------------
    monthly = defaultdict(lambda: Decimal("0"))
    undated_total = Decimal("0")
    for received_on, amount in PaymentReceipt.objects.values_list("received_on", "amount"):
        if received_on:
            monthly[received_on.strftime("%Y-%m")] += amount
        else:
            undated_total += amount
    monthly_trend = [{"month": k, "amount": v} for k, v in sorted(monthly.items())]

    return {
        "fy_rows": fy_rows,
        "grand_outstanding": grand_outstanding,
        "client_outstanding": client_outstanding,
        "engineer_rows": engineer_rows,
        "monthly_trend": monthly_trend,
        "undated_received": undated_total,
    }


def build_forecast() -> dict:
    """Next-FY revenue forecast, two scenarios per active client.

    conservative: the client renews at the latest year's net amount.
    growth: for rate-based clients with >= 2 years of student counts, project
    the count forward by the client's average YoY growth and re-price at the
    latest rate + 18% GST. Fixed-fee or single-year clients fall back to the
    conservative figure (flagged).
    """
    billings = list(_annotated_billings().order_by("client__name", "year_start"))
    if not billings:
        return {"target_year": "", "rows": [], "conservative_total": Decimal("0"),
                "growth_total": Decimal("0"), "current_billed": Decimal("0"), "current_year": ""}

    max_start = max(b.year_start for b in billings)
    target_year = f"{max_start + 1}-{max_start + 2}"
    current_year = f"{max_start}-{max_start + 1}"

    by_client: dict[int, list[ClientBilling]] = defaultdict(list)
    for b in billings:
        by_client[b.client_id].append(b)

    rows = []
    conservative_total = Decimal("0")
    growth_total = Decimal("0")
    current_billed = sum(
        (b.net_amount or Decimal("0")) for b in billings if b.year_start == max_start
    )

    for client_billings in by_client.values():
        client = client_billings[0].client
        if not client.is_active:
            continue  # discontinued clients don't renew
        latest = max(client_billings, key=lambda b: b.year_start)
        conservative = latest.net_amount or Decimal("0")

        counts = [(b.year_start, b.student_count) for b in client_billings if b.student_count]
        counts.sort()
        note = ""
        projected_count = None
        if latest.rate and latest.student_count and len(counts) >= 2:
            growth_factors = []
            for (y1, c1), (y2, c2) in zip(counts, counts[1:]):
                if c1 and y2 == y1 + 1:
                    growth_factors.append(Decimal(c2) / Decimal(c1))
            if growth_factors:
                avg_growth = sum(growth_factors) / len(growth_factors)
                projected_count = int((Decimal(latest.student_count) * avg_growth)
                                      .to_integral_value(rounding=ROUND_HALF_UP))
                growth_amount = (Decimal(projected_count) * latest.rate * GST).quantize(
                    TWO_DP, rounding=ROUND_HALF_UP
                )
            else:
                growth_amount = conservative
                note = "no consecutive-year trend"
        else:
            growth_amount = conservative
            note = "fixed fee" if not latest.rate else "single year of data"

        rows.append({
            "client_id": client.pk,
            "name": client.name,
            "engineer": latest.engineer,
            "current_year": latest.academic_year,
            "current_net": conservative,
            "current_count": latest.student_count,
            "projected_count": projected_count,
            "conservative": conservative,
            "growth": growth_amount,
            "note": note,
        })
        conservative_total += conservative
        growth_total += growth_amount

    rows.sort(key=lambda r: r["growth"], reverse=True)
    return {
        "target_year": target_year,
        "current_year": current_year,
        "current_billed": current_billed,
        "rows": rows,
        "conservative_total": conservative_total,
        "growth_total": growth_total,
    }
