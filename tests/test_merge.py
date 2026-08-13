"""M4b: merge/survivorship tests (DESIGN §5 rows 1, 2, 5, 11, 13, 14)."""
from transformer.merge import merge_cluster
from transformer.models import Evidence, SourceRecord

AS_OF = (2026, 8)


def build(records_spec):
    """records_spec: list of (record_id, source_type, updated_at, [(field, value, method)])"""
    records = {}
    for rid, stype, updated, atoms in records_spec:
        rec = SourceRecord(record_id=rid, source_id=rid.split("#")[0],
                           source_type=stype, updated_at=updated)
        for i, (path, value, method) in enumerate(atoms):
            rec.evidence.append(Evidence(
                field_path=path, value=value, raw_value=value,
                source_id=rec.source_id, source_type=stype, method=method,
                record_id=rid, order_index=i))
        records[rid] = rec
    cluster = {"cluster_id": min(records), "record_ids": sorted(records),
               "match_keys_used": []}
    return cluster, records


def run(records_spec, as_of=AS_OF):
    cluster, records = build(records_spec)
    return merge_cluster(cluster, records, as_of)


def exp_entry(company, title, start, end, current, summary=None):
    return {"company": company, "title": title, "start": start, "end": end,
            "is_current": current, "summary": summary}


def test_scalar_conflict_winner_alternatives_and_penalty():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", "2026-05-01",
         [("full_name", "Rohan Mehta", "direct_field")]),
        ("n.txt#file", "notes_txt", None,
         [("full_name", "Rohan M.", "regex:labeled_name_v1")]),
    ])
    assert profile["full_name"] == "Rohan Mehta"  # trust order
    p = [x for x in profile["provenance"] if x["field"] == "full_name"][0]
    assert p["source"] == "ats.json" and p["alternatives"] == ["Rohan M."]
    assert 0 < profile["field_confidence"]["full_name"] < 0.90  # penalized


def test_location_merges_atomically_no_chimera():
    ats_loc = {"city": "Bengaluru", "region": None, "country": "IN"}
    notes_loc = {"city": "San Francisco", "region": None, "country": "US"}
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None, [("location", ats_loc, "direct_field")]),
        ("n.txt#file", "notes_txt", None,
         [("location", notes_loc, "regex:labeled_location_v1")]),
    ])
    assert profile["location"] in (ats_loc, notes_loc)  # whole struct, one source
    assert profile["location"] == ats_loc  # trust picks ATS


def test_sets_ordered_by_confidence_then_value():
    profile, _ = run([
        ("r.csv#row=1", "recruiter_csv", None,
         [("emails", "solo@x.com", "direct_field")]),
        ("ats.json#idx=0", "ats_json", None,
         [("emails", "corroborated@x.com", "direct_field")]),
        ("n.txt#file", "notes_txt", None,
         [("emails", "corroborated@x.com", "regex:email_v1")]),
    ])
    assert profile["emails"][0] == "corroborated@x.com"  # emails[0] = most trusted


def test_phone_pass2_uses_cluster_country():
    profile, notes = run([
        ("ats.json#idx=0", "ats_json", None,
         [("location", {"city": "Bengaluru", "region": None, "country": "IN"},
           "direct_field")]),
        ("r.csv#row=1", "recruiter_csv", None,
         [("phones_raw", "98765 43210", "direct_field")]),
    ])
    assert profile["phones"] == ["+919876543210"] and notes == []


def test_phone_without_any_region_reported_not_guessed():
    profile, notes = run([
        ("r.csv#row=1", "recruiter_csv", None,
         [("phones_raw", "98765 43210", "direct_field")]),
    ])
    assert profile["phones"] == []
    assert notes[0]["reason"] == "no_region_context"


def test_dateless_current_merges_with_dated_current_same_company():
    profile, _ = run([
        ("r.csv#row=1", "recruiter_csv", None,
         [("experience", exp_entry("Zenlytics", "Backend Engineer",
                                   None, None, True), "direct_field")]),
        ("ats.json#idx=0", "ats_json", None,
         [("experience", exp_entry("Zenlytics", "Senior Backend Engineer",
                                   (2022, 3), None, True), "direct_field")]),
    ])
    assert len(profile["experience"]) == 1
    got = profile["experience"][0]
    assert got["title"] == "Senior Backend Engineer"  # ATS trust wins
    assert got["start"] == "2022-03" and got["is_current"] is True


def test_promotion_stays_two_entries():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None, [
            ("experience", exp_entry("Zenlytics", "Senior Backend Engineer",
                                     (2022, 3), None, True), "direct_field"),
            ("experience", exp_entry("Zenlytics", "Backend Engineer",
                                     (2019, 7), (2022, 2), False), "direct_field"),
        ]),
    ])
    assert len(profile["experience"]) == 2  # sequential ranges never fuse


def test_years_experience_interval_union_no_double_count():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None, [
            ("experience", exp_entry("BlueYonder", "Sr DE",
                                     (2021, 6), None, True), "direct_field"),
            ("experience", exp_entry("Nimbus", "DE",
                                     (2018, 2), (2021, 5), False), "direct_field"),
        ]),
    ])
    # 2018-02..2021-05 = 40mo; 2021-06..2026-08 = 63mo; contiguous union 103mo.
    assert profile["years_experience"] == 8.6


def test_derived_years_beats_stated_and_records_alternative():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None, [
            ("experience", exp_entry("BlueYonder", "Sr DE",
                                     (2021, 6), None, True), "direct_field"),
            ("years_experience", 15, "direct_field"),
        ]),
    ])
    assert profile["years_experience"] == 5.3  # 63mo = 5.25y, HALF_UP -> 5.3
    p = [x for x in profile["provenance"] if x["field"] == "years_experience"][0]
    assert p["method"].startswith("derived:") and "15" in p["alternatives"]


def test_current_job_without_as_of_yields_null_years():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None, [
            ("experience", exp_entry("BlueYonder", "Sr DE",
                                     (2021, 6), None, True), "direct_field"),
        ]),
    ], as_of=None)
    assert profile["years_experience"] is None  # no clock is ever consulted


def test_skills_union_with_flags_and_sources():
    profile, _ = run([
        ("ats.json#idx=0", "ats_json", None,
         [("skills", {"name": "python", "canonical": True}, "dict:skill_alias_v1")]),
        ("n.txt#file", "notes_txt", None,
         [("skills", {"name": "python", "canonical": True}, "dict:skill_scan_v1"),
          ("skills", {"name": "quantum basket weaving", "canonical": False},
           "dict:skill_scan_v1")]),
    ])
    names = {s["name"]: s for s in profile["skills"]}
    assert names["python"]["sources"] == ["ats.json", "n.txt"]
    assert names["quantum basket weaving"]["canonical"] is False
    assert profile["skills"][0]["name"] == "python"  # corroborated first


def test_candidate_id_is_content_derived_and_stable():
    spec = [("r.csv#row=1", "recruiter_csv", None,
             [("emails", "alice.fern@gmail.com", "direct_field")])]
    a, _ = run(spec)
    b, _ = run(spec)
    assert a["candidate_id"] == b["candidate_id"]
    # Same person via a plus-tagged variant -> same id (match-key seeded).
    c, _ = run([("x.json#idx=0", "ats_json", None,
                 [("emails", "alice.fern+jobs@gmail.com", "direct_field")])])
    assert c["candidate_id"] == a["candidate_id"]
