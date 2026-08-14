"""The projector: canonical profile x config -> output record (ADR-012).

Fixed per-field order: resolve `from` -> normalize -> on_missing -> type-check.
Empty means null/absent — an empty array is a present value. A normalize
failure is treated as missing and reported, never a crash. A record with
validation errors is excluded by the caller; the batch always continues.
"""
from __future__ import annotations

from ..normalize.registry import NormalizeError, apply as apply_normalizer
from .config import Config
from .paths import MISSING, resolve, top_field

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "string[]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "number[]": lambda v: isinstance(v, list)
    and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v),
    "object[]": lambda v: isinstance(v, list) and all(isinstance(x, dict) for x in v),
}


def project(profile: dict, cfg: Config):
    """-> (output | None, errors, notes). None output means the record failed
    validation (a required/on_missing=error field was missing)."""
    out: dict = {}
    errors: list[dict] = []
    notes: list[dict] = []

    for f in cfg.fields:
        val = resolve(profile, f.segs)
        if val is not MISSING and f.normalize:
            try:
                val = apply_normalizer(f.normalize, val)
            except NormalizeError as e:
                notes.append({
                    "field": f.path, "raw_value": _short(val), "reason": str(e),
                })
                val = MISSING  # normalize failure == missing (ADR-012)
        if val is MISSING:
            if f.required:
                errors.append({"field": f.path, "problem": "required_missing"})
            elif cfg.on_missing == "null":
                _set(out, f.out_parts, None)
            elif cfg.on_missing == "error":
                errors.append({"field": f.path, "problem": "missing"})
            # omit: leave the key out entirely
            continue
        if not _TYPE_CHECKS[f.type](val):
            errors.append({
                "field": f.path,
                "problem": f"expected {f.type}, got {type(val).__name__}",
            })
            continue
        _set(out, f.out_parts, val)

    if cfg.include_provenance:
        out["provenance"] = _rekeyed_provenance(profile, cfg)
    if cfg.include_confidence:
        out["confidence"] = {
            "overall": profile.get("overall_confidence", 0.0),
            "fields": {
                f.path: profile.get("field_confidence", {}).get(top_field(f.from_path))
                for f in cfg.fields
                if top_field(f.from_path) in profile.get("field_confidence", {})
            },
        }
    return (None if errors else out), errors, notes


def _rekeyed_provenance(profile: dict, cfg: Config) -> list[dict]:
    """Provenance re-keyed to *output* field names (ADR-012): entries the
    consumer cannot see are dropped, prefixes are renamed."""
    entries = []
    for p in profile.get("provenance", []):
        for f in cfg.fields:
            src = f.from_path
            renamed = None
            if p["field"] == src:
                renamed = f.path
            elif p["field"].startswith(src + "[") or p["field"].startswith(src + "."):
                renamed = f.path + p["field"][len(src):]
            if renamed is not None:
                entries.append({**p, "field": renamed})
    entries.sort(key=lambda p: (p["field"], p["source"]))
    seen = set()
    out = []
    for p in entries:
        k = (p["field"], p["source"], p["method"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _set(out: dict, parts: list[str], value) -> None:
    cur = out
    for name in parts[:-1]:
        cur = cur.setdefault(name, {})
    cur[parts[-1]] = value


def _short(v) -> str:
    s = str(v)
    return s if len(s) <= 80 else s[:77] + "..."
