"""M7 stretch: resume adapter (skipped cleanly when extras not installed)."""
from pathlib import Path

import pytest

pytest.importorskip("docx", reason="resume extras not installed (pip install .[resume])")

from transformer.adapters import resume
from transformer.adapters.base import run_adapter
from transformer.pipeline import run_pipeline
from transformer.projection.config import load

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resume_alice.docx"
CTX = {"default_region": None, "strict": False}


def test_resume_extracts_name_contacts_skills():
    res = run_adapter(resume, FIXTURE, CTX)
    assert res.status == "ok"
    rec = res.records[0]
    by = {}
    for e in rec.evidence:
        by.setdefault(e.field_path, []).append(e)
    assert by["full_name"][0].value == "Alice Fern"
    assert by["full_name"][0].method == "regex:resume_title_name_v1"
    assert by["emails"][0].value == "alice.fern@gmail.com"
    assert by["phones"][0].value == "+14155552671"
    assert {e.value["name"] for e in by["skills"]} >= {
        "python", "postgresql", "terraform", "airflow",
    }
    assert all(e.source_type == "resume" for e in rec.evidence)


def test_resume_merges_into_alice_cluster_with_provenance():
    files = [p for p in SAMPLES.iterdir() if p.is_file()] + [FIXTURE]
    result = run_pipeline(files, load(ROOT / "configs" / "default.json"),
                          as_of=(2026, 8))
    assert len(result.profiles) == 4  # still four people — resume joined Alice
    alice = [p for p in result.profiles if p["full_name"] == "Alice Fern"][0]
    terra = [s for s in alice["skills"] if s["name"] == "terraform"]
    assert terra and terra[0]["sources"] == ["resume_alice.docx"]
    cluster = [c for c in result.report["merges"]["clusters"]
               if "resume_alice.docx#file" in c["record_ids"]][0]
    assert "ats.json#idx=0" in cluster["record_ids"]
    # Same experience entries as without the resume: it corroborates, not dupes.
    assert len(alice["experience"]) == 2


def test_garbage_docx_is_contained(tmp_path):
    bad = tmp_path / "broken.docx"
    bad.write_bytes(b"this is not a zip archive")
    res = run_adapter(resume, bad, CTX)
    assert res.status == "skipped" and res.errors
