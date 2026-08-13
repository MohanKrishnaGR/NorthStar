"""The four-construct path DSL (ADR-011): name, a.b, a[0], a[].b.

Deliberately not JSONPath: the grammar is closed, so it can be exhaustively
tested and every `from` path validated against the canonical schema at config
load — a typo fails before any candidate is processed.
"""
from __future__ import annotations

import re

from ..models import CANONICAL_TYPES

_SEG_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+|)\])?$")

MISSING = object()


class PathError(ValueError):
    pass


def parse(path: str) -> list[tuple[str, object]]:
    """Segments: (name, None) | (name, int) | (name, "[]"). Max one map."""
    segs: list[tuple[str, object]] = []
    maps = 0
    for part in str(path).split("."):
        m = _SEG_RE.match(part)
        if not m:
            raise PathError(f"bad path segment {part!r} in {path!r}")
        name, idx = m.group(1), m.group(2)
        if idx is None:
            segs.append((name, None))
        elif idx == "":
            segs.append((name, "[]"))
            maps += 1
        else:
            segs.append((name, int(idx)))
    if maps > 1:
        raise PathError(f"at most one [] per path: {path!r}")
    return segs


def resolve(record: object, segs: list) -> object:
    """Value at path, or MISSING. [] maps over the array (skipping missing
    elements); an empty array resolves to [] — present, not missing."""
    cur = record
    for i, (name, idx) in enumerate(segs):
        if not isinstance(cur, dict) or cur.get(name) is None:
            return MISSING
        cur = cur[name]
        if idx is None:
            continue
        if not isinstance(cur, list):
            return MISSING
        if idx == "[]":
            rest = segs[i + 1:]
            out = []
            for el in cur:
                v = resolve(el, rest) if rest else el
                if v is not MISSING and v is not None:
                    out.append(v)
            return out
        if idx >= len(cur):
            return MISSING
        cur = cur[idx]
    return MISSING if cur is None else cur


def canonical_type(path: str) -> str:
    """Type a `from` path resolves to, per models.CANONICAL_TYPES."""
    segs = parse(path)
    key_parts = []
    mapped = False
    for name, idx in segs:
        key_parts.append(name + ("[]" if idx is not None else ""))
        if idx == "[]":
            mapped = True
    key = ".".join(key_parts)
    t = CANONICAL_TYPES.get(key)
    if t is None and key.endswith("[]") and key[:-2] in CANONICAL_TYPES:
        base = CANONICAL_TYPES[key[:-2]]
        if base.endswith("[]"):
            t = base[:-2]
    if t is None:
        raise PathError(f"unknown canonical path: {path!r}")
    return t + "[]" if mapped else t


def top_field(path: str) -> str:
    """Top-level canonical field a path reads from ('emails[0]' -> 'emails')."""
    return parse(path)[0][0]
