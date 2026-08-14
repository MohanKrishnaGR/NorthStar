"""T2 hostile corpus: file-level garbage degrades to *named* report entries,
never crashes, and never invents profiles (GOLDEN_DATASET §5, tier 2)."""
from pathlib import Path

import pytest

from transformer.pipeline import run_pipeline
from transformer.projection.config import load

ROOT = Path(__file__).resolve().parent.parent
T2 = ROOT / "goldens" / "t2"


@pytest.fixture(scope="module")
def t2_run():
    files = [p for p in T2.iterdir() if p.is_file()]
    return run_pipeline(files, load(ROOT / "configs" / "default.json"),
                        as_of=(2026, 8))


def status_of(run, source_id):
    got = [s for s in run.report["sources"] if s["source_id"] == source_id]
    assert got, f"{source_id} missing from report"
    return got[0]


def test_garbage_sources_skipped_with_errors(t2_run):
    for name in ("truncated.json", "page.json", "data.csv", "empty.json",
                 "fake.pdf"):
        src = status_of(t2_run, name)
        assert src["status"] == "skipped", name
        assert src["errors"], f"{name} skipped silently — must carry a reason"


def test_utf16_bom_decodes_and_extracts(t2_run):
    # DEFECTS_PLAN D2: the right closure for an "honest miss" is to stop
    # missing — the BOM is two unambiguous bytes, so decode, don't grade "ok
    # with zero evidence".
    src = status_of(t2_run, "utf16.txt")
    assert src["status"] == "ok" and src["evidence_emitted"] > 0
    ute = [p for p in t2_run.profiles if p["full_name"] == "Ute Sechzehn"]
    assert ute and ute[0]["emails"] == ["ute@example.com"]


def test_unrecognized_file_is_named(t2_run):
    assert t2_run.report["unrecognized_files"] == ["noext"]


def test_bom_csv_still_yields_its_profile(t2_run):
    assert status_of(t2_run, "bom.csv")["status"] == "ok"
    assert any(p["full_name"] == "Bo Marker" for p in t2_run.profiles)


def test_hostile_corpus_never_invents_candidates(t2_run):
    # Exactly the two healthy inputs produce people; garbage conjures none.
    assert sorted(p["full_name"] for p in t2_run.profiles) == [
        "Bo Marker", "Ute Sechzehn"]
