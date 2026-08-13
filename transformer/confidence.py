"""Confidence scoring: transparent noisy-OR arithmetic (ADR-007).

Every number here is reproducible by hand from constants.py:
    strength  s = source_trust x method_reliability
    agreement   = 1 - prod(1 - s_i)   over sources agreeing with the winner
    support     = sum(s_agree) / sum(s_all)
    confidence  = agreement * support
Set elements skip the support penalty: a source that does not list an element
is a partial view, not a contradiction. Scores are ordinal, not calibrated
probabilities — the README says so too.
"""
from __future__ import annotations

from .constants import CORE_FIELD_WEIGHTS, strength
from .models import Evidence, value_repr


def _per_source_strengths(atoms: list[Evidence]) -> dict[str, float]:
    """Max strength per source file — corroboration counts once per source,
    so a duplicated CSV row cannot vouch for itself (DESIGN §5 row 9)."""
    out: dict[str, float] = {}
    for a in atoms:
        s = strength(a.source_type, a.method)
        if s > out.get(a.source_id, 0.0):
            out[a.source_id] = s
    return out


def _noisy_or(strengths) -> float:
    p = 1.0
    for s in strengths:
        p *= 1.0 - s
    return 1.0 - p


def scalar_trace(all_atoms: list[Evidence], winner_atoms: list[Evidence]) -> dict:
    """The full arithmetic behind a scalar score — what the UI's "show the
    math" panel renders. scalar_confidence() is its final number."""
    win = _per_source_strengths(winner_atoms)
    agreement = _noisy_or(win.values())
    groups: dict[tuple[str, str], float] = {}
    for a in all_atoms:
        k = (a.source_id, value_repr(a.value))
        s = strength(a.source_type, a.method)
        if s > groups.get(k, 0.0):
            groups[k] = s
    total = sum(groups.values())
    support = sum(win.values()) / total if total else 0.0
    return {
        "per_source": {k: round(v, 6) for k, v in sorted(win.items())},
        "competing_total": round(total, 6),
        "agreement": round(agreement, 6),
        "support": round(support, 6),
        "confidence": round(agreement * support, 6),
    }


def scalar_confidence(all_atoms: list[Evidence], winner_atoms: list[Evidence]) -> float:
    """Confidence in a chosen value, penalized by disagreeing evidence."""
    return scalar_trace(all_atoms, winner_atoms)["confidence"]


def element_trace(atoms: list[Evidence]) -> dict:
    per_source = _per_source_strengths(atoms)
    return {
        "per_source": {k: round(v, 6) for k, v in sorted(per_source.items())},
        "confidence": round(_noisy_or(per_source.values()), 6),
    }


def element_confidence(atoms: list[Evidence]) -> float:
    """Set elements (emails, phones, skills, links): pure noisy-OR, support=1."""
    return element_trace(atoms)["confidence"]


def overall(field_conf: dict[str, float]) -> float:
    """Weighted mean over core fields; an empty field contributes 0 — the
    overall score measures trust in the whole profile, and honest emptiness
    still lowers that (ADR-007)."""
    total_w = sum(CORE_FIELD_WEIGHTS.values())
    got = sum(w * field_conf.get(f, 0.0) for f, w in CORE_FIELD_WEIGHTS.items())
    return round(got / total_w, 6)
