# Candidate Data Transformer

Turns messy multi-source candidate data (recruiter CSV, ATS JSON, recruiter
notes, resumes) into one canonical, deduplicated profile per candidate — with
per-field provenance, confidence scores, and a runtime config that reshapes
the output without code changes.

**Live demo (GitHub Pages):** https://mohankrishnagr.github.io/NorthStar/ —
the glass-box explorer preloaded with the 21-persona golden corpus. Click any
profile field to see its evidence highlighted in the source; expand any
confidence score into the arithmetic behind it.

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

python -m pytest -q      # 176 tests incl. golden-persona, hostile, metamorphic, scale suites

# Glass-box explorer UI (React, Material 3) — self-contained HTML, no server:
python -m transformer run --input goldens/t1 --config configs/default.json \
  --out out/_p.json --report out/_r.json --as-of 2026-08 \
  --emit-ui out/explorer.html
# open out/explorer.html in any browser. Rebuild the template after UI edits:
#   cd ui && npm install && cd .. && python tools/build_ui.py

# Interactive workspace (stdlib http.server — zero extra dependencies):
python -m transformer serve
# -> http://127.0.0.1:8765  · upload any of the six source types (csv/json/
#    txt/docx/pdf incl. github_*/linkedin_* recorded payloads), pick or edit
#    the projection config in the UI (load-time errors shown verbatim), set
#    as-of / default-region, run, then explore the grounded result.
#    Tip: without an explicit as-of, the derived default prefers record
#    timestamps (ATS updated_at) over employment-claim dates, so one
#    future-dated claim can't drag "now"; a corpus with no timestamps
#    falls back to claim dates and logs a WARN (ADR-016: still no clock).
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

### Ops (OPS_PLAN.md)

- **Structured logs** on stderr: `--log-format text|json`, `--log-level`
  (default `warning` — a clean run is silent; anomalies like skipped
  sources, refused unions, and soft-key merges are exactly what appears).
  Outputs stay clock-free; telemetry may know what time it is.
- **Versioned reference data**: trust tables live in `transformer/data/scoring.json`
  (inside the package, so the installed wheel is self-contained),
  alias dictionaries carry version headers, and every run report records
  `engine_version` + `scoring_version` + dictionary versions — the complete
  reproducibility pin. Changing reference data is a ritual:
  bump the version, run `tools/update_reference_checksums.py`, regenerate
  gold, review the diff (enforced by `tests/test_reference_data.py`).
- **Container**: `docker compose up --build` → workspace on
  `127.0.0.1:8765` (multi-stage build; non-root; healthcheck).
- **CI** (`.github/workflows/ci.yml`): lint · tests · gold-gate ·
  scale-gate · determinism · ui-freshness · docker smoke · demo artifact —
  each job named for the claim its failure breaks. A **nightly canary**
  re-runs the golden corpus and byte-compares: the golden dataset acting
  as a production monitor.

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
- **The pipeline never fetches URLs** — network breaks offline determinism;
  LinkedIn has no sanctioned API. Profile URLs found in any source are still
  captured into `links.*` (and serve as identity match keys). GitHub's public
  API is exercised at the *recording boundary* instead:
  `python tools/fetch_github.py <profile-url> --out samples` calls it once
  and writes `github_<login>.json`, which the pipeline replays
  deterministically forever.
- **The sample inputs are self-authored.** No official sample files
  accompanied this problem statement, so `samples/` (and the golden corpus)
  were built to its field lists — deliberately nastier than clean demo data.
  If official samples arrive, only the declarative mapping tables in the
  adapters should need adjusting.
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
  adapters/       CSV, ATS JSON, notes .txt, resume .docx/.pdf (optional extra),
                  recorded-response github_*.json / linkedin_*.json (ADR-017)
  identity.py     blocking + union-find (email/phone/profile-URL keys),
                  contradiction & multi-identity guards
  merge.py        survivorship, atomic location, interval-union years, phone pass 2
  confidence.py   noisy-OR scoring
  projection/     4-construct path DSL, config compile, projector, schema builder
  pipeline.py     orchestration; cli.py the thin surface
configs/          default.json (identity projection) + recruiter_view.json
samples/          sample inputs (see table above)
out/              committed outputs of the two quickstart commands
goldens/          golden dataset: t1/ 20 mechanism-named personas across all six
                  source types, t2/ hostile corpus, expected/ pinned outputs,
                  TRUTH.md (per-persona expectations and why — see GOLDEN_DATASET.md)
ui/               React explorer (Material 3 tokens): Landing-AI-style grounding —
                  click any profile field to highlight its evidence in the source,
                  audit the confidence arithmetic, walk the identity cluster.
                  The UI is the Evidence model rendered — it adds nothing the
                  CLI doesn't produce (see UI_DESIGN.md). Built template is
                  committed, so --emit-ui works without Node installed.
tools/            fixture (re)builders + gen_scale.py, the seeded Tier-3 generator
                  with planted ground truth (recall/false-merge/runtime gate)
tests/            171 tests: unit, e2e, determinism, golden personas, hostile
                  corpus, metamorphic invariants, scale gate
```
