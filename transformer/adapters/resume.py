"""Resume adapter (M7 stretch): PDF/DOCX text -> the shared free-text scanner.

The only new machinery is text extraction; every rule is notes_txt's, at
resume trust (0.70). Dependencies are optional (pip install .[resume]) and
imported lazily — without them a resume file is reported `skipped`, never a
crash. A scanned image-only PDF yields no text and is reported the same way.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import text
from .base import SourceResult
from .notes_txt import scan_into

SOURCE_TYPE = "resume"

# First-line-is-the-name heuristic: 2-4 words, each starting uppercase, no
# digits/@/|. Word bodies allow unicode letters so "Carlos Núñez" qualifies;
# headings like "Curriculum Vitae" match the shape and are excluded by name.
_NAME_LINE_RE = re.compile(
    r"^(?:[A-Z][^\s\d@|,;:]{1,24})(?:\s+[A-Z][^\s\d@|,;:]{1,24}){1,3}$"
)
_NOT_NAMES = {"curriculum vitae", "resume", "cv", "personal profile"}


def detect(path: Path) -> bool:
    return path.suffix.lower() in {".pdf", ".docx"}


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    if path.suffix.lower() == ".docx":
        body = _docx_text(path)
    else:
        body = _pdf_text(path)
    if not body.strip():
        raise ValueError("no extractable text (scanned/image-only file?)")

    rec = SourceRecord(record_id=f"{res.source_id}#file",
                       source_id=res.source_id, source_type=SOURCE_TYPE)

    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if _NAME_LINE_RE.match(first) and text.fold(first) not in _NOT_NAMES:
        rec.evidence.append(Evidence(
            field_path="full_name", value=text.nfc(first), raw_value=first,
            source_id=res.source_id, source_type=SOURCE_TYPE,
            method="regex:resume_title_name_v1", record_id=rec.record_id,
            order_index=0))

    scan_into(rec, body, ctx)
    res.records_read = 1
    if rec.evidence:
        res.records.append(rec)


def _docx_text(path: Path) -> str:
    import docx  # lazy: optional dependency

    return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)


def _pdf_text(path: Path) -> str:
    import pdfplumber  # lazy: optional dependency

    with pdfplumber.open(str(path)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
