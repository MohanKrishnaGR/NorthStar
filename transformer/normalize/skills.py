"""Skill canonicalization: fold pipeline + curated alias dictionary (ADR-010).

Unknown skills are kept verbatim (folded) and flagged canonical=False — never
dropped, never force-mapped to the nearest known skill.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import text

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "skill_aliases.json"

# Keep +, #, . so c++, c#, node.js survive folding.
_STRIP_RE = re.compile(r"[^a-z0-9+#.\s]")
_VERSION_RE = re.compile(r"\s+v?\d+(\.\d+)*$")
_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def aliases() -> dict[str, str]:
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


def fold_skill(raw: object) -> str:
    s = text.fold(str(raw))
    s = _STRIP_RE.sub(" ", s)
    s = _VERSION_RE.sub("", s)
    return _WS_RE.sub(" ", s).strip(" .")


def canonicalize(raw: object) -> tuple[str, bool]:
    """(canonical_name, True) on a dictionary hit; (folded_raw, False) miss."""
    f = fold_skill(raw)
    hit = aliases().get(f)
    return (hit, True) if hit else (f, False)


# Aliases that are ordinary English words: valid in an explicit skills field
# (canonicalize), but scanning prose for them would invent skills from
# sentences like "we go over the rest of the plan".
_SCAN_EXCLUDE = frozenset({"go", "rest", "spring", "express", "swift", "js"})


@lru_cache(maxsize=1)
def _scan_patterns() -> list[tuple[re.Pattern, str]]:
    # Longest aliases first so "machine learning" beats "machine"; boundaries
    # exclude identifier-ish chars so "javascript" doesn't hit inside a word.
    pats = []
    for alias in sorted(set(aliases()) - _SCAN_EXCLUDE, key=lambda a: (-len(a), a)):
        pats.append(
            (re.compile(rf"(?<![a-z0-9+#]){re.escape(alias)}(?![a-z0-9+#])"), alias)
        )
    return pats


def find_all(body: str) -> list[str]:
    """Canonical skill names found in free text, sorted, deduped."""
    folded = text.fold(body)
    found = set()
    for pat, alias in _scan_patterns():
        if pat.search(folded):
            found.add(aliases()[alias])
    return sorted(found)


def find_spans(body: str) -> dict[str, tuple[int, int]]:
    """First-occurrence span per canonical skill, searched on lower(body) so
    offsets map back to the original text. Grounding only (UI locators) —
    membership always comes from find_all."""
    low = body.lower()
    out: dict[str, tuple[int, int]] = {}
    for pat, alias in _scan_patterns():
        m = pat.search(low)
        if m:
            canon = aliases()[alias]
            if canon not in out or m.start() < out[canon][0]:
                out[canon] = (m.start(), m.end())
    return out
