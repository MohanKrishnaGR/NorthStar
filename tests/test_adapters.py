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


def test_null_markers_never_become_values(tmp_path):
    f = tmp_path / "markers.csv"
    f.write_text(
        "name,email,phone,current_company,title\n"
        'Nolan Marker,nolan@example.com,N/A,—,tbd\n',
        encoding="utf-8",
    )
    res = run_adapter(recruiter_csv, f, CTX)
    rec = res.records[0]
    assert not _fields(rec, "phones") and not _fields(rec, "phones_raw")
    assert not _fields(rec, "experience")  # "—" company + "tbd" title filtered
    assert res.unparseable == []  # filtered silently, not reported as junk


def test_ats_skills_as_string_and_numeric_phone(tmp_path):
    f = tmp_path / "odd.json"
    f.write_text(
        '{"candidateName": "Skye String", "skills": "SQL, Python",'
        ' "phoneNumber": 9876543210, "designation": "n/a"}',
        encoding="utf-8",
    )
    res = run_adapter(ats_json, f, CTX)
    rec = res.records[0]
    names = {e.value["name"] for e in _fields(rec, "skills")}
    assert names == {"sql", "python"}  # not iterated as characters
    assert _fields(rec, "phones_raw")[0].value == "9876543210"  # str-coerced
    assert not _fields(rec, "experience")  # "n/a" designation filtered


def test_education_grammar_positive_and_negative(tmp_path):
    f = tmp_path / "edu.txt"
    f.write_text(
        "B.Tech in Computer Science, IIT Bombay, 2018\n"
        "M.S. Computer Science — Stanford University (2020)\n"
        "MBA, IIM Ahmedabad 2015\n"
        "Skills: MS Office, Excel\n"          # degree token, no institution
        "MS Office 2016 certified\n"           # year but still no institution
        "She will be joining Stanford University this fall\n",  # 'be' needs its dot
        encoding="utf-8",
    )
    res = run_adapter(notes_txt, f, CTX)
    edus = [e.value for e in res.records[0].evidence if e.field_path == "education"]
    assert len(edus) == 3  # the three real degrees, none of the bait
    by_inst = {e["institution"]: e for e in edus}
    assert by_inst["IIT Bombay"]["field"] == "Computer Science"
    assert by_inst["Stanford University"]["end_year"] == 2020
    assert by_inst["IIM Ahmedabad"]["degree"] == "MBA"


def test_block_experience_grammar(tmp_path):
    f = tmp_path / "blocks.txt"
    f.write_text(
        "Pixelforge — Frontend Lead\n"
        "Jan 2023 - Present\n"
        "\n"
        "Senior Analyst | Helios Retail\n"
        "2019 - 2021\n"
        "\n"
        "Joined in Jan 2020 after the merger\n"          # header has a date: no
        "We shipped to Mar 2021 deadlines and beyond\n",  # prose, not a pure range
        encoding="utf-8",
    )
    res = run_adapter(notes_txt, f, CTX)
    exps = [e.value for e in res.records[0].evidence
            if e.field_path == "experience"]
    assert len(exps) == 2
    pixel = [x for x in exps if x["company"] == "Pixelforge"][0]
    assert pixel["title"] == "Frontend Lead" and pixel["is_current"]
    assert pixel["start"] == (2023, 1)
    helios = [x for x in exps if x["company"] == "Helios Retail"][0]
    assert helios["title"] == "Senior Analyst"  # company found via suffix hint
    assert helios["start"] == (2019, None) and helios["end"] == (2021, None)


def test_garbage_json_is_contained():
    res = run_adapter(ats_json, SAMPLES / "garbage.json", CTX)
    assert res.status == "skipped" and res.errors and not res.records


def test_empty_csv_is_ok_with_zero_records():
    res = run_adapter(recruiter_csv, SAMPLES / "empty.csv", CTX)
    assert res.status == "ok" and res.records == []
