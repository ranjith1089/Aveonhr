"""Template helpers for the shared FlyonUI-inspired theme (left rail nav)."""
from django import template

register = template.Library()


@register.filter(name="has_module")
def has_module(membership, module: str) -> bool:
    """``{% if request.membership|has_module:"payroll" %}`` - module gate for
    rail links. Unknown/missing membership hides the link."""
    if membership is None:
        return False
    try:
        return bool(membership.has_module(module))
    except (AttributeError, KeyError):
        return False


@register.filter(name="get_item")
def get_item(mapping, key):
    """``{{ dict|get_item:key }}`` - dictionary lookup with a variable key."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""


@register.filter(name="initials")
def initials(name) -> str:
    """'Priya Natarajan' -> 'PN'. Used for avatar circles."""
    parts = [p for p in str(name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"
