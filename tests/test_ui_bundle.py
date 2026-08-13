"""U1: the UI bundle — locators, traces, and gold-safety of collect_ui."""
from pathlib import Path

import pytest

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
T1 = ROOT / "goldens" / "t1"

pytest.importorskip("docx", reason="T1 includes docx resumes")


@pytest.fixture(scope="module")
def ui_run():
    files = [p for p in T1.iterdir() if p.is_file()]
    return run_pipeline(files, load(ROOT / "configs" / "default.json"),
                        as_of=(2026, 8), collect_ui=True)


def cand(run, name):
    return [c for c in run.ui_bundle["candidates"]
            if c["canonical"]["full_name"] == name][0]


def test_collect_ui_does_not_change_outputs(ui_run):
    files = [p for p in T1.iterdir() if p.is_file()]
    plain = run_pipeline(files, load(ROOT / "configs" / "default.json"),
                         as_of=(2026, 8))
    assert dumps(plain.profiles) == dumps(ui_run.profiles)
    assert dumps(plain.report) == dumps(ui_run.report)
    assert "_debug" not in ui_run.ui_bundle["candidates"][0]["canonical"]


def test_sources_carry_content(ui_run):
    by_id = {s["source_id"]: s for s in ui_run.ui_bundle["sources"]}
    assert by_id["t1_roster.csv"]["content"]["kind"] == "csv"
    assert "Avery Stone" in by_id["t1_roster.csv"]["content"]["text"]
    # docx content is the *extracted* text — exactly what the engine saw.
    assert "Curriculum Vitae" in by_id["resume_p07.docx"]["content"]["text"]


def test_locators_ground_evidence(ui_run):
    avery = cand(ui_run, "Avery Stone")
    email_atoms = avery["debug"]["emails"]["elements"][0]["atoms"]
    csv_atom = [a for a in email_atoms if a["source_id"] == "t1_roster.csv"][0]
    assert csv_atom["locator"] == {"kind": "cell", "row": 1, "col": "email"}
    notes_atom = [a for a in email_atoms if a["source_id"] == "notes_p01.txt"][0]
    span = notes_atom["locator"]
    body = [s for s in ui_run.ui_bundle["sources"]
            if s["source_id"] == "notes_p01.txt"][0]["content"]["text"]
    assert body[span["start"]:span["end"]] == "avery.stone@example.com"


def test_trace_matches_field_confidence(ui_run):
    grace = cand(ui_run, "Grace Obi")
    dbg = grace["debug"]["full_name"]
    assert dbg["trace"]["confidence"] == grace["canonical"]["field_confidence"]["full_name"]
    assert dbg["trace"]["support"] < 1.0  # the CSV disagreement is visible


def test_excluded_candidates_still_present_for_ui(ui_run):
    files = [p for p in T1.iterdir() if p.is_file()]
    rv = run_pipeline(files, load(ROOT / "configs" / "recruiter_view.json"),
                      as_of=(2026, 8), collect_ui=True)
    excluded = [c for c in rv.ui_bundle["candidates"] if c["excluded"]]
    assert len(excluded) == 4  # visible in the UI, absent from profiles.json
