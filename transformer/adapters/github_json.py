"""GitHub recorded-response adapter (ADR-017).

Reads a cached REST payload (`github_<login>.json` — the naming convention is
the detection rule; a fetcher that recorded the response names the file).
Live fetching stays descoped: this adapter never touches the network, so runs
stay offline-deterministic.

Two honesty rules baked in:
- `login` is never promoted to full_name; only an explicit `name` counts,
  and GitHub `name` is often null.
- repo languages become skills at *derived* reliability — a repo containing
  YAML does not make someone a YAML expert, and these must never outvote a
  resume's explicit skills.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Evidence, SourceRecord
from ..normalize import country as country_mod
from ..normalize import emails, skills, text, urls
from .base import SourceResult, read_text

SOURCE_TYPE = "github_json"


def detect(path: Path) -> bool:
    return path.suffix.lower() == ".json" and path.name.lower().startswith("github_")


def extract(path: Path, res: SourceResult, ctx: dict) -> None:
    doc = json.loads(read_text(path))
    if not isinstance(doc, dict):
        raise ValueError("github payload is not an object")
    rid = f"{res.source_id}#user"
    rec = SourceRecord(record_id=rid, source_id=res.source_id,
                       source_type=SOURCE_TYPE)

    def add(field_path, value, raw, method="direct_field", key=None):
        loc = {"kind": "path", "path": key} if key else None
        rec.evidence.append(Evidence(
            field_path=field_path, value=value, raw_value=raw,
            source_id=res.source_id, source_type=SOURCE_TYPE,
            method=method, record_id=rid, order_index=len(rec.evidence),
            locator=loc))

    name = doc.get("name")
    if name and not text.is_null_marker(name):
        add("full_name", text.nfc(str(name)), name, key="name")
    if doc.get("bio"):
        add("headline", text.nfc(str(doc["bio"])), doc["bio"], key="bio")

    login = doc.get("login")
    gh_url = doc.get("html_url") or (f"https://github.com/{login}" if login else None)
    if gh_url:
        add("links.github", urls.classify(str(gh_url))[1], gh_url, key="html_url")
    if doc.get("blog"):
        bucket, cleaned = urls.classify(str(doc["blog"]))
        add(f"links.{bucket}", cleaned, doc["blog"], key="blog")

    if doc.get("email"):
        norm = emails.normalize(doc["email"])
        if norm:
            add("emails", norm, doc["email"], key="email")

    loc = doc.get("location")
    if loc and not text.is_null_marker(loc):
        parts = [p.strip() for p in str(loc).split(",")]
        iso = country_mod.to_iso2(parts[-1], codes=False) if len(parts) > 1 else None
        add("location", {"city": text.nfc(parts[0]), "region": None,
                         "country": iso}, loc, key="location")

    langs = doc.get("languages") or {}
    if isinstance(langs, dict):
        langs = list(langs)
    for lang in langs:
        if text.is_null_marker(lang):
            continue
        name_, canonical = skills.canonicalize(lang)
        add("skills", {"name": name_, "canonical": canonical}, lang,
            method="derived:github_languages_v1", key="languages")

    res.records_read = 1
    if rec.evidence:
        res.records.append(rec)
