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

# --- R2: education line grammar -------------------------------------------
# Precision-first: a bare degree token never fires — the line must also
# yield an institution (keyword-anchored capture). That's what keeps
# "Skills: MS Office 2016" from becoming an M.S. degree, and bare English
# "ma"/"ba"/"be" need their dots to count at all.
_DEGREE_RE = re.compile(
    r"(?i)\b(ph\.?d|m\.?tech|b\.?tech|m\.?eng|b\.?eng|mba|m\.?sc|b\.?sc|"
    r"m\.s|b\.s|ms|bs|m\.a|b\.a|b\.e|bachelor(?:'?s)?|master(?:'?s)?)\b"
)
_INSTITUTION_RE = re.compile(
    r"((?:[A-Z][\w.&']*\s+)*(?:University|Institute|College|School|Academy|"
    r"Polytechnic)(?:\s+of\s+[A-Z][\w']*(?:\s+[A-Z][\w']*)*)?"
    r"|(?:IIT|IIM|NIT|BITS)\s+[A-Z][\w']*)"
)
_FIELD_RE = re.compile(
    r"\bin\s+([A-Z][A-Za-z &]{2,40}?)(?=\s*(?:,|—|–|\(|\||$))"
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _parse_education_line(line: str) -> dict | None:
    s = line.strip()
    if not s or len(s) > 120:
        return None
    deg = _DEGREE_RE.search(s)
    inst = _INSTITUTION_RE.search(s)
    if not deg or not inst:
        return None
    fld = _FIELD_RE.search(s)
    years = _YEAR_RE.findall(s)
    return {
        "institution": text.nfc(inst.group(1)),
        "degree": text.nfc(deg.group(1)),
        "field": text.nfc(fld.group(1)) if fld else None,
        "end_year": int(years[-1]) if years else None,
    }


# --- R3: block-form experience ("Company — Title" over a pure range line) --
_HEADER_SPLIT_RE = re.compile(r"\s+(?:—|–|\||--)\s+|,\s+")
_COMPANY_HINT_RE = re.compile(
    r"\b(Inc|LLC|Ltd|Labs|Systems|Technologies|Analytics|Studio|Group|Cloud|"
    r"Software|Media|Bank|Retail|Press|Partners|Consulting)\b"
)
_RANGE_WORDS_RE = re.compile(r"(?i)\b(to|until|through|since|present|current|now)\b")
_RANGE_JUNK_RE = re.compile(r"[\s\-–—·|,()./]+")


def _is_pure_range_line(s: str) -> bool:
    """True when the line IS a date range, not prose that mentions dates:
    after removing date tokens and separators, almost nothing remains."""
    s = s.strip()
    if not s or not dates.parse_range(s):
        return False
    residue = dates.TOKEN_RE.sub("", s)
    residue = _RANGE_WORDS_RE.sub("", residue)
    residue = _RANGE_JUNK_RE.sub("", residue)
    return len(residue) <= 3


def _split_header(line: str) -> tuple[str, str] | None:
    """'Company — Title' (or Title-first) header, exactly two segments,
    carrying no dates of its own. Company = the segment with a company-ish
    suffix; otherwise first=company by stated convention — provenance keeps
    the raw line, so a wrong guess is auditable, never silent."""
    s = line.strip()
    if not s or len(s) > 120 or dates.parse(s) is not None:
        return None
    parts = [p.strip() for p in _HEADER_SPLIT_RE.split(s, maxsplit=1)
             if p and p.strip()]
    if len(parts) != 2:
        return None
    a, b = parts
    if not (a[:1].isupper() and b[:1].isupper() and len(a) <= 60 and len(b) <= 60):
        return None
    if _COMPANY_HINT_RE.search(b) and not _COMPANY_HINT_RE.search(a):
        return b, a
    return a, b


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

    # Line pass: education (R2), single-line experience, block experience (R3).
    lines: list[tuple[str, int, int]] = []
    pos = 0
    for raw_line in body.splitlines(keepends=True):
        stripped = raw_line.rstrip("\r\n")
        lines.append((stripped, pos, pos + len(stripped)))
        pos += len(raw_line)

    consumed: set[int] = set()
    for idx, (line, start_off, end_off) in enumerate(lines):
        if idx in consumed:
            continue
        line_span = span(start_off, end_off)

        edu = _parse_education_line(line)
        if edu:
            add("education", edu, line.strip(), "regex:education_line_v1",
                locator=line_span)
            continue

        rng = dates.parse_range(line)
        if rng:
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
            continue

        # R3: dateless "Company — Title" header + pure range on the next line.
        if idx + 1 < len(lines):
            nxt, _, nxt_end = lines[idx + 1]
            if _is_pure_range_line(nxt):
                header = _split_header(line)
                if header:
                    company, title = header
                    start, end, is_current = dates.parse_range(nxt)
                    add("experience", {
                        "company": text.nfc(company), "title": text.nfc(title),
                        "start": start, "end": end, "is_current": is_current,
                        "summary": None,
                    }, f"{line.strip()} / {nxt.strip()}",
                        "regex:experience_block_v1",
                        locator=span(start_off, nxt_end))
                    consumed.add(idx + 1)
