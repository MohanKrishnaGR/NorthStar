"""URL extraction and link classification (links.linkedin / github / other)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

URL_RE = re.compile(
    r"""(?ix)
    \bhttps?://[^\s<>"')\]]+
  | \b(?:www\.)?(?:linkedin\.com|github\.com)/[^\s<>"')\]]+
    """
)


def classify(url: str) -> tuple[str, str]:
    """(bucket, cleaned_url) where bucket is linkedin|github|other."""
    u = url.strip().rstrip(".,;:")
    if not u.lower().startswith("http"):
        u = "https://" + u
    host = urlparse(u).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if host.endswith("linkedin.com"):
        return "linkedin", u
    if host.endswith("github.com"):
        return "github", u
    return "other", u


def find_all(body: str) -> list[str]:
    return [m.group(0) for m in URL_RE.finditer(body)]


def match_key(url: str) -> str:
    """Identity-matching form of a profile URL (ADR-017): scheme, www, query
    strings (tracking params), fragments, and trailing slashes ignored —
    github.com/alice?tab=repos and https://www.github.com/alice/ are the same
    person. Matching only; output keeps the original URL."""
    _, cleaned = classify(url)
    p = urlparse(cleaned.lower())
    host = p.netloc[4:] if p.netloc.startswith("www.") else p.netloc
    return f"{host}{p.path}".rstrip("/")
