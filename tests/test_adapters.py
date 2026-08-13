"""M2: adapter tests against the sample fixtures (DESIGN §5 rows 3, 9)."""
from pathlib import Path

from transformer.adapters import ats_json, detect_adapter, notes_txt, recruiter_csv
from transformer.adapters.base import run_adapter

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
CTX = {"default_region": None, "strict": False}


def _fields(rec, path):
    return [e for e in rec.evidence if e.field_path == path]


def test_detection_registry():
    assert detect_adapter(SAMPLES / "recruiters.csv") is recruiter_csv
    assert detect_adapter(SAMPLES / "ats.json") is ats_json
    assert detect_adapter(SAMPLES / "notes_alice.txt") is notes_txt
    assert detect_adapter(SAMPLES / "unknown.xyz") is None


def test_csv_extracts_and_contains_shifted_row():
    res = run_adapter(recruiter_csv, SAMPLES / "recruiters.csv", CTX)
    assert res.status == "partial"  # the column-shifted row was contained
    assert res.records_read == 6 and len(res.records) == 5
    r1 = res.records[0]
    assert _fields(r1, "full_name")[0].value == "Alice Fern"
    assert _fields(r1, "emails")[0].value == "alice.fern@gmail.com"
    assert _fields(r1, "phones")[0].value == "+14155552671"
    exp = _fields(r1, "experience")[0].value
    assert exp["is_current"] is True and exp["start"] is None  # honest nulls


def test_csv_national_phone_without_region_stays_raw():
    res = run_adapter(recruiter_csv, SAMPLES / "recruiters.csv", CTX)
    rohan = res.records[1]
    assert not _fields(rohan, "phones")  # no silent +1/+91 guess (ADR-009)
    assert _fields(rohan, "phones_raw")[0].normalized is False


def test_ats_maps_foreign_fields():
    res = run_adapter(ats_json, SAMPLES / "ats.json", CTX)
    assert res.status == "ok" and len(res.records) == 3
    alice = res.records[0]
    assert alice.updated_at == "2026-05-14"  # in-band recency (ADR-016)
    assert _fields(alice, "full_name")[0].value == "Alice Fern"
    skills = [e.value for e in _fields(alice, "skills")]
    assert {"name": "python", "canonical": True} in skills
    assert {"name": "quantum basket weaving", "canonical": False} in skills
    jobs = [e.value for e in _fields(alice, "experience")]
    dated = [j for j in jobs if j["start"] == (2021, 6)]
    assert dated and dated[0]["is_current"] is True and dated[0]["end"] is None
    loc = _fields(alice, "location")[0].value
    assert loc == {"city": "San Francisco", "region": "CA", "country": "US"}


def test_ats_empty_to_means_unknown_not_present():
    res = run_adapter(ats_json, SAMPLES / "ats.json", CTX)
    priya = res.records[2]
    dated = [
        e.value for e in _fields(priya, "experience") if e.value["start"] == (2023, None)
    ]
    assert dated and dated[0]["is_current"] is False and dated[0]["end"] is None


def test_notes_extracts_labeled_and_scanned_fields():
    res = run_adapter(notes_txt, SAMPLES / "notes_alice.txt", CTX)
    rec = res.records[0]
    assert _fields(rec, "full_name")[0].value == "Alice Fern"
    assert _fields(rec, "emails")[0].value == "alice.fern@gmail.com"
    assert _fields(rec, "phones")[0].value == "+14155552671"
    assert {e.value["name"] for e in _fields(rec, "skills")} >= {
        "python", "airflow", "postgresql", "kubernetes",
    }
    assert _fields(rec, "links.github") and _fields(rec, "links.other")
    exps = [e.value for e in _fields(rec, "experience")]
    blue = [x for x in exps if x["company"] == "BlueYonder Analytics"]
    assert blue and blue[0]["start"] == (2021, 6) and blue[0]["is_current"]
    assert blue[0]["title"] == "Senior Data Engineer"
    nimbus = [x for x in exps if x["company"] == "Nimbus Retail"]
    assert nimbus and nimbus[0]["start"] == (2018, None)
    loc = _fields(rec, "location")[0].value
    assert loc["city"] == "San Francisco" and loc["country"] == "US"
    assert not _fields(rec, "phones_raw")  # "2018 - 2021" is not a phone


def test_garbage_json_is_contained():
    res = run_adapter(ats_json, SAMPLES / "garbage.json", CTX)
    assert res.status == "skipped" and res.errors and not res.records


def test_empty_csv_is_ok_with_zero_records():
    res = run_adapter(recruiter_csv, SAMPLES / "empty.csv", CTX)
    assert res.status == "ok" and res.records == []
