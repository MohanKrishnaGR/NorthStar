"""Adapter contract and fault boundary (DESIGN.md ADR-013).

An adapter turns one source file into SourceRecords full of Evidence atoms.
Any exception inside extract() marks the source `skipped` (row-level failures
mark it `partial`); the run always continues with whatever evidence exists.
`--strict` re-raises instead — a development aid, never a documented run mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_ENCODINGS = ("utf-8-sig", "cp1252")  # deterministic fallback order


@dataclass
class SourceResult:
    source_id: str
    source_type: str
    status: str = "ok"  # ok | partial | skipped
    records: list = field(default_factory=list)  # list[SourceRecord]
    records_read: int = 0
    errors: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    unparseable: list = field(default_factory=list)  # {field, raw_value, reason}

    def note_unparseable(self, fieldname: str, raw: object, reason: str) -> None:
        self.unparseable.append(
            {"field": fieldname, "raw_value": str(raw), "reason": reason}
        )


def read_text(path: Path) -> str:
    blob = path.read_bytes()
    # BOM sniff first (DEFECTS_PLAN D2): a UTF-16 BOM is two unambiguous
    # bytes — decode properly instead of letting the cp1252 fallback "read"
    # NUL-riddled junk. No content guessing beyond the BOM (that trap stays
    # closed); the chain stays deterministic.
    if blob.startswith(b"\xff\xfe") or blob.startswith(b"\xfe\xff"):
        return blob.decode("utf-16")
    last_err: Exception | None = None
    for enc in _ENCODINGS:
        try:
            return blob.decode(enc)
        except UnicodeDecodeError as e:  # pragma: no cover - cp1252 rarely fails
            last_err = e
    raise last_err  # type: ignore[misc]


def run_adapter(adapter, path: Path, ctx: dict) -> SourceResult:
    res = SourceResult(source_id=path.name, source_type=adapter.SOURCE_TYPE)
    try:
        adapter.extract(path, res, ctx)
    except Exception as e:
        if ctx.get("strict"):
            raise
        res.status = "skipped"
        res.records = []
        res.errors.append(f"{type(e).__name__}: {e}")
    if res.status != "skipped" and res.errors:
        res.status = "partial"
    return res
