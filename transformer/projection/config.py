"""Config loading is a compile step (ADR-011/012, PLAN §3.6).

All problems are collected and reported together — a config author fixes one
list, not one error per run. Any error here means exit code 2 upstream,
before a single candidate is processed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..models import TYPE_VOCABULARY
from ..normalize import registry
from . import paths

_ON_MISSING = {"null", "omit", "error"}

# Semantic domains: which canonical top-level field each normalizer may read
# from. Type compatibility alone would let "E164 on full_name" through (both
# are strings) — exactly the load-time error ADR-011 promises to catch.
# None = any field (the normalizer is content-generic).
_NORMALIZER_DOMAINS: dict[str, set[str] | None] = {
    "E164": {"phones"},
    "ISO3166": {"location"},
    "canonical": {"skills"},
    "YYYY-MM": {"experience", "education"},
    "lower": None,
}


class ConfigError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class FieldSpec:
    path: str
    from_path: str
    segs: list
    out_parts: list[str]
    type: str
    required: bool = False
    normalize: str | None = None


@dataclass
class Config:
    fields: list[FieldSpec] = field(default_factory=list)
    include_provenance: bool = False
    include_confidence: bool = False
    on_missing: str = "null"
    raw: dict = field(default_factory=dict)


def load(source: str | Path | dict) -> Config:
    doc = source if isinstance(source, dict) else json.loads(
        Path(source).read_text(encoding="utf-8")
    )
    errors: list[str] = []
    cfg = Config(
        include_provenance=bool(doc.get("include_provenance", False)),
        include_confidence=bool(doc.get("include_confidence", False)),
        on_missing=doc.get("on_missing", "null"),
        raw=doc,
    )
    if cfg.on_missing not in _ON_MISSING:
        errors.append(f"on_missing must be one of {sorted(_ON_MISSING)}")

    entries = doc.get("fields")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(errors + ["config needs a non-empty 'fields' list"])

    seen_paths: list[tuple[str, ...]] = []
    for i, entry in enumerate(entries):
        where = f"fields[{i}]"
        if not isinstance(entry, dict) or "path" not in entry:
            errors.append(f"{where}: each field needs a 'path'")
            continue
        out_path = entry["path"]
        try:
            out_segs = paths.parse(out_path)
        except paths.PathError as e:
            errors.append(f"{where}: {e}")
            continue
        if any(idx is not None for _, idx in out_segs):
            errors.append(f"{where}: output path {out_path!r} may not use []/[i]")
            continue
        parts = tuple(name for name, _ in out_segs)
        for prev in seen_paths:
            if parts == prev or parts[: len(prev)] == prev or prev[: len(parts)] == parts:
                errors.append(f"{where}: output path {out_path!r} collides with a prior path")
        seen_paths.append(parts)

        from_path = entry.get("from", out_path)  # `from` defaults to `path`
        declared = entry.get("type")
        if declared not in TYPE_VOCABULARY:
            errors.append(f"{where}: type must be one of {sorted(TYPE_VOCABULARY)}")
            continue
        try:
            segs = paths.parse(from_path)
            resolved = paths.canonical_type(from_path)
        except paths.PathError as e:
            errors.append(f"{where}: {e}")
            continue
        if resolved != declared:
            errors.append(
                f"{where}: declared type {declared!r} but {from_path!r} "
                f"resolves to {resolved!r}"
            )
        norm = entry.get("normalize")
        if norm is not None:
            domain = _NORMALIZER_DOMAINS.get(norm)
            if not registry.known(norm):
                errors.append(f"{where}: unknown normalize {norm!r}")
            elif declared not in registry.APPLICABLE_TYPES[norm]:
                errors.append(
                    f"{where}: normalize {norm!r} not applicable to type {declared!r}"
                )
            elif domain is not None and paths.top_field(from_path) not in domain:
                errors.append(
                    f"{where}: normalize {norm!r} reads {from_path!r}, but only "
                    f"applies to {sorted(domain)}"
                )
        cfg.fields.append(FieldSpec(
            path=out_path, from_path=from_path, segs=segs,
            out_parts=list(parts), type=declared,
            required=bool(entry.get("required", False)), normalize=norm,
        ))

    if errors:
        raise ConfigError(errors)
    return cfg
