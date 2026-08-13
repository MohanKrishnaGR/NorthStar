"""ATS JSON adapter — foreign field names mapped declaratively (ADR-002).

The mapping tables below are data, not code: when the real sample files
arrive, adjusting them is the only expected change. Accepts a bare object,
an array, or {"candidates": [...]}.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import country, dates, emails, phones, skills, text, urls
from .base import SourceResult, read_text

SOURCE_TYPE = "ats_json"

# Foreign name -> canonical scalar target.
_SCALAR_MAP = {
    "candidateName": "full_name",
    "candidate_name": "full_name",
    "fullName": "full_name",
    "headline": "headline",
    "summary": "headline",
}
_EMAIL_KEYS = ("emailAddress", "email_id", "email")
_PHONE_KEYS = ("phoneNumber", "contact_phone", "phone")
_URL_KEYS = ("profileUrls", "links", "urls")
_UPDATED_KEYS = ("lastUpdated", "updated_at", "modifiedAt")
_WORK_KEYS = ("workHistory", "work_history", "employment")
_EDU_KEYS = ("schooling", "education")
# An empty "to" is an *unknown* end, not "present" — is_current is only ever
# asserted, never inferred from absence (DESIGN.md north star).
_PRESENT_WORDS = {"present", "current", "now", "ongoing"}


def detect(path: Path) -> bool:
    return path.suffix.lower() == ".json"


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    doc = json.loads(read_text(path))
    if isinstance(doc, dict) and isinstance(doc.get("candidates"), list):
        entries = doc["candidates"]
    elif isinstance(doc, dict):
        entries = [doc]
    elif isinstance(doc, list):
        entries = doc
    else:
        raise ValueError("ATS JSON is neither an object nor an array")

    if isinstance(doc, dict) and isinstance(doc.get("candidates"), list):
        prefix_fmt = "candidates[{i}]"
    elif isinstance(doc, list):
        prefix_fmt = "[{i}]"
    else:
        prefix_fmt = ""

    for i, entry in enumerate(entries):
        res.records_read += 1
        rid = f"{res.source_id}#idx={i}"
        if not isinstance(entry, dict):
            res.errors.append(f"{rid}: entry is not an object")
            continue
        rec = SourceRecord(record_id=rid, source_id=res.source_id,
                           source_type=SOURCE_TYPE)
        for k in _UPDATED_KEYS:
            if entry.get(k):
                rec.updated_at = text.nfc(str(entry[k]))
                break
        order = 0
        prefix = prefix_fmt.format(i=i)

        def jp(key: str) -> dict:
            path = f"{prefix}.{key}" if prefix else key
            return {"kind": "path", "path": path}

        def add(field_path, value, raw, method="direct_field", normalized=True,
                locator=None):
            nonlocal order
            rec.evidence.append(Evidence(
                field_path=field_path, value=value, raw_value=raw,
                source_id=res.source_id, source_type=SOURCE_TYPE,
                method=method, record_id=rid, order_index=order,
                normalized=normalized, locator=locator))
            order += 1

        for foreign, target in _SCALAR_MAP.items():
            v = _s(entry, foreign)
            if v:
                add(target, v, entry[foreign], locator=jp(foreign))

        for k in _EMAIL_KEYS:
            v = _s(entry, k)
            if v:
                norm = emails.normalize(v)
                if norm:
                    add("emails", norm, entry[k], locator=jp(k))
                else:
                    res.note_unparseable("emails", entry[k], "not_an_email")

        for k in _PHONE_KEYS:
            v = _s(entry, k)  # also coerces JSON-number phones to strings
            if v:
                e164 = phones.to_e164(v, ctx.get("default_region"))
                if e164:
                    add("phones", e164, entry[k], locator=jp(k))
                else:
                    add("phones_raw", v, entry[k], normalized=False,
                        locator=jp(k))

        for k in _URL_KEYS:
            for j, u in enumerate(entry.get(k) or []):
                bucket, cleaned = urls.classify(str(u))
                add(f"links.{bucket}", cleaned, u, locator=jp(f"{k}[{j}]"))

        raw_skills = entry.get("skills") or []
        if isinstance(raw_skills, str):
            # Some ATS exports join skills into one string; never iterate a
            # string as characters.
            raw_skills = [p for p in raw_skills.split(",") if p.strip()]
        for j, raw_skill in enumerate(raw_skills):
            if text.is_null_marker(raw_skill):
                continue
            name, canonical = skills.canonicalize(raw_skill)
            add("skills", {"name": name, "canonical": canonical}, raw_skill,
                method="dict:skill_alias_v1", locator=jp(f"skills[{j}]"))

        for k in ("totalYearsExperience", "yearsOfExperience", "experience_years"):
            v = entry.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                # A *stated* claim — the merge stage prefers range-derived
                # values and records this as an alternative (ADR-006).
                add("years_experience", v, v, locator=jp(k))
                break

        loc = _location_of(entry)
        if loc:
            add("location", loc, json.dumps(loc, sort_keys=True),
                locator=jp("city"))

        cur_company = _s(entry, "currentEmployer", "current_employer")
        cur_title = _s(entry, "designation", "jobTitle")
        if cur_company or cur_title:
            add("experience", {
                "company": cur_company, "title": cur_title,
                "start": None, "end": None, "is_current": True, "summary": None,
            }, f"{cur_company}|{cur_title}",
                locator=jp("currentEmployer" if cur_company else "designation"))

        for k in _WORK_KEYS:
            for j, job in enumerate(entry.get(k) or []):
                if not isinstance(job, dict):
                    continue
                to_raw = str(job.get("to") or "")
                is_current = text.fold(to_raw) in _PRESENT_WORDS and bool(job.get("from"))
                add("experience", {
                    "company": _s(job, "org", "company", "employer"),
                    "title": _s(job, "role", "title", "position"),
                    "start": dates.parse(job.get("from") or ""),
                    "end": None if is_current else dates.parse(to_raw),
                    "is_current": is_current,
                    "summary": _s(job, "description", "summary"),
                }, json.dumps(job, sort_keys=True), locator=jp(f"{k}[{j}]"))

        for k in _EDU_KEYS:
            for j, edu in enumerate(entry.get(k) or []):
                if not isinstance(edu, dict):
                    continue
                end_year = edu.get("endYear") or edu.get("end_year")
                parsed_year = dates.parse(str(end_year)) if end_year else None
                add("education", {
                    "institution": _s(edu, "school", "institution"),
                    "degree": _s(edu, "degree"),
                    "field": _s(edu, "fieldOfStudy", "field", "major"),
                    "end_year": parsed_year[0] if parsed_year else None,
                }, json.dumps(edu, sort_keys=True), locator=jp(f"{k}[{j}]"))

        if rec.evidence:
            res.records.append(rec)


def _s(d: dict, *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = text.nfc(str(v))
        if s and not text.is_null_marker(s):
            return s
    return None


def _location_of(entry: dict) -> dict | None:
    city = _s(entry, "city")
    region = _s(entry, "region", "state")
    ctry = entry.get("country")
    iso = country.to_iso2(ctry) if ctry else None
    if not any([city, region, iso]):
        return None
    return {"city": city, "region": region, "country": iso}
