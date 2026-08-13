"""Country name -> ISO-3166 alpha-2 via a curated alias table.

Unknown strings stay None — never guessed (DESIGN.md north star).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import text

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "country_aliases.json"


@lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    with open(_DATA, encoding="utf-8") as f:
        return json.load(f)


# 2-letter aliases safe to honor even inside "City, XX" strings. Others
# ("CA", "IN", "DE"...) collide with US states and English words — honoring
# them there would turn "San Francisco, CA" into Canada: wrong-but-confident.
_SAFE_SHORT = {"us", "uk"}


def to_iso2(raw: object, codes: bool = True) -> str | None:
    """ISO-3166 alpha-2 or None. codes=False is for free-text location
    strings, where ambiguous 2-letter aliases must not match."""
    key = text.fold(str(raw)).strip(" .")
    if not codes and len(key) <= 2 and key not in _SAFE_SHORT:
        return None
    return _aliases().get(key)
