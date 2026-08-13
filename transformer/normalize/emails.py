"""Email normalization and identity-matching keys (ADR-005)."""
from __future__ import annotations

import re

from . import text

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def normalize(raw: object) -> str | None:
    """Canonical output form: NFC, trimmed, lowercased. None if not an email."""
    s = text.nfc(str(raw)).strip(" .,;<>()[]\"'")
    return s.lower() if EMAIL_RE.fullmatch(s) else None


def match_key(email: str) -> str:
    """Identity-matching key only — output always keeps the original address.

    Plus-tags stripped everywhere; dots ignored on gmail domains only (they are
    address-equivalent there and nowhere else). googlemail folds into gmail.
    """
    local, _, domain = email.lower().partition("@")
    local = local.split("+", 1)[0]
    if domain in GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def find_all(body: str) -> list[str]:
    """All email-shaped substrings in free text, in document order."""
    return [m.group(0) for m in EMAIL_RE.finditer(body)]
