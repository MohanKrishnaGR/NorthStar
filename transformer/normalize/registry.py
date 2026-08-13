"""Named normalizers for the projection layer (ADR-012).

Every normalizer is idempotent — projection routinely re-normalizes values
that are already canonical. NormalizeError means "value exists but will not
normalize": the projector treats that as missing and reports it, never crashes.
"""
from __future__ import annotations

from . import country, dates, phones, skills, text


class NormalizeError(ValueError):
    pass


def _e164(v: object) -> str:
    got = phones.to_e164(v)
    if got is None:
        raise NormalizeError(f"not E.164-normalizable without region context: {v!r}")
    return got


def _canonical(v: object) -> str:
    name, _ = skills.canonicalize(v)
    if not name:
        raise NormalizeError(f"empty after skill folding: {v!r}")
    return name


def _yyyymm(v: object) -> str:
    d = dates.parse(v)
    if d is None:
        raise NormalizeError(f"no parseable date in: {v!r}")
    return dates.render(d)


def _iso3166(v: object) -> str:
    got = country.to_iso2(v)
    if got is None:
        raise NormalizeError(f"unknown country: {v!r}")
    return got


def _lower(v: object) -> str:
    return text.fold(str(v))


_FNS = {
    "E164": _e164,
    "canonical": _canonical,
    "YYYY-MM": _yyyymm,
    "ISO3166": _iso3166,
    "lower": _lower,
}

# Which declared config types each normalizer may attach to — checked at
# config load (ADR-011), so "E164 on full_name" fails before any candidate runs.
APPLICABLE_TYPES = {
    "E164": {"string", "string[]"},
    "canonical": {"string", "string[]"},
    "YYYY-MM": {"string"},
    "ISO3166": {"string"},
    "lower": {"string", "string[]"},
}


def known(name: str) -> bool:
    return name in _FNS


def apply(name: str, value: object) -> object:
    fn = _FNS[name]
    if isinstance(value, list):
        return [fn(v) for v in value]
    return fn(value)
