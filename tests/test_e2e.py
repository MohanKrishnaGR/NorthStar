"""M6: end-to-end runs over the sample fixtures (DESIGN §5 rows 3, 10, 15)."""
from pathlib import Path

import pytest

from transformer.cli import main
from transformer.pipeline import run_pipeline
from transformer.projection.config import load

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
AS_OF = (2026, 8)


def sample_files():
    return [p for p in SAMPLES.iterdir() if p.is_file()]


@pytest.fixture(scope="module")
def default_run():
    return run_pipeline(sample_files(), load(ROOT / "configs" / "default.json"),
                        as_of=AS_OF)


def by_name(result, name):
    for p in result.profiles:
        if p.get("full_name") == name:
            return p
    raise AssertionError(f"no profile named {name}")


def test_four_profiles_alice_merged_across_five_records(default_run):
    assert len(default_run.profiles) == 4  # Alice, Rohan, Priya, flagged notes
    alice_cluster = [
        c for c in default_run.report["merges"]["clusters"]
        if "ats.json#idx=0" in c["record_ids"]
    ][0]
    # 3 CSV rows (dup + plus-tag variant) + ATS + notes_alice = 5 records.
    assert len(alice_cluster["record_ids"]) == 5


def test_alice_profile_content(default_run):
    alice = by_name(default_run, "Alice Fern")
    assert set(alice["emails"]) == {"alice.fern@gmail.com",
                                    "alice.fern+jobs@gmail.com"}
    assert alice["phones"] == ["+14155552671"]  # CSV pass1 + ATS pass2 agree
    assert alice["location"] == {"city": "San Francisco", "region": "CA",
                                 "country": "US"}
    assert alice["links"]["github"] == "https://github.com/alicefern"
    # D4: her own-name domain earns the portfolio bucket at merge time.
    assert alice["links"]["portfolio"] == "https://alicefern.dev"
    assert alice["links"]["other"] == []
    assert alice["years_experience"] == 8.6
    comps = [(e["company"], e["start"], e["end"], e["is_current"])
             for e in alice["experience"]]
    assert ("BlueYonder Analytics", "2021-06", None, True) in comps
    assert ("Nimbus Retail", "2018-02", "2021-05", False) in comps
    assert len(alice["experience"]) == 2
    assert alice["education"][0]["institution"] == "IIT Delhi"
    skill_names = [s["name"] for s in alice["skills"]]
    assert "python" in skill_names
    qbw = [s for s in alice["skills"] if s["name"] == "quantum basket weaving"]
    assert qbw and qbw[0]["canonical"] is False  # kept, flagged, never dropped


def test_rohan_pass2_phone_corroborates_not_duplicates(default_run):
    rohan = by_name(default_run, "Rohan Mehta")
    assert rohan["phones"] == ["+919876543210"]  # one value, two sources
    # ATS title beats CSV title; CSV's is preserved as an alternative.
    blue = [p for p in rohan["provenance"] if p["field"] == "experience[0]"]
    assert blue and blue[0]["source"] == "ats.json"


def test_priya_unioned_via_shared_phone(default_run):
    priya = by_name(default_run, "Priya Sharma")
    assert set(priya["emails"]) == {"priya@sharma.dev", "priya.sharma@nimbus.io"}


def test_multi_identity_notes_isolated_and_flagged(default_run):
    srcs = {s["source_id"]: s for s in default_run.report["sources"]}
    assert "multi_identity_source" in srcs["notes_two_people.txt"]["flags"]
    ids = [p["candidate_id"] for p in default_run.profiles]
    assert len(ids) == len(set(ids))  # no id collision with Alice's profile


def test_garbage_and_empty_sources_contained(default_run):
    srcs = {s["source_id"]: s for s in default_run.report["sources"]}
    assert srcs["garbage.json"]["status"] == "skipped"
    assert srcs["empty.csv"]["status"] == "ok"
    assert srcs["recruiters.csv"]["status"] == "partial"  # shifted row contained


def test_custom_config_excludes_nameless_candidate():
    result = run_pipeline(sample_files(),
                          load(ROOT / "configs" / "recruiter_view.json"),
                          as_of=AS_OF)
    # The flagged notes cluster has no full_name -> required_missing.
    assert len(result.profiles) == 3
    assert any(v["problem"] == "required_missing"
               for v in result.report["validation"])
    out = result.profiles[0]
    assert set(out) == {"full_name", "primary_email", "phone", "skills",
                        "confidence"}


def test_default_as_of_derived_from_inputs():
    result = run_pipeline(sample_files(), load(ROOT / "configs" / "default.json"))
    # Latest date in the inputs is ats.json's lastUpdated 2026-05-14.
    assert result.report["run"]["as_of"] == "2026-05"


def test_cli_end_to_end(tmp_path):
    out, rep = tmp_path / "profiles.json", tmp_path / "report.json"
    code = main([
        "run", "--input", str(SAMPLES), "--config",
        str(ROOT / "configs" / "default.json"), "--out", str(out),
        "--report", str(rep), "--as-of", "2026-08",
    ])
    assert code == 0 and out.exists() and rep.exists()


def test_cli_bad_config_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"fields": [{"path": "x", "from": "emials[0]", '
                   '"type": "string"}]}', encoding="utf-8")
    code = main(["run", "--input", str(SAMPLES), "--config", str(bad),
                 "--out", str(tmp_path / "o.json"),
                 "--report", str(tmp_path / "r.json")])
    assert code == 2


def test_cli_no_readable_sources_exits_2(tmp_path):
    empty_dir = tmp_path / "inputs"
    empty_dir.mkdir()
    (empty_dir / "junk.xyz").write_text("nothing", encoding="utf-8")
    code = main(["run", "--input", str(empty_dir), "--config",
                 str(ROOT / "configs" / "default.json"),
                 "--out", str(tmp_path / "o.json"),
                 "--report", str(tmp_path / "r.json")])
    assert code == 2
