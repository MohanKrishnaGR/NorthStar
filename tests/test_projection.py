"""M5: projection layer tests (DESIGN §5 rows 8, 15; PLAN §4)."""
import pytest

from transformer.projection import paths, schema
from transformer.projection.config import ConfigError, load
from transformer.projection.project import project

PROFILE = {
    "candidate_id": "abc123",
    "full_name": "Alice Fern",
    "emails": ["alice.fern@gmail.com", "afern@work.com"],
    "phones": ["+14155552671"],
    "location": {"city": "San Francisco", "region": "CA", "country": "US"},
    "links": {"linkedin": None, "github": "https://github.com/alicefern",
              "portfolio": None, "other": []},
    "headline": None,
    "years_experience": 8.6,
    "skills": [
        {"name": "python", "canonical": True, "confidence": 0.99, "sources": ["ats.json"]},
        {"name": "airflow", "canonical": True, "confidence": 0.9, "sources": ["ats.json"]},
    ],
    "experience": [], "education": [],
    "provenance": [
        {"field": "full_name", "source": "ats.json", "method": "direct_field",
         "alternatives": []},
        {"field": "emails[0]", "source": "ats.json", "method": "direct_field",
         "alternatives": []},
        {"field": "emails[1]", "source": "r.csv", "method": "direct_field",
         "alternatives": []},
    ],
    "field_confidence": {"full_name": 0.985, "emails": 0.945, "phones": 0.9,
                         "skills": 0.99},
    "overall_confidence": 0.61,
}


# ------------------------------------------------------------------ path DSL


def test_four_path_constructs():
    assert paths.resolve(PROFILE, paths.parse("full_name")) == "Alice Fern"
    assert paths.resolve(PROFILE, paths.parse("location.city")) == "San Francisco"
    assert paths.resolve(PROFILE, paths.parse("emails[0]")) == "alice.fern@gmail.com"
    assert paths.resolve(PROFILE, paths.parse("skills[].name")) == ["python", "airflow"]


def test_path_missing_and_empty_array_distinction():
    assert paths.resolve(PROFILE, paths.parse("headline")) is paths.MISSING
    assert paths.resolve(PROFILE, paths.parse("emails[5]")) is paths.MISSING
    empty = dict(PROFILE, skills=[])
    assert paths.resolve(empty, paths.parse("skills[].name")) == []  # present!


def test_path_grammar_limits():
    with pytest.raises(paths.PathError):
        paths.parse("skills[].sources[]")  # two maps
    with pytest.raises(paths.PathError):
        paths.parse("emails[x]")


# ------------------------------------------------------- config load rejects


def _cfg(fields, **kw):
    return {"fields": fields, **kw}


REJECTS = [
    _cfg([{"path": "e", "from": "emials[0]", "type": "string"}]),  # typo path
    _cfg([{"path": "n", "from": "full_name", "type": "number"}]),  # type clash
    _cfg([{"path": "n", "from": "full_name", "type": "string",
           "normalize": "E164"}]),  # normalizer/type incompatible
    _cfg([{"path": "a", "from": "full_name", "type": "string"},
          {"path": "a", "from": "headline", "type": "string"}]),  # dup path
    _cfg([{"path": "a", "from": "full_name", "type": "string"},
          {"path": "a.b", "from": "headline", "type": "string"}]),  # parent/child
    _cfg([{"path": "out[0]", "from": "emails", "type": "string[]"}]),  # bracket out
    _cfg([]),  # empty fields
    _cfg([{"path": "x", "from": "full_name", "type": "string"}],
         on_missing="explode"),  # bad on_missing
]


@pytest.mark.parametrize("doc", REJECTS)
def test_config_load_rejections(doc):
    with pytest.raises(ConfigError):
        load(doc)


def test_config_from_defaults_to_path():
    cfg = load(_cfg([{"path": "full_name", "type": "string"}]))
    assert cfg.fields[0].from_path == "full_name"


# --------------------------------------------------- on_missing x required


def _one_field(required, on_missing):
    return load(_cfg(
        [{"path": "headline", "type": "string", "required": required}],
        on_missing=on_missing,
    ))


def test_missing_optional_null():
    out, errors, _ = project(PROFILE, _one_field(False, "null"))
    assert out == {"headline": None} and not errors


def test_missing_optional_omit():
    out, errors, _ = project(PROFILE, _one_field(False, "omit"))
    assert out == {} and not errors


def test_missing_optional_error():
    out, errors, _ = project(PROFILE, _one_field(False, "error"))
    assert out is None and errors[0]["problem"] == "missing"


@pytest.mark.parametrize("on_missing", ["null", "omit", "error"])
def test_missing_required_always_fails(on_missing):
    out, errors, _ = project(PROFILE, _one_field(True, on_missing))
    assert out is None and errors[0]["problem"] == "required_missing"


# ------------------------------------------------------- projection behavior


def test_recruiter_view_projection_and_rekeying():
    cfg = load({
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string",
             "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string",
             "normalize": "E164"},
            {"path": "skills", "from": "skills[].name", "type": "string[]",
             "normalize": "canonical"},
        ],
        "include_confidence": True, "include_provenance": True,
        "on_missing": "null",
    })
    out, errors, notes = project(PROFILE, cfg)
    assert not errors and not notes
    assert out["primary_email"] == "alice.fern@gmail.com"
    assert out["phone"] == "+14155552671"  # idempotent re-normalization
    assert out["skills"] == ["python", "airflow"]
    prov_fields = {p["field"] for p in out["provenance"]}
    assert "primary_email" in prov_fields  # re-keyed from emails[0]
    assert "emails[1]" not in prov_fields  # invisible fields drop out
    assert out["confidence"]["fields"]["primary_email"] == 0.945
    assert out["confidence"]["overall"] == 0.61


def test_normalize_failure_treated_as_missing_and_reported():
    broken = dict(PROFILE, phones=["junk-number"])
    cfg = load(_cfg([{"path": "phone", "from": "phones[0]", "type": "string",
                      "normalize": "E164"}]))
    out, errors, notes = project(broken, cfg)
    assert not errors and out == {"phone": None}
    assert notes[0]["field"] == "phone"


def test_nested_output_paths():
    cfg = load(_cfg([
        {"path": "contact.email", "from": "emails[0]", "type": "string"},
        {"path": "contact.city", "from": "location.city", "type": "string"},
    ]))
    out, errors, _ = project(PROFILE, cfg)
    assert out == {"contact": {"email": "alice.fern@gmail.com",
                               "city": "San Francisco"}}


# ------------------------------------------------------------ schema + validate


def test_generated_schema_accepts_output_and_rejects_junk():
    cfg = load({
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string"},
        ],
        "include_confidence": True, "on_missing": "null",
    })
    sch = schema.build(cfg)
    out, _, _ = project(PROFILE, cfg)
    assert schema.validate(out, sch) == []
    assert schema.validate({"full_name": 42, "primary_email": None,
                            "confidence": {"overall": 1, "fields": {}}}, sch)
    # extra keys are rejected: the output shape is exactly what was requested
    bad = dict(out, surprise=1)
    assert any("surprise" in e for e in schema.validate(bad, sch))
