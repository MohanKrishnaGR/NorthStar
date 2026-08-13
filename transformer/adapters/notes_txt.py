"""Recruiter notes adapter: deterministic rule-based extraction (ADR-003).

One candidate per file — an assumption the identity stage guards with the
multi-identity rule (ADR-005). Notes contribute contact info, links, skills,
labeled fields, and simple "Title at Company <range>" experience lines.
No NER, no LLM: missed values become null, which the problem prefers to guesses.

scan_into() is shared with the resume adapter — same rules, different trust
(the source_type on the record decides the weight, not the extractor).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import country as country_mod
from ..normalize import dates, emails, phones, skills, text, urls
from .base import SourceResult, read_text

SOURCE_TYPE = "notes_txt"

_LABEL_NAME_RE = re.compile(r"(?im)^(?:name|candidate)\s*[:\-]\s*(.+)$")
_LABEL_TITLE_RE = re.compile(r"(?im)^(?:role|title)\s*[:\-]\s*(.+)$")
_LABEL_LOCATION_RE = re.compile(r"(?im)^(?:location|based in)\s*[:\-]\s*(.+)$")
# Consecutive Capitalized words after " at " — stops at lowercase words like
# "since" AND at capitalized month names, so both "at BlueYonder Analytics
# since Jun 2021" and "at Nimbus Retail Feb 2018 - May 2021" capture only the
# company.
_MONTH_STOP = r"(?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b)"
_AT_COMPANY_RE = re.compile(
    r"\bat\s+((?:[A-Z][\w&.']*)(?:\s+(?:" + _MONTH_STOP + r"[A-Z][\w&.']*|of|the))*)"
)


def detect(path: Path) -> bool:
    return path.suffix.lower() == ".txt"


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    body = read_text(path)
    rec = SourceRecord(record_id=f"{res.source_id}#file",
                       source_id=res.source_id, source_type=SOURCE_TYPE)
    scan_into(rec, body, ctx)
    res.records_read = 1
    if rec.evidence:
        res.records.append(rec)


def scan_into(rec: SourceRecord, body: str, ctx: dict) -> None:
    """Run every free-text extractor over body, appending Evidence to rec.
    Every atom carries a character-span locator so the UI can ground it."""

    def span(start: int, end: int) -> dict:
        return {"kind": "span", "start": start, "end": end}

    def add(field_path, value, raw, method, normalized=True, locator=None):
        rec.evidence.append(Evidence(
            field_path=field_path, value=value, raw_value=raw,
            source_id=rec.source_id, source_type=rec.source_type,
            method=method, record_id=rec.record_id,
            order_index=len(rec.evidence), normalized=normalized,
            locator=locator))

    m = _LABEL_NAME_RE.search(body)
    if m:
        add("full_name", text.nfc(m.group(1)), m.group(1),
            "regex:labeled_name_v1", locator=span(*m.span(1)))
    m = _LABEL_TITLE_RE.search(body)
    if m:
        add("headline", text.nfc(m.group(1)), m.group(1),
            "regex:labeled_title_v1", locator=span(*m.span(1)))
    m = _LABEL_LOCATION_RE.search(body)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        iso = country_mod.to_iso2(parts[-1], codes=False) if len(parts) > 1 else None
        add("location", {
            "city": text.nfc(parts[0]) if parts else None,
            "region": None,
            "country": iso,
        }, m.group(1), "regex:labeled_location_v1", locator=span(*m.span(1)))

    for m in emails.EMAIL_RE.finditer(body):
        norm = emails.normalize(m.group(0))
        if norm:
            add("emails", norm, m.group(0), "regex:email_v1",
                locator=span(*m.span()))

    seen_phones = set()
    for m in phones.CANDIDATE_RE.finditer(body):
        raw_phone = m.group(0).strip()
        e164 = phones.to_e164(raw_phone, ctx.get("default_region"))
        if e164 and e164 not in seen_phones:
            seen_phones.add(e164)
            add("phones", e164, raw_phone, "regex:phone_v1",
                locator=span(*m.span()))
        # >= 9 digits: below that, free-text "phone" candidates are usually
        # year ranges ("2018 - 2021" has 8 digits) — noise, not numbers.
        elif not e164 and sum(ch.isdigit() for ch in raw_phone) >= 9:
            add("phones_raw", raw_phone, raw_phone,
                "regex:phone_v1", normalized=False, locator=span(*m.span()))

    for m in urls.URL_RE.finditer(body):
        bucket, cleaned = urls.classify(m.group(0))
        add(f"links.{bucket}", cleaned, m.group(0), "regex:url_v1",
            locator=span(*m.span()))

    skill_spans = skills.find_spans(body)
    for name in skills.find_all(body):
        loc = span(*skill_spans[name]) if name in skill_spans else None
        add("skills", {"name": name, "canonical": True}, name,
            "dict:skill_scan_v1", locator=loc)

    pos = 0
    for raw_line in body.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        line_span = span(pos, pos + len(line))
        pos += len(raw_line)
        rng = dates.parse_range(line)
        if not rng:
            continue
        start, end, is_current = rng
        cm = _AT_COMPANY_RE.search(line)
        company = text.nfc(cm.group(1)) if cm else None
        title = None
        if cm:
            prefix = line[: cm.start()].strip(" .;,-")
            if 0 < len(prefix) <= 60 and ":" not in prefix:
                title = text.nfc(prefix)
        if company or title:
            add("experience", {
                "company": company, "title": title, "start": start,
                "end": end, "is_current": is_current, "summary": None,
            }, line.strip(), "regex:experience_line_v1", locator=line_span)
