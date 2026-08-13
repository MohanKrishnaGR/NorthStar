"""Metamorphic suite (GOLDEN_DATASET §6.4): dataset-wide invariants that need
no gold at all — properties that must hold under input perturbation."""
from pathlib import Path

import pytest

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
T1 = ROOT / "goldens" / "t1"
AS_OF = (2026, 8)

pytest.importorskip("docx", reason="T1 includes docx resumes")


def cfg():
    return load(ROOT / "configs" / "default.json")


def t1_files():
    return [p for p in T1.iterdir() if p.is_file()]


def profile(run, name):
    return [p for p in run.profiles if p.get("full_name") == name][0]


def test_file_order_is_irrelevant():
    fwd = run_pipeline(t1_files(), cfg(), as_of=AS_OF)
    rev = run_pipeline(list(reversed(t1_files())), cfg(), as_of=AS_OF)
    assert dumps(fwd.profiles) == dumps(rev.profiles)
    assert dumps(fwd.report) == dumps(rev.report)


def test_removing_a_corroborator_never_raises_confidence():
    full = run_pipeline(t1_files(), cfg(), as_of=AS_OF)
    without = run_pipeline(
        [p for p in t1_files() if p.name != "notes_p01.txt"], cfg(), as_of=AS_OF)
    before = profile(full, "Avery Stone")["confidence"]["fields"]
    after = profile(without, "Avery Stone")["confidence"]["fields"]
    for field in ("full_name", "emails", "skills"):
        assert after[field] <= before[field], field


def test_removing_a_contradictor_never_lowers_the_winner():
    # notes_p18.txt carries the losing alt-slug LinkedIn URL for Tomas Eder.
    full = run_pipeline(t1_files(), cfg(), as_of=AS_OF)
    without = run_pipeline(
        [p for p in t1_files() if p.name != "notes_p18.txt"], cfg(), as_of=AS_OF)
    before = profile(full, "Tomas Eder")["confidence"]["fields"]["links"]
    after = profile(without, "Tomas Eder")["confidence"]["fields"]["links"]
    assert after >= before
    assert profile(without, "Tomas Eder")["links"]["linkedin"] == \
        profile(full, "Tomas Eder")["links"]["linkedin"]  # winner unchanged


def test_adding_an_empty_source_changes_no_profile():
    base = run_pipeline(t1_files(), cfg(), as_of=AS_OF)
    padded = run_pipeline(t1_files() + [ROOT / "samples" / "empty.csv"],
                          cfg(), as_of=AS_OF)
    assert dumps(base.profiles) == dumps(padded.profiles)
