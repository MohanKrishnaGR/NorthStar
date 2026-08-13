"""String intake normalization (DESIGN.md ADR-016).

Every string entering the system passes through nfc(); every comparison uses
fold(). Otherwise "José" (NFD) and "José" (NFC) — visually identical —
become a phantom name conflict.
"""
from __future__ import annotations

import unicodedata


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s)).strip()


def fold(s: str) -> str:
    """Comparison form: NFC + casefold (not lower — casefold handles ß etc.)."""
    return nfc(s).casefold()


# Strings that mean "no value" in real exports. Checked at adapter intake so
# "N/A" never becomes someone's phone number or employer (GOLDEN_DATASET §8.4).
NULL_MARKERS = frozenset({
    "", "-", "--", "—", "–", "n/a", "n.a", "na", "none", "null", "nil",
    "tbd", "unknown", "?",
})


def is_null_marker(s: object) -> bool:
    return fold(str(s)).strip(" .") in NULL_MARKERS


def strip_accents(s: str) -> str:
    """Accent-insensitive comparison form ("José" ~ "Jose"). Comparison only —
    stored values always keep their accents."""
    decomposed = unicodedata.normalize("NFD", fold(s))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
