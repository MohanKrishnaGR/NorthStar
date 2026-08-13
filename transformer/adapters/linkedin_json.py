"""LinkedIn recorded-export adapter (ADR-017).

Reads an export-style payload (`linkedin_<slug>.json` — naming convention is
the detection rule). There is no sanctioned live API and scraping violates
ToS, so only pre-exported fixture data ever enters this path. Exports rarely
carry email/phone, so these records typically join clusters through the
profile-URL link key or the soft key.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import country as country_mod
from ..normalize import dates, text, urls
from .base import SourceResult, read_text

SOURCE_TYPE = "linkedin_json"


def detect(path: Path) -> bool:
    return path.suffix.lower() == ".json" and path.name.lower().startswith("linkedin_")


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    doc = json.loads(read_text(path))
    if not isinstance(doc, dict):
        raise ValueError("linkedin payload is not an object")
    rid = f"{res.source_id}#profile"
    rec = SourceRecord(record_id=rid, source_id=res.source_id,
                       source_type=SOURCE_TYPE)

    def add(field_path, value, raw, method="direct_field"):
        rec.evidence.append(Evidence(
            field_path=field_path, value=value, raw_value=raw,
            source_id=res.source_id, source_type=SOURCE_TYPE,
            method=method, record_id=rid, order_index=len(rec.evidence)))

    name = doc.get("fullName") or " ".join(
        p for p in (doc.get("firstName"), doc.get("lastName")) if p
    )
    if name and not text.is_null_marker(name):
        add("full_name", text.nfc(name), name)
    if doc.get("headline"):
        add("headline", text.nfc(str(doc["headline"])), doc["headline"])
    if doc.get("publicProfileUrl"):
        add("links.linkedin", urls.classify(str(doc["publicProfileUrl"]))[1],
            doc["publicProfileUrl"])

    loc = doc.get("location")
    if isinstance(loc, dict):
        iso = country_mod.to_iso2(loc.get("country") or "") if loc.get("country") else None
        add("location", {
            "city": text.nfc(loc["city"]) if loc.get("city") else None,
            "region": None, "country": iso,
        }, json.dumps(loc, sort_keys=True))

    for pos in doc.get("positions") or []:
        if not isinstance(pos, dict):
            continue
        start = _partial(pos.get("startDate"))
        end = _partial(pos.get("endDate"))
        is_current = bool(pos.get("isCurrent")) and end is None
        add("experience", {
            "company": _clean(pos.get("companyName")),
            "title": _clean(pos.get("title")),
            "start": start, "end": end, "is_current": is_current,
            "summary": _clean(pos.get("summary")),
        }, json.dumps(pos, sort_keys=True))

    for edu in doc.get("educations") or []:
        if not isinstance(edu, dict):
            continue
        end_year = edu.get("endYear")
        parsed = dates.parse(str(end_year)) if end_year else None
        add("education", {
            "institution": _clean(edu.get("schoolName")),
            "degree": _clean(edu.get("degreeName") or edu.get("degree")),
            "field": _clean(edu.get("fieldOfStudy")),
            "end_year": parsed[0] if parsed else None,
        }, json.dumps(edu, sort_keys=True))

    res.records_read = 1
    if rec.evidence:
        res.records.append(rec)


def _clean(v) -> str | None:
    if v is None or text.is_null_marker(v):
        return None
    return text.nfc(str(v))


def _partial(d) -> dates.PartialDate | None:
    if isinstance(d, dict) and d.get("year"):
        month = d.get("month")
        return (int(d["year"]), int(month) if month else None)
    return None
