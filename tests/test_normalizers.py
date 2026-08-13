"""M1: table-driven normalizer tests (PLAN.md §4 — DESIGN §5 rows 6, 7, 12)."""
import pytest

from transformer.normalize import (
    country,
    dates,
    emails,
    phones,
    registry,
    skills,
    text,
    urls,
)

# ---------------------------------------------------------------- text / NFC


def test_nfc_folds_visually_identical_names():
    nfd = "José"  # e + combining acute
    nfc = "José"
    assert text.fold(nfd) == text.fold(nfc)


def test_casefold_not_just_lower():
    assert text.fold("STRASSE") == text.fold("strasse".replace("ss", "ß"))


# -------------------------------------------------------------------- emails

EMAIL_CASES = [
    ("  Mohan.K@Gmail.COM ", "mohan.k@gmail.com"),
    ("<alice@example.com>", "alice@example.com"),
    ("not-an-email", None),
    ("a@b", None),
]


@pytest.mark.parametrize("raw,want", EMAIL_CASES)
def test_email_normalize(raw, want):
    assert emails.normalize(raw) == want


MATCH_KEY_CASES = [
    ("mohan.k+jobs@gmail.com", "mohank@gmail.com"),  # plus-tag + gmail dots
    ("mohan.k@googlemail.com", "mohank@gmail.com"),  # googlemail folds in
    ("a.b+x@company.com", "a.b@company.com"),  # dots kept off-gmail
]


@pytest.mark.parametrize("raw,want", MATCH_KEY_CASES)
def test_email_match_key(raw, want):
    assert emails.match_key(raw) == want


# -------------------------------------------------------------------- phones

PHONE_CASES = [
    ("+91 98765 43210", None, "+919876543210"),
    ("98765 43210", "IN", "+919876543210"),
    ("9876543210", None, None),  # no region context: refuse (ADR-009)
    ("+14155552671 ext. 22", None, "+14155552671"),
    ("garbage", "US", None),
    ("+919876543210", None, "+919876543210"),  # idempotent
]


@pytest.mark.parametrize("raw,region,want", PHONE_CASES)
def test_to_e164(raw, region, want):
    assert phones.to_e164(raw, region) == want


def test_phone_split_cell():
    got = phones.split_cell("+14155552671 / 98765 43210")
    assert len(got) == 2 and got[0].startswith("+1415")


# --------------------------------------------------------------------- dates

DATE_CASES = [
    ("Jan 2020", (2020, 1)),
    ("January 2020", (2020, 1)),
    ("2020-01", (2020, 1)),
    ("01/2020", (2020, 1)),
    ("2020", (2020, None)),
    ("2021-03-15", (2021, 3)),
    ("15/03/2021", (2021, 3)),  # 15 can't be a month: resolvable
    ("03/04/2021", (2021, None)),  # ambiguous month: honestly unknown
    ("03/03/2021", (2021, 3)),  # equal parts: unambiguous
    ("no date here", None),
]


@pytest.mark.parametrize("raw,want", DATE_CASES)
def test_date_parse(raw, want):
    assert dates.parse(raw) == want


def test_date_render_preserves_precision():
    assert dates.render((2020, 1)) == "2020-01"
    assert dates.render((2019, None)) == "2019"  # never coerced to January


RANGE_CASES = [
    ("Jan 2020 - Present", ((2020, 1), None, True)),
    ("Jan 2020 – Present", ((2020, 1), None, True)),
    ("2019 – 2021", ((2019, None), (2021, None), False)),
    ("since 2018", ((2018, None), None, True)),
    ("03/2019 to 11/2021", ((2019, 3), (2021, 11), False)),
]


@pytest.mark.parametrize("raw,want", RANGE_CASES)
def test_date_range(raw, want):
    assert dates.parse_range(raw) == want


def test_year_only_spans_whole_year_for_overlap():
    # "2019" overlaps "2019-06..2019-08"
    assert dates.overlaps(
        (2019, None), (2019, None), (2019, 6), (2019, 8), as_of=(2026, 8)
    )


# ------------------------------------------------------------------- country


@pytest.mark.parametrize(
    "raw,want",
    [("United States", "US"), ("usa", "US"), ("India", "IN"), ("U.K.", "GB"),
     ("Atlantis", None)],
)
def test_country(raw, want):
    assert country.to_iso2(raw) == want


# -------------------------------------------------------------------- skills

SKILL_CASES = [
    ("ReactJS", ("react", True)),
    ("Python 3.10", ("python", True)),
    ("JS (ES6)", ("javascript", True)),
    ("K8s", ("kubernetes", True)),
    ("Quantum Basket Weaving", ("quantum basket weaving", False)),  # kept, flagged
]


@pytest.mark.parametrize("raw,want", SKILL_CASES)
def test_skill_canonicalize(raw, want):
    assert skills.canonicalize(raw) == want


def test_skill_find_all_in_prose():
    body = "Built NLP pipelines with PyTorch; solid PostgreSQL and Kubernetes."
    got = skills.find_all(body)
    assert {"nlp", "pytorch", "postgresql", "kubernetes"} <= set(got)


def test_skill_scan_ignores_english_words():
    assert skills.find_all("let's go over the rest of the spring plan") == []


# ---------------------------------------------------------------------- urls


def test_url_classify():
    assert urls.classify("www.linkedin.com/in/alice")[0] == "linkedin"
    assert urls.classify("https://github.com/afern")[0] == "github"
    assert urls.classify("https://alice.dev")[0] == "other"


# ------------------------------------------------------------------ registry


def test_registry_apply_and_idempotency():
    assert registry.apply("E164", "+919876543210") == "+919876543210"
    assert registry.apply("YYYY-MM", "Jan 2020") == "2020-01"
    assert registry.apply("YYYY-MM", "2020-01") == "2020-01"  # idempotent
    assert registry.apply("ISO3166", "India") == "IN"
    assert registry.apply("canonical", ["ReactJS", "react"]) == ["react", "react"]


def test_registry_failure_raises_normalize_error():
    with pytest.raises(registry.NormalizeError):
        registry.apply("E164", "hello")
    with pytest.raises(registry.NormalizeError):
        registry.apply("ISO3166", "Atlantis")
