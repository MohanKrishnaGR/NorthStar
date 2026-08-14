"""Scoring reference data: loaded from data/scoring.json, versioned (OPS_PLAN §2.1).

The values are judgment calls made inspectable AND governable: every
confidence number in the output traces back to one versioned file plus
arithmetic a reviewer can redo by hand. Changing that file is a reviewed
event — the run report records `scoring_version`, CI checks the checksum
discipline (tests/test_reference_data.py), and gold outputs are regenerated
and re-reviewed as part of the same change.

Rationale for the values (kept here because JSON has no comments):

- SOURCE_TRUST — how much we trust a source's claims a priori. An ATS record
  was entered by a recruiter into a system of record (highest); a CSV export
  is the same data minus system validation; LinkedIn is self-reported but
  platform-structured; GitHub profile fields are self-authored; a resume is
  self-reported prose; free-text notes are hearsay written at speed.
  "derived" atoms carry trust 1.0 because their uncertainty is expressed in
  METHOD_RELIABILITY instead — never in both.

- METHOD_RELIABILITY — how much the extraction technique preserves the
  source's intent. A directly mapped field is the source's own claim; a
  regex hit is that claim seen through a pattern; a dictionary lookup adds
  an alias-table hop; a derived value is our arithmetic on top of their
  claims. phones_pass2 is the same parse as pass 1 — only the region came
  from the cluster.

- CORE_FIELD_WEIGHTS — weights for overall_confidence (ADR-007). Identity
  fields dominate because a profile whose name/email are shaky is unusable
  regardless of the rest. An empty field contributes 0: overall confidence
  measures how much the whole profile can be trusted, and honest emptiness
  still lowers that.
"""
from __future__ import annotations

import json
from pathlib import Path

_SCORING_PATH = Path(__file__).resolve().parent.parent / "data" / "scoring.json"

with open(_SCORING_PATH, encoding="utf-8") as _f:
    _SCORING = json.load(_f)

SCORING_VERSION: str = _SCORING["version"]
SOURCE_TRUST: dict[str, float] = _SCORING["source_trust"]
METHOD_RELIABILITY: dict[str, float] = _SCORING["method_reliability"]
CORE_FIELD_WEIGHTS: dict[str, int] = _SCORING["core_field_weights"]

# Sources whose record boundary is an assumption (one candidate per file),
# guarded by the multi-identity rule in identity.py (ADR-005). Structural,
# not tunable — stays in code.
UNSTRUCTURED_TYPES = frozenset({"notes_txt", "resume"})


def method_reliability(method: str) -> float:
    """Reliability of a method string; the family prefix before ':' keys it."""
    return METHOD_RELIABILITY[method.split(":", 1)[0]]


def strength(source_type: str, method: str) -> float:
    """Evidence strength s = source_trust x method_reliability (ADR-007)."""
    return SOURCE_TRUST[source_type] * method_reliability(method)
