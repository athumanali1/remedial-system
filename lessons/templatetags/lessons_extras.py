from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Safely get a value from a dict in templates: {{ mydict|dict_get:key }}"""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""


@register.filter
def index(sequence, i):
    """Return sequence[i] or empty string if out of range/invalid."""
    try:
        return sequence[i]
    except Exception:
        return ""


@register.filter
def short_class(name):
    """Abbreviate class names e.g. 'FORM 2 NORTH' -> 'F2N'."""
    if not isinstance(name, str):
        return name
    parts = name.strip().upper().split()
    # Expect patterns like ['FORM', '2', 'NORTH']
    if len(parts) >= 3 and parts[0] == "FORM" and parts[1].isdigit():
        num = parts[1]
        letter = parts[2][0] if parts[2] else ""
        return f"F{num}{letter}"
    return name


@register.filter
def short_subject(name):
    """Abbreviate common subject names e.g. 'MATHEMATICS' -> 'Math'."""
    if not isinstance(name, str):
        return name
    key = name.strip().upper()
    mapping = {
        "MATHEMATICS": "Math",
        "MATH": "Math",
        "ENGLISH": "Eng",
        "KISWAHILI": "Kis",
        "BIOLOGY": "Bio",
        "PHYSICS": "Pyc",
        "AGRICULTURE": "Agric",
        "BUSINESS": "Buss",
        "COMPUTER": "Comp",
        "HISTORY": "Hist",
        "GEOGRAPHY": "Geo",
    }
    return mapping.get(key, name)
