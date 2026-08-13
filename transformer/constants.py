"""Trust, reliability, and weight tables (DESIGN.md ADR-006/007).

These are judgment calls made inspectable: every confidence number in the
output traces back to this file plus arithmetic a reviewer can redo by hand.
They are deliberately constants, not config — changing them changes what the
scores *mean*, which should be a reviewed code change, not a runtime knob.
"""
from __future__ import annotations

# How much we trust a source's claims a priori. An ATS record was entered by
# a recruiter into a system of record (highest); a CSV export is the same data
# minus system validation; a resume is self-reported; free-text notes are
# hearsay written at speed. "derived" atoms carry trust 1.0 because their
# uncertainty is expressed in METHOD_RELIABILITY instead — never in both.
SOURCE_TRUST: dict[str, float] = {
    "ats_json": 0.90,
    "recruiter_csv": 0.85,
    "linkedin_json": 0.80,  # self-reported but platform-structured (recorded fixture)
    "github_json": 0.75,    # platform-verified login; profile fields self-authored
    "resume": 0.70,
    "notes_txt": 0.50,
    "derived": 1.00,
}

# How much the extraction technique preserves the source's intent. A directly
# mapped field is the source's own claim; a regex hit is that claim seen
# through a pattern; a dictionary lookup adds an alias-table hop; a derived
# value is our arithmetic on top of their claims.
METHOD_RELIABILITY: dict[str, float] = {
    "direct_field": 1.00,
    "regex": 0.90,
    "phones_pass2": 0.90,  # same parse as pass 1; region came from the cluster
    "dict": 0.85,
    "derived": 0.60,
}

# Weights for overall_confidence (ADR-007). Identity fields dominate because a
# profile whose name/email are shaky is unusable regardless of the rest.
# A field that is empty contributes 0 — overall confidence measures how much
# the whole profile can be trusted, and honest emptiness still lowers that.
CORE_FIELD_WEIGHTS: dict[str, int] = {
    "full_name": 3,
    "emails": 3,
    "phones": 2,
    "skills": 2,
    "experience": 2,
    "location": 1,
    "headline": 1,
    "years_experience": 1,
    "education": 1,
    "links": 1,
}

# Sources whose record boundary is an assumption (one candidate per file),
# guarded by the multi-identity rule in identity.py (ADR-005).
UNSTRUCTURED_TYPES = frozenset({"notes_txt", "resume"})


def method_reliability(method: str) -> float:
    """Reliability of a method string; the family prefix before ':' keys it."""
    return METHOD_RELIABILITY[method.split(":", 1)[0]]


def strength(source_type: str, method: str) -> float:
    """Evidence strength s = source_trust x method_reliability (ADR-007)."""
    return SOURCE_TRUST[source_type] * method_reliability(method)
