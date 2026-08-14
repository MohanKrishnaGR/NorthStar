"""The GitHub recording tool — tested with an injected fetcher, never live
network (CI stays offline-deterministic; the tool alone owns the boundary)."""
import json
import sys
from pathlib import Path

import pytest

from transformer.adapters import detect_adapter, github_json
from transformer.adapters.base import run_adapter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from fetch_github import parse_login, record, shape_payload  # noqa: E402


@pytest.mark.parametrize("given,want", [
    ("https://github.com/octocat", "octocat"),
    ("https://www.github.com/octocat/", "octocat"),
    ("github.com/octocat?tab=repositories", "octocat"),
    ("octocat", "octocat"),
])
def test_parse_login(given, want):
    assert parse_login(given) == want


def test_parse_login_rejects_junk():
    with pytest.raises(ValueError):
        parse_login("https://gitlab.com/someone")
    with pytest.raises(ValueError):
        parse_login("not a login!")


def test_shape_payload_counts_primary_languages_skipping_forks():
    user = {"login": "octo", "name": "Octo Cat", "bio": None,
            "html_url": "https://github.com/octo", "blog": "",
            "email": None, "location": "The Internet",
            "followers": 999}  # extra keys never leak into the recording
    repos = [
        {"language": "Python", "fork": False},
        {"language": "Python", "fork": False},
        {"language": "Go", "fork": False},
        {"language": "Rust", "fork": True},   # forks don't vouch for skills
        {"language": None, "fork": False},
    ]
    got = shape_payload(user, repos)
    assert got["languages"] == {"Go": 1, "Python": 2}
    assert "followers" not in got and got["login"] == "octo"


def test_recording_roundtrips_through_the_adapter(tmp_path):
    def fake_fetch(path):
        if path.startswith("/users/wale/repos"):
            return [{"language": "Python", "fork": False}]
        return {"login": "wale", "name": "Wale Adeyemi", "bio": "platforms",
                "html_url": "https://github.com/wale", "blog": None,
                "email": None, "location": None}

    out = record("https://github.com/wale", tmp_path, fetch=fake_fetch)
    assert out.name == "github_wale.json"
    assert detect_adapter(out) is github_json  # naming convention holds
    res = run_adapter(github_json, out, {"default_region": None})
    fields = {e.field_path for e in res.records[0].evidence}
    assert {"full_name", "links.github", "skills"} <= fields
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["languages"] == {"Python": 1}
