"""O1: reference-data governance (OPS_PLAN §2.1).

Scoring tables and alias dictionaries are versioned, checksummed inputs to
every confidence number in the output. This suite enforces the ritual:
change the content -> bump the version -> rerun the checksum tool -> the
gold diff gets reviewed in the same change.
"""
import hashlib
import json
from pathlib import Path

from transformer import __version__
from transformer.constants import (
    CORE_FIELD_WEIGHTS,
    METHOD_RELIABILITY,
    SCORING_VERSION,
    SOURCE_TRUST,
)

DATA = Path(__file__).resolve().parent.parent / "data"


def _checksums():
    return json.loads((DATA / "CHECKSUMS.json").read_text(encoding="utf-8"))


def test_reference_files_match_recorded_checksums():
    recorded = _checksums()
    for name, rec in recorded.items():
        blob = (DATA / name).read_bytes()
        actual = hashlib.sha256(blob).hexdigest()
        assert actual == rec["sha256"], (
            f"{name} changed without the ritual: bump its version field and "
            f"run tools/update_reference_checksums.py (then regenerate and "
            f"review gold)"
        )
        assert json.loads(blob)["version"] == rec["version"]


def test_scoring_loads_and_is_complete():
    assert SCORING_VERSION
    assert set(SOURCE_TRUST) >= {"ats_json", "recruiter_csv", "notes_txt",
                                 "resume", "github_json", "linkedin_json",
                                 "derived"}
    assert set(METHOD_RELIABILITY) >= {"direct_field", "regex", "dict",
                                       "derived", "phones_pass2"}
    assert all(0 < v <= 1 for v in SOURCE_TRUST.values())
    assert all(0 < v <= 1 for v in METHOD_RELIABILITY.values())
    assert all(w > 0 for w in CORE_FIELD_WEIGHTS.values())


def test_run_report_carries_the_full_pin():
    from transformer.pipeline import run_pipeline
    from transformer.projection.config import load

    root = Path(__file__).resolve().parent.parent
    files = [p for p in (root / "samples").iterdir() if p.is_file()]
    result = run_pipeline(files, load(root / "configs" / "default.json"),
                          as_of=(2026, 8))
    run = result.report["run"]
    assert run["engine_version"] == __version__
    assert run["scoring_version"] == SCORING_VERSION
    assert set(run["dictionary_versions"]) == {"skill_aliases",
                                               "country_aliases"}
