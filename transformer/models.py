"""Core data model: Evidence atoms, source records, canonical type map.

Every extracted value is born as an Evidence atom (DESIGN.md ADR-004). Merging
is a pure function over a canonically sorted pool of atoms — that single fact
makes provenance free and reruns byte-identical (ADR-016).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


def value_repr(value: object) -> str:
    """Stable string form of any evidence value; used only inside sort keys."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class Evidence:
    field_path: str          # canonical path, e.g. "emails", "experience"
    value: object            # normalized value (pass-1 where applicable)
    raw_value: object        # exactly as seen in the source
    source_id: str           # file-level id, e.g. "recruiters.csv"
    source_type: str         # adapter type; keys constants.SOURCE_TRUST
    method: str              # e.g. "direct_field", "regex:email_v1"
    record_id: str           # per-candidate record, e.g. "recruiters.csv#row=2"
    order_index: int = 0     # stable position within the record
    normalized: bool = True  # False => value kept raw, surfaced in run report

    def sort_key(self):
        # Canonical evidence sort key (PLAN.md §3.1): the one ordering every
        # stage applies before iterating, so input file order can never leak
        # into output. field_path first groups atoms for the merge stage.
        return (
            self.field_path,
            value_repr(self.value),
            self.source_type,
            self.source_id,
            self.record_id,
            self.order_index,
            self.method,
        )


@dataclass
class SourceRecord:
    """One candidate as seen by one source (a CSV row, an ATS entry, a file)."""

    record_id: str
    source_id: str
    source_type: str
    evidence: list[Evidence] = field(default_factory=list)
    updated_at: str | None = None  # in-band recency only, never mtime (ADR-016)
    flags: list[str] = field(default_factory=list)


# Canonical paths a projection config may reference, and their types
# (ADR-011). "X[]" entries are the element reached through a map or index.
# skills[].sources is deliberately absent: string[][] is outside the type
# vocabulary, so configs cannot project it.
CANONICAL_TYPES: dict[str, str] = {
    "candidate_id": "string",
    "full_name": "string",
    "headline": "string",
    "years_experience": "number",
    "emails": "string[]",
    "phones": "string[]",
    "location": "object",
    "location.city": "string",
    "location.region": "string",
    "location.country": "string",
    "links": "object",
    "links.linkedin": "string",
    "links.github": "string",
    "links.portfolio": "string",
    "links.other": "string[]",
    "skills": "object[]",
    "skills[].name": "string",
    "skills[].confidence": "number",
    "experience": "object[]",
    "experience[].company": "string",
    "experience[].title": "string",
    "experience[].start": "string",
    "experience[].end": "string",
    "experience[].summary": "string",
    "experience[].is_current": "boolean",
    "education": "object[]",
    "education[].institution": "string",
    "education[].degree": "string",
    "education[].field": "string",
    "education[].end_year": "number",
}

TYPE_VOCABULARY = frozenset(
    {"string", "number", "boolean", "object", "string[]", "number[]", "object[]"}
)
