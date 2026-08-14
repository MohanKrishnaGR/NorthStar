"""T1 golden corpus: one test per persona (see goldens/TRUTH.md).

Regenerate pinned bytes (then review the diff by eye!) with:
  python -m transformer run --input goldens/t1 --config configs/default.json \
    --out goldens/expected/t1_profiles_default.json \
    --report goldens/expected/t1_report_default.json --as-of 2026-08
  (same for configs/recruiter_view.json -> *_recruiter_view.json)
"""
from pathlib import Path

import pytest

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
T1 = ROOT / "goldens" / "t1"
EXPECTED = ROOT / "goldens" / "expected"
AS_OF = (2026, 8)

pytest.importorskip("docx", reason="T1 includes docx resumes (pip install .[resume])")


def t1_files():
    return [p for p in T1.iterdir() if p.is_file()]


@pytest.fixture(scope="module")
def default_run():
    return run_pipeline(t1_files(), load(ROOT / "configs" / "default.json"),
                        as_of=AS_OF)


@pytest.fixture(scope="module")
def rv_run():
    return run_pipeline(t1_files(), load(ROOT / "configs" / "recruiter_view.json"),
                        as_of=AS_OF)


def prof(run, name):
    got = [p for p in run.profiles if p.get("full_name") == name]
    assert len(got) == 1, f"expected exactly one profile named {name!r}, got {len(got)}"
    return got[0]


def cluster_containing(run, record_id):
    for c in run.report["merges"]["clusters"]:
        if record_id in c["record_ids"]:
            return c
    raise AssertionError(f"no cluster contains {record_id}")


def prov_entry(profile, field):
    got = [p for p in profile["provenance"] if p["field"] == field]
    assert got, f"no provenance for {field}"
    return got[0]


def skill(profile, name):
    got = [s for s in profile["skills"] if s["name"] == name]
    assert got, f"skill {name!r} not in profile"
    return got[0]


# ------------------------------------------------------------ pinned bytes


def test_gold_bytes_default(default_run):
    assert dumps(default_run.profiles) + "\n" == (
        EXPECTED / "t1_profiles_default.json").read_text(encoding="utf-8")
    assert dumps(default_run.report) + "\n" == (
        EXPECTED / "t1_report_default.json").read_text(encoding="utf-8")


def test_gold_bytes_recruiter_view(rv_run):
    assert dumps(rv_run.profiles) + "\n" == (
        EXPECTED / "t1_profiles_recruiter_view.json").read_text(encoding="utf-8")


# ------------------------------------------------------------- aggregates


def test_aggregate_counts_ids_refusals(default_run, rv_run):
    assert len(default_run.profiles) == 28
    assert len(rv_run.profiles) == 24
    ids = [p["candidate_id"] for p in default_run.profiles]
    assert len(ids) == len(set(ids))
    kinds = sorted(r["key"].split(":")[0] for r in default_run.report["merges"]["refusals"])
    assert kinds == ["email", "email", "phone", "phone"]
    reasons = {u["reason"] for u in default_run.report["unparseable"]}
    assert reasons == {"no_region_context", "inverted_date_range",
                       "future_dated_range"}


# --------------------------------------------------------------- personas


def test_p01_baseline_ceiling(default_run):
    avery = prof(default_run, "Avery Stone")
    assert len(cluster_containing(default_run, "t1_roster.csv#row=1")["record_ids"]) == 7
    assert avery["phones"] == ["+14155552671"]
    assert avery["years_experience"] == 5.6
    assert avery["location"]["country"] == "US"
    assert avery["links"]["github"] == "https://github.com/averystone"
    assert avery["links"]["portfolio"] == "https://averystone.dev"  # D4
    assert avery["links"]["other"] == []
    assert avery["flags"] == []  # clean clusters carry an empty flags list
    # GitHub-derived 'go' sits below every explicitly claimed skill.
    assert skill(avery, "go")["confidence"] < min(
        skill(avery, n)["confidence"] for n in ("python", "sql", "airflow"))
    # Ceiling vs floor: the fully-corroborated profile outranks the notes-only
    # ghost on both the name score and overall.
    noor = prof(default_run, "Noor Zaidi")
    assert avery["confidence"]["overall"] > noor["confidence"]["overall"]
    assert (avery["confidence"]["fields"]["full_name"]
            > noor["confidence"]["fields"]["full_name"])


def test_p02_tagged_email_variants(default_run):
    bina = prof(default_run, "Bina Rao")
    assert len(bina["emails"]) == 3
    assert bina["emails"][0] == "bina.rao+jobs@gmail.com"  # trust-ordered
    assert bina["experience"][0]["title"] == "Senior Data Analyst"


def test_p03_reordered_nfd_name_merges(default_run):
    carlos = prof(default_run, "Núñez, Carlos")
    assert len(cluster_containing(default_run, "t1_roster.csv#row=3")["record_ids"]) == 2
    assert prov_entry(carlos, "full_name")["alternatives"] == ["Carlos Núñez"]
    assert carlos["years_experience"] == 4.7


def test_p04_pass2_resolves_and_corroborates(default_run):
    devi = prof(default_run, "Devi Iyer")
    assert devi["phones"] == ["+919812345678"]


def test_p04b_no_region_context_stays_empty(default_run):
    farid = prof(default_run, "Farid Khan")
    assert farid["phones"] == []
    assert any(u["reason"] == "no_region_context"
               for u in default_run.report["unparseable"])


def test_p05_conflicts_penalized_and_preserved(default_run):
    grace = prof(default_run, "Grace Obi")
    avery = prof(default_run, "Avery Stone")
    assert prov_entry(grace, "full_name")["alternatives"] == ["Grace N. Obi"]
    assert (grace["confidence"]["fields"]["full_name"]
            < avery["confidence"]["fields"]["full_name"])
    assert {s["name"] for s in grace["skills"]} == {"sql", "python"}  # string split
    assert len(grace["experience"]) == 2  # Retail vs Retail Group: append


def test_p06_promoted_link_key_join_no_double_count(default_run):
    hana = prof(default_run, "Hana Suzuki")
    cluster = cluster_containing(default_run, "linkedin_hanasuzuki.json#profile")
    assert any(k.startswith("link:") for k in cluster["match_keys_used"])
    assert hana["years_experience"] == 6.7
    assert len(hana["experience"]) == 3  # manager, senior, advisor
    assert hana["education"][0]["institution"] == "Kyoto University"


def test_p07_education_extracted_from_resume(default_run):
    ishaan = prof(default_run, "Ishaan Verma")
    assert ishaan["education"] == [{
        "institution": "IIT Bombay", "degree": "B.Tech",
        "field": "Data Engineering", "end_year": 2018,
    }]


def test_p07_year_only_precision(default_run):
    ishaan = prof(default_run, "Ishaan Verma")  # name via notes label, not "Curriculum Vitae"
    quanta = [e for e in ishaan["experience"] if e["company"] == "Quanta Insights"][0]
    assert quanta["start"] == "2019" and quanta["end"] == "2021"  # never -01
    meridian = [e for e in ishaan["experience"] if "Meridian" in e["company"]][0]
    assert meridian["start"] == "2021"  # ambiguous 03/04/2021 keeps year only
    assert ishaan["years_experience"] == 3.0


def test_p08_derived_beats_stated(default_run):
    jorge = prof(default_run, "Jorge Silva")
    assert jorge["years_experience"] == 5.3
    p = prov_entry(jorge, "years_experience")
    assert p["method"].startswith("derived:") and "15" in p["alternatives"]


def test_p09_twins_with_strong_keys_stay_apart(default_run):
    twins = [p for p in default_run.profiles if p["full_name"] == "Kiran Patel"]
    assert len(twins) == 2
    assert twins[0]["candidate_id"] != twins[1]["candidate_id"]


def test_p10_twins_without_keys_soft_merge_documented(default_run):
    lenas = [p for p in default_run.profiles if p["full_name"] == "Lena Novak"]
    assert len(lenas) == 1  # the documented soft-key false-merge boundary
    assert lenas[0]["flags"] == ["soft_key_merge"]  # D3: visible in output


def test_p11_shared_inbox_refused_distinct_ids(default_run):
    sam, dana = prof(default_run, "Sam Ortiz"), prof(default_run, "Dana Kim")
    assert sam["candidate_id"] != dana["candidate_id"]  # contested-key fix
    assert sam["emails"] == dana["emails"] == ["referrals@agency.example"]


def test_p12_switchboard_phone_refused(default_run):
    omar, petra = prof(default_run, "Omar Haddad"), prof(default_run, "Petra Vogel")
    assert omar["phones"] == petra["phones"] == ["+14155552672"]
    assert omar["candidate_id"] != petra["candidate_id"]


def test_p13_chain_positive(default_run):
    cluster = cluster_containing(default_run, "notes_chain.txt#file")
    assert len(cluster["record_ids"]) == 3
    chen = prof(default_run, "C. Chen")  # ATS trust wins the name
    assert prov_entry(chen, "full_name")["alternatives"] == ["Casey Chen"]
    assert {s["name"] for s in chen["skills"]} >= {"kafka", "kubernetes"}


def test_p13b_broken_chain_refused(default_run):
    priya = prof(default_run, "Priya Patel")
    assert priya["phones"] == ["+14155552674"]
    blair = prof(default_run, "Blair Novak")
    assert blair["candidate_id"] != priya["candidate_id"]


def test_p14_gossip_isolated(default_run):
    srcs = {s["source_id"]: s for s in default_run.report["sources"]}
    assert srcs["notes_gossip.txt"]["flags"] == ["multi_identity_source"]
    gossip = [p for p in default_run.profiles if p["full_name"] is None
              and len(p["emails"]) == 3]
    assert len(gossip) == 1
    # D3: the caution rides the profile itself, not just the report.
    assert gossip[0]["flags"] == ["multi_identity_source"]
    avery = prof(default_run, "Avery Stone")
    assert "avery.stone@example.com" in gossip[0]["emails"]  # named, not attached
    assert gossip[0]["candidate_id"] != avery["candidate_id"]


def test_p15_ghost_floor_and_exclusion(default_run, rv_run):
    noor = prof(default_run, "Noor Zaidi")
    assert noor["emails"] == [] and {s["name"] for s in noor["skills"]} == {"sql"}
    assert not any(p.get("full_name") == "Noor Zaidi" for p in rv_run.profiles)


def test_p16_cjk_spacing_documented_split(default_run):
    spaced = prof(default_run, "田中 太郎")
    unspaced = prof(default_run, "田中太郎")
    assert spaced["candidate_id"] != unspaced["candidate_id"]
    email_refusals = [r for r in default_run.report["merges"]["refusals"]
                      if r["key"] == "email:taro.tanaka@example.jp"]
    assert email_refusals  # DESIGN §5 row 19: visible, not hidden


def test_p17_hoarder_skills_gauntlet(default_run):
    rhea = prof(default_run, "Rhea Hoardley")
    names = {s["name"] for s in rhea["skills"]}
    assert {"react", "go", "kubernetes", "typescript", "python"} <= names
    assert "spring" not in names and "rest" not in names  # bait resisted
    assert skill(rhea, "ms office")["canonical"] is False
    assert skill(rhea, "yaml")["confidence"] < skill(rhea, "react")["confidence"]
    assert rhea["full_name"] == "Rhea Hoardley"  # GitHub name:null promoted nothing


def test_p18_url_conflict_and_param_corroboration(default_run):
    tomas = prof(default_run, "Tomas Eder")
    assert tomas["links"]["linkedin"] == "https://linkedin.com/in/tomas-eder"
    alts = prov_entry(tomas, "links.linkedin")["alternatives"]
    assert any("tomas-eder-alt" in a for a in alts)
    assert tomas["links"]["github"] == "https://github.com/teder"
    assert tomas["links"]["portfolio"] == "https://tomas.dev"  # D4
    assert tomas["links"]["other"] == []


def test_p19_degenerate_dates(default_run):
    uma = prof(default_run, "Uma Reddy")
    assert uma["years_experience"] == 0.1  # only the sane one-month job
    assert len(uma["experience"]) == 4  # entries still emitted honestly
    # D1a: the fully-future CLOSED range (Futura LLC) is dropped too now.
    reasons = [u["reason"] for u in default_run.report["unparseable"]]
    assert "future_dated_range" in reasons and "inverted_date_range" in reasons


def test_p20_cp1252_accents_survive(default_run):
    renee = prof(default_run, "Renée Fontaine")
    assert renee["phones"] == ["+33612345678"]
    assert renee["experience"][0]["company"] == "Café Lumière"


# P21 "The Portable": one fixture, three mechanisms — three test functions,
# so a failure names what broke (RESUME_PLAN R1 assert-separation).


def test_p21_pdf_acquisition(default_run):
    src = [s for s in default_run.report["sources"]
           if s["source_id"] == "resume_p21.pdf"][0]
    assert src["status"] == "ok" and src["evidence_emitted"] > 0
    wale = prof(default_run, "Wale Adeyemi")  # pipe line: name = first segment
    assert wale["emails"] == ["wale.adeyemi@example.com"]
    assert wale["phones"] == ["+447911123456"]
    assert {s["name"] for s in wale["skills"]} == {"python", "terraform", "kafka"}


def test_p21_block_experience_from_pdf(default_run):
    wale = prof(default_run, "Wale Adeyemi")
    assert wale["experience"] == [{
        "company": "Harmattan Cloud", "title": "Platform Engineer",
        "start": "2022-03", "end": None, "is_current": True, "summary": None,
    }]
    assert wale["years_experience"] == 4.5  # 2022-03 → as-of 2026-08


def test_p21_education_from_pdf(default_run):
    wale = prof(default_run, "Wale Adeyemi")
    assert wale["education"] == [{
        "institution": "University of Lagos", "degree": "B.Sc",
        "field": "Computer Science", "end_year": 2016,
    }]


def test_p01_table_skill_from_docx(default_run):
    avery = prof(default_run, "Avery Stone")
    terra = skill(avery, "terraform")  # lives only in the resume's table
    assert terra["sources"] == ["resume_p01.docx"]
