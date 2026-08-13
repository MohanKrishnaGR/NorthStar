"""Precision-preserving date parsing (ADR-008).

Internal form is a (year, month|None) tuple. Rendering emits "YYYY-MM" when
the month is known and "YYYY" when it is not — coercing "2019" to "2019-01"
would be textbook wrong-but-confident. Ambiguous numeric dates (03/04/2021,
locale unknown) keep the year and drop the month.
"""
from __future__ import annotations

import re

PartialDate = tuple[int, int | None]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Alternation order matters: longer/less ambiguous shapes first.
TOKEN_RE = re.compile(
    r"""(?ix)
    (?P<present>\bpresent\b|\bcurrent\b|\bongoing\b|\bnow\b|\btill\ date\b)
  | (?P<ymd>(?P<ymd_y>\d{4})[-/](?P<ymd_m>\d{1,2})[-/](?P<ymd_d>\d{1,2}))
  | (?P<dmy>(?P<dmy_a>\d{1,2})[-/](?P<dmy_b>\d{1,2})[-/](?P<dmy_y>\d{4}))
  | (?P<mname>(?P<mn>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may
      |jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?
      |nov(?:ember)?|dec(?:ember)?)\.?,?\s+(?P<mn_y>\d{4}))
  | (?P<ym>(?P<ym_y>\d{4})[-/](?P<ym_m>\d{1,2})(?!\d))
  | (?P<my>(?P<my_m>\d{1,2})[-/](?P<my_y>\d{4}))
  | (?P<y>\b(?:19|20)\d{2}\b)
    """
)

_RANGE_GAP = 12  # max chars between two tokens to read them as a range


def _from_match(m: re.Match) -> PartialDate | None | str:
    """PartialDate, the string 'present', or None if the token is not a date."""
    if m.group("present"):
        return "present"
    if m.group("ymd"):
        y, mo = int(m.group("ymd_y")), int(m.group("ymd_m"))
        return (y, mo) if 1 <= mo <= 12 else (y, None)
    if m.group("dmy"):
        # dd/mm vs mm/dd: resolvable only when one part exceeds 12, or both
        # are equal. Otherwise the month is honestly unknown (ADR-008).
        a, b, y = int(m.group("dmy_a")), int(m.group("dmy_b")), int(m.group("dmy_y"))
        if a > 12 and b <= 12:
            return (y, b)
        if b > 12 and a <= 12:
            return (y, a)
        if a == b and a <= 12:
            return (y, a)
        return (y, None)
    if m.group("mname"):
        return (int(m.group("mn_y")), _MONTHS[m.group("mn").lower()[:3]])
    if m.group("ym"):
        y, mo = int(m.group("ym_y")), int(m.group("ym_m"))
        return (y, mo) if 1 <= mo <= 12 else (y, None)
    if m.group("my"):
        y, mo = int(m.group("my_y")), int(m.group("my_m"))
        return (y, mo) if 1 <= mo <= 12 else (y, None)
    if m.group("y"):
        return (int(m.group("y")), None)
    return None


def parse(s: object) -> PartialDate | None:
    """First date token in the string, or None."""
    for m in TOKEN_RE.finditer(str(s)):
        got = _from_match(m)
        if isinstance(got, tuple):
            return got
    return None


def parse_range(s: str):
    """(start, end, is_current) from free text, or None.

    Handles "Jan 2020 - Present", "2019–2021", "since 2020". Tokens further
    apart than a small gap are two dates in prose, not a range.
    """
    tokens = []
    for m in TOKEN_RE.finditer(str(s)):
        got = _from_match(m)
        if got is not None:
            tokens.append((m.start(), m.end(), got))
    if not tokens:
        return None
    first = tokens[0]
    if isinstance(first[2], tuple) and re.search(
        r"(?i)\bsince\b", s[: first[0]]
    ):
        return (first[2], None, True)
    if len(tokens) >= 2 and isinstance(first[2], tuple):
        nxt = tokens[1]
        if nxt[0] - first[1] <= _RANGE_GAP:
            if nxt[2] == "present":
                return (first[2], None, True)
            if isinstance(nxt[2], tuple):
                return (first[2], nxt[2], False)
    return None


def render(d: PartialDate | None) -> str | None:
    if d is None:
        return None
    y, mo = d
    return f"{y:04d}-{mo:02d}" if mo else f"{y:04d}"


def month_index(d: PartialDate, bound: str) -> int:
    """Months-since-year-0 index. Year-only dates span their whole year:
    'start' snaps to January, 'end' to December (documented upper bound)."""
    y, mo = d
    if mo is None:
        mo = 1 if bound == "start" else 12
    return y * 12 + (mo - 1)


def overlaps(a_start, a_end, b_start, b_end, as_of: PartialDate) -> bool:
    """Interval overlap; None end means open-ended, closed at as_of."""
    a0 = month_index(a_start, "start")
    a1 = month_index(a_end, "end") if a_end else month_index(as_of, "end")
    b0 = month_index(b_start, "start")
    b1 = month_index(b_end, "end") if b_end else month_index(as_of, "end")
    return a0 <= b1 and b0 <= a1
