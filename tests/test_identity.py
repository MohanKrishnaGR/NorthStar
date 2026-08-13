"""M3: identity resolution tests (DESIGN §5 rows 4, 10; PLAN §4)."""
import pytest

from transformer.identity import names_compatible, resolve
from transformer.models import Evidence, SourceRecord


def mkrec(rid, source_type="recruiter_csv", name=None, mails=(), phone_nums=(),
          company=None):
    rec = SourceRecord(record_id=rid, source_id=rid.split("#")[0],
                       source_type=source_type)
    i = 0

    def add(path, value):
        nonlocal i
        rec.evidence.append(Evidence(
            field_path=path, value=value, raw_value=value,
            source_id=rec.source_id, source_type=source_type,
            method="direct_field", record_id=rid, order_index=i))
        i += 1

    if name:
        add("full_name", name)
    for m in mails:
        add("emails", m)
    for p in phone_nums:
        add("phones", p)
    if company:
        add("experience", {"company": company, "title": None, "start": None,
                           "end": None, "is_current": True, "summary": None})
    return rec


# ------------------------------------------------------- name predicate table

NAME_TABLE = [
    ("Mohan Krishna", "M. Krishna", True),   # initial prefix
    ("Mohan Krishna", "Krishna Mohan", True),  # token reorder
    ("Alice Fern", "Fern, Alice", True),
    ("José García", "Jose Garcia", True),    # accent-insensitive comparison
    ("Mohan Krishna", "Priya Sharma", False),
    ("Bob Smith", "Robert Smith", True),     # shared surname carries it
    ("Bob", "Robert", False),                # bare nicknames stay apart
]


@pytest.mark.parametrize("a,b,want", NAME_TABLE)
def test_names_compatible(a, b, want):
    assert names_compatible(a, b) is want
    assert names_compatible(b, a) is want  # symmetric


# ------------------------------------------------------------------- merging


def test_email_match_key_merges_plus_tag_variants():
    res = resolve([
        mkrec("a.csv#row=1", name="Alice Fern", mails=["alice.fern@gmail.com"]),
        mkrec("b.json#idx=0", "ats_json", name="Alice Fern",
              mails=["alice.fern+jobs@gmail.com"]),
    ])
    assert len(res.clusters) == 1
    assert res.clusters[0]["record_ids"] == ["a.csv#row=1", "b.json#idx=0"]


def test_shared_phone_unions_different_emails():
    res = resolve([
        mkrec("a.csv#row=1", name="Priya Sharma", mails=["priya@sharma.dev"],
              phone_nums=["+918765432109"]),
        mkrec("b.json#idx=0", "ats_json", name="Priya Sharma",
              mails=["priya.sharma@nimbus.io"], phone_nums=["+918765432109"]),
    ])
    assert len(res.clusters) == 1


def test_soft_key_only_without_strong_keys():
    merged = resolve([
        mkrec("a.csv#row=1", name="Dana Wu", company="Acme"),
        mkrec("b.csv#row=1", name="Dana Wu", company="Acme"),
    ])
    assert len(merged.clusters) == 1
    apart = resolve([
        mkrec("a.csv#row=1", name="Dana Wu", company="Acme"),
        mkrec("b.csv#row=1", name="Dana Wu", company="Globex"),
    ])
    assert len(apart.clusters) == 2


def test_transitive_contradiction_guard():
    # A-B share an email; B-C share a phone; A and C are different people.
    a = mkrec("a.csv#row=1", name="Alice Fern", mails=["shared@ref.com"])
    b = mkrec("b.json#idx=0", "ats_json", name="A. Fern",
              mails=["shared@ref.com"], phone_nums=["+14155552671"])
    c = mkrec("c.csv#row=1", name="Priya Sharma", phone_nums=["+14155552671"])
    res = resolve([a, b, c])
    sizes = sorted(len(cl["record_ids"]) for cl in res.clusters)
    assert sizes == [1, 2]  # AB fused, C refused — never ABC
    assert res.refusals and res.refusals[0]["reason"] == "suspect_shared_identifier"


def test_multi_identity_notes_file_attaches_to_no_one():
    notes = mkrec("notes.txt#file", "notes_txt",
                  mails=["alice.fern@gmail.com", "priya.sharma@nimbus.io"])
    alice = mkrec("a.csv#row=1", name="Alice Fern", mails=["alice.fern@gmail.com"])
    priya = mkrec("a.csv#row=2", name="Priya Sharma", mails=["priya.sharma@nimbus.io"])
    res = resolve([notes, alice, priya])
    assert len(res.clusters) == 3  # notes stands alone; no transitive fusion
    assert res.record_flags["notes.txt#file"] == ["multi_identity_source"]


def test_structured_row_with_two_emails_still_merges():
    # A CSV row is one candidate by construction — two emails are both theirs.
    row = mkrec("a.csv#row=1", name="Alice Fern",
                mails=["alice.fern@gmail.com", "afern@work.com"])
    other = mkrec("b.json#idx=0", "ats_json", name="Alice Fern",
                  mails=["afern@work.com"])
    res = resolve([row, other])
    assert len(res.clusters) == 1


def test_link_key_joins_recorded_api_payload():
    # A GitHub fixture has no email/phone; the shared profile URL joins it.
    ats = mkrec("ats.json#idx=0", "ats_json", name="Alice Fern",
                mails=["alice.fern@gmail.com"])
    ats.evidence.append(Evidence(
        field_path="links.github", value="https://github.com/alicefern",
        raw_value="", source_id="ats.json", source_type="ats_json",
        method="direct_field", record_id="ats.json#idx=0", order_index=9))
    gh = mkrec("github_alicefern.json#user", "github_json")
    gh.evidence.append(Evidence(
        field_path="links.github",
        value="https://www.github.com/alicefern/",  # www + trailing slash
        raw_value="", source_id="github_alicefern.json",
        source_type="github_json", method="direct_field",
        record_id="github_alicefern.json#user", order_index=0))
    res = resolve([ats, gh])
    assert len(res.clusters) == 1
    assert any(k.startswith("link:") for k in res.clusters[0]["match_keys_used"])


def test_portfolio_links_are_not_match_keys():
    a = mkrec("a.csv#row=1", name="Dana Wu", mails=["dana@x.com"])
    b = mkrec("b.csv#row=1", name="Sam Ortiz", mails=["sam@y.com"])
    for rec in (a, b):
        rec.evidence.append(Evidence(
            field_path="links.other", value="https://agency.example.com",
            raw_value="", source_id=rec.source_id, source_type=rec.source_type,
            method="direct_field", record_id=rec.record_id, order_index=9))
    res = resolve([a, b])
    assert len(res.clusters) == 2  # a shared agency site fuses no one


def test_resolution_is_order_independent():
    recs = [
        mkrec("a.csv#row=1", name="Alice Fern", mails=["shared@ref.com"]),
        mkrec("b.json#idx=0", "ats_json", name="A. Fern",
              mails=["shared@ref.com"], phone_nums=["+14155552671"]),
        mkrec("c.csv#row=1", name="Priya Sharma", phone_nums=["+14155552671"]),
        mkrec("d.txt#file", "notes_txt",
              mails=["x@y.com", "z@w.com"]),
    ]
    fwd = resolve(recs)
    rev = resolve(list(reversed(recs)))
    assert [c["record_ids"] for c in fwd.clusters] == [
        c["record_ids"] for c in rev.clusters
    ]
    assert fwd.refusals == rev.refusals
