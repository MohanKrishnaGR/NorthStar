# Candidate Data Transformer

Turns messy multi-source candidate data (recruiter CSV, ATS JSON, recruiter
notes, resumes) into one canonical, deduplicated profile per candidate — with
per-field provenance, confidence scores, and a runtime config that reshapes
the output without code changes.

Design rationale lives in [DESIGN.md](DESIGN.md) (16 ADRs); the build plan in
[PLAN.md](PLAN.md). The one-line philosophy, from the problem statement:
**wrong-but-confident is worse than honestly-empty** — every tie here breaks
toward `null` plus an explanation in the run report, never a guess.

## Quickstart

```bash
pip install .            # Python 3.11+; deps: phonenumbers, jsonschema
pip install .[resume]    # optional: PDF/DOCX resume support
pip install .[dev]       # pytest

# Default canonical output + run report
python -m transformer run --input samples \
  --config configs/default.json \
  --out out/profiles_default.json --report out/run_report_default.json

# Custom projection (the problem statement's example config)
python -m transformer run --input samples \
  --config configs/recruiter_view.json \
  --out out/profiles_recruiter_view.json --report out/run_report_recruiter_view.json

python -m pytest -q      # 129 tests
```

The `out/` directory contains exactly what these two commands produce on the
sample inputs — and `tests/test_gold.py` fails if code and committed outputs
ever drift apart.

### CLI flags

| Flag | Meaning |
|---|---|
| `--as-of YYYY-MM` | Pins "now" for open-ended job durations. Default: the latest date observed in the inputs. **The system clock is never consulted** — reruns are byte-identical forever. |
| `--default-region IN` | Region for phones without `+CC`. Unset means such phones are never guessed into E.164; they are preserved raw and reported. |
| `--strict` | Development aid: re-raise adapter errors instead of containing them. |

Exit codes: `0` profiles emitted (report may carry warnings) · `2` unusable
config / bad arguments / zero readable sources. A garbage source is a
*reported condition*, never a crash.

## Pipeline

```
detect -> extract -> normalize (pass 1) -> resolve identity -> merge
       (+ phone pass 2) -> score confidence -> project (config) -> validate
```

Every extracted value is born as an **Evidence atom**
`{field, value, raw_value, source, method}`; merging is a pure function over
the canonically sorted pool. That single decision makes provenance free,
confidence auditable, and determinism provable (see the determinism suite:
same inputs, shuffled file order, touched mtimes → byte-identical output).

Confidence is transparent noisy-OR arithmetic over
`source_trust x method_reliability` (tables with rationale in
`transformer/constants.py`). Scores are **ordinal**, not calibrated
probabilities: they order trust; they are not percentages.

## What the sample inputs demonstrate

| File | Nastiness it proves out |
|---|---|
| `recruiters.csv` | duplicate rows, plus-tagged email variant, `"Fern, Alice"` name order, national phone without country code, column-shifted row (contained as `partial`) |
| `ats.json` | foreign field names, conflicting titles/companies vs CSV, in-band `lastUpdated` recency, unknown skill kept + flagged (`canonical: false`) |
| `notes_alice.txt` | free-text extraction: labeled fields, skills scan, "Title at Company since Jun 2021" lines, year-only ranges |
| `notes_two_people.txt` | **multi-identity guard**: a file naming two people is excluded from identity blocking and flagged — the alternative is silently fusing two candidates |
| `garbage.json` / `empty.csv` | truncated JSON is `skipped` with the error in the report; a header-only CSV is `ok` with zero records |

## Assumptions & descopes (stated, not silent)

- **One candidate per unstructured file** — assumed and *guarded*: ≥2 distinct
  strong identifiers in one notes/resume file ⇒ its identity keys are
  withdrawn and the source flagged `multi_identity_source`.
- **No live GitHub/LinkedIn fetching** — network breaks offline determinism;
  LinkedIn has no sanctioned API. Profile URLs found in any source are still
  captured into `links.*`. The adapter registry leaves a slot for a
  recorded-response API adapter.
- **No LLM extraction** — rule-based extractors keep runs deterministic and
  every value traceable to a named method; an LLM extractor would slot in as
  just another Evidence emitter with its own (lower) reliability weight.
- **Notes/resumes contribute a bounded field set** (contacts, links, skills,
  labeled fields, simple experience lines). No NER: a missed value becomes
  `null`, which the problem statement prefers to an invented one.
- **ATS field mappings are fixture-defined** pending real sample files;
  adjusting the declarative map in `adapters/ats_json.py` is the only
  expected change when they arrive.
- **`candidate_id` is content-derived** (hash of the cluster's smallest
  strong identifier). If a later run adds a *stronger* identifier for a
  cluster, its id changes — acceptable for a batch tool, noted here.
- **An empty ATS `to` date means unknown**, not "present": `is_current` is
  only ever asserted by a source, never inferred from absence.
- **Fuzzy/phonetic name matching is out**: a false split is recoverable, a
  false merge silently poisons downstream decisions.

## Repo map

```
transformer/
  models.py       Evidence atom + canonical type map (the spine)
  constants.py    trust/reliability/weight tables, with rationale
  normalize/      NFC text, emails, phones (2-pass E.164), dates ({year,month?}),
                  country ISO-3166, skills alias dict, URLs, idempotent registry
  adapters/       CSV, ATS JSON, notes .txt, resume .docx/.pdf (optional extra)
  identity.py     blocking + union-find, contradiction & multi-identity guards
  merge.py        survivorship, atomic location, interval-union years, phone pass 2
  confidence.py   noisy-OR scoring
  projection/     4-construct path DSL, config compile, projector, schema builder
  pipeline.py     orchestration; cli.py the thin surface
configs/          default.json (identity projection) + recruiter_view.json
samples/          sample inputs (see table above)
out/              committed outputs of the two quickstart commands
tests/            129 tests incl. determinism and gold-output suites
```
