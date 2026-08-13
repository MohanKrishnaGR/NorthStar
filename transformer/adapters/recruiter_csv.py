"""Recruiter CSV adapter: one candidate per row.

Columns per the problem statement: name, email, phone, current_company,
title. current_company/title become a dateless experience entry with
is_current=True — "current" is what the column name asserts; dates stay
honestly null (DESIGN.md ADR-002 note).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import emails, phones, text
from .base import SourceResult, read_text

SOURCE_TYPE = "recruiter_csv"

_KNOWN_HEADERS = {"name", "email", "phone", "current_company", "title"}


def detect(path: Path) -> bool:
    return path.suffix.lower() == ".csv"


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    body = read_text(path)
    reader = csv.DictReader(io.StringIO(body))
    headers = {text.fold(h): h for h in (reader.fieldnames or [])}
    if not (_KNOWN_HEADERS & set(headers)):
        raise ValueError(f"unrecognized CSV headers: {reader.fieldnames!r}")

    def cell(row: dict, name: str) -> str:
        raw = row.get(headers.get(name, ""), "") or ""
        return text.nfc(raw)

    for i, row in enumerate(reader, start=1):
        res.records_read += 1
        rid = f"{res.source_id}#row={i}"
        if None in row and row[None]:
            # More values than headers: a shifted row. Contain, don't trust.
            res.errors.append(f"{rid}: column-shifted row skipped")
            continue
        rec = SourceRecord(record_id=rid, source_id=res.source_id,
                           source_type=SOURCE_TYPE)
        order = 0

        def add(field_path, value, raw, method="direct_field", normalized=True):
            nonlocal order
            rec.evidence.append(Evidence(
                field_path=field_path, value=value, raw_value=raw,
                source_id=res.source_id, source_type=SOURCE_TYPE,
                method=method, record_id=rid, order_index=order,
                normalized=normalized))
            order += 1

        if cell(row, "name"):
            add("full_name", cell(row, "name"), row.get(headers.get("name")))

        for raw_email in _split_multi(cell(row, "email")):
            norm = emails.normalize(raw_email)
            if norm:
                add("emails", norm, raw_email)
            elif raw_email:
                res.note_unparseable("emails", raw_email, "not_an_email")

        for raw_phone in phones.split_cell(cell(row, "phone")):
            e164 = phones.to_e164(raw_phone, ctx.get("default_region"))
            if e164:
                add("phones", e164, raw_phone)
            else:
                # Kept raw for post-merge pass 2 (ADR-009); never a match key.
                add("phones_raw", raw_phone, raw_phone, normalized=False)

        company, title = cell(row, "current_company"), cell(row, "title")
        if company or title:
            add("experience", {
                "company": company or None, "title": title or None,
                "start": None, "end": None, "is_current": True,
                "summary": None,
            }, f"{company}|{title}")

        if rec.evidence:
            res.records.append(rec)


def _split_multi(raw: str) -> list[str]:
    out = []
    for part in raw.replace(";", " ").replace(",", " ").split():
        out.append(part)
    return out or ([raw] if raw else [])
