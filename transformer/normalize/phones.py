"""Phone normalization to E.164 — never guesses a region (ADR-009).

A number without +CC normalizes only when an explicit region is supplied:
pass 1 uses the operator's --default-region, pass 2 (post-merge) uses the
cluster's resolved country. No region, no E.164 — the raw value is preserved
and reported, never laundered into false precision.
"""
from __future__ import annotations

import re

import phonenumbers

EXT_RE = re.compile(r"\s*(?:ext\.?|extension|x)\s*\d+\s*$", re.IGNORECASE)
CANDIDATE_RE = re.compile(r"\+?\d[\d\s\-().]{6,}\d")


def strip_extension(raw: str) -> str:
    return EXT_RE.sub("", str(raw).strip())


def to_e164(raw: object, region: str | None = None) -> str | None:
    """E.164 string, or None. Idempotent: an E.164 input returns itself."""
    s = strip_extension(str(raw))
    if s.startswith("+"):
        region = None  # explicit country code always wins
    elif region is None:
        return None  # no context — refuse rather than assume (ADR-009)
    try:
        parsed = phonenumbers.parse(s, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def split_cell(raw: object) -> list[str]:
    """Split a multi-number cell ('x / y', 'x; y') into candidate strings."""
    parts = re.split(r"[/;,]|\band\b", str(raw))
    return [p.strip() for p in parts if any(ch.isdigit() for ch in p)]


def find_all(body: str) -> list[str]:
    """Phone-shaped substrings in free text, in document order."""
    return [m.group(0).strip() for m in CANDIDATE_RE.finditer(body)]
