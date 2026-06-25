"""Template filters used by proposal templates."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter(name="inr")
def inr(value) -> str:
    """
    Indian-style comma grouping for whole rupees.

    500000 -> 5,00,000
    59000  -> 59,000
    """
    if value is None or value == "":
        return ""
    try:
        n = int(Decimal(str(value)).to_integral_value())
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return f"{sign}{s}"
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return f"{sign}{','.join(parts)},{last3}"
