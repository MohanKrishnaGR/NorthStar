"""Record a GitHub profile for the pipeline (the ADR-002/017 recording boundary).

The pipeline never touches the network. THIS tool does — exactly once, at
recording time — and writes the payload the github_json adapter replays
forever, keeping runs offline-deterministic:

    python tools/fetch_github.py https://github.com/octocat --out samples
    python -m transformer run --input samples ...

Uses the public REST API; set GITHUB_TOKEN to raise the rate limit.
Languages are aggregated as primary-language counts across non-fork public
repos — a deliberate proxy (per-repo byte counts would cost one API call per
repository for data the adapter already discounts to derived reliability).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

_LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_API = "https://api.github.com"


def parse_login(url_or_login: str) -> str:
    """Accepts a profile URL or a bare login; returns the validated login."""
    s = url_or_login.strip().rstrip("/")
    if "github.com" in s:
        s = s.split("github.com/", 1)[1]
        s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not _LOGIN_RE.match(s):
        raise ValueError(f"not a GitHub login or profile URL: {url_or_login!r}")
    return s


def shape_payload(user: dict, repos: list[dict] | None) -> dict:
    """Exactly the shape transformer/adapters/github_json.py replays."""
    languages: dict[str, int] = {}
    for repo in repos or []:
        lang = repo.get("language")
        if lang and not repo.get("fork"):
            languages[lang] = languages.get(lang, 0) + 1
    payload = {k: user.get(k) for k in
               ("login", "name", "bio", "html_url", "blog", "email", "location")}
    payload["languages"] = dict(sorted(languages.items()))
    return payload


def _api_fetch(path: str):
    req = urllib.request.Request(_API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "candidate-transformer-recorder",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def record(url_or_login: str, out_dir: str | Path, fetch=_api_fetch) -> Path:
    login = parse_login(url_or_login)
    user = fetch(f"/users/{login}")
    repos = fetch(f"/users/{login}/repos?per_page=100&sort=full_name")
    payload = shape_payload(user, repos)
    out = Path(out_dir) / f"github_{login}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile", help="GitHub profile URL or bare login")
    ap.add_argument("--out", default="samples",
                    help="directory for the recorded payload (default: samples)")
    args = ap.parse_args()
    out = record(args.profile, args.out)
    print(f"recorded -> {out}  (the {out.name.split('_', 1)[1].rsplit('.', 1)[0]}"
          f" adapter will replay it deterministically)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
