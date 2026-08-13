# Implementation Plan — Multi-Source Candidate Data Transformer

**Basis:** DESIGN.md rev 2 (16 ADRs). **Date:** 2026-08-13.
**Principle:** build in dependency order, test each layer before the next consumes it, keep every ADR decision mechanical at coding time — no design thinking mid-implementation.

---

## 1. Repository layout

```
candidate-transformer/
├── README.md                     # run steps, assumptions, descopes, ID-stability note (ADR-016)
├── DESIGN.md                     # this design record
├── pyproject.toml                # deps: phonenumbers, jsonschema (+pytest dev)
│                                 # extras [resume]: pdfplumber, python-docx
│                                 # (pydantic dropped during build: dataclasses +
│                                 #  jsonschema cover models and validation)
├── transformer/
│   ├── __main__.py               # python -m transformer
│   ├── cli.py                    # argparse: run --input --config --out --report
│   │                             #   [--as-of] [--default-region] [--strict]
│   ├── models.py                 # Evidence, SourceRecord, canonical type map
│   ├── constants.py              # trust table, method table, core-field weights (ADR-006/007)
│   ├── normalize/
│   │   ├── text.py               # NFC + casefold intake (ADR-016)
│   │   ├── emails.py             # + matching-key variant (plus-tags, gmail dots)
│   │   ├── phones.py             # pass-1/pass-2 entry points (ADR-009)
│   │   ├── dates.py              # {year, month|null} grammar (ADR-008)
│   │   ├── country.py            # alias table → ISO-3166 alpha-2
│   │   ├── skills.py             # fold + alias dict (ADR-010)
│   │   ├── urls.py               # link classification (linkedin/github/portfolio/other)
│   │   └── registry.py           # name → normalizer; all idempotent (ADR-012)
│   ├── adapters/
│   │   ├── base.py               # detect() contract, fault boundary, SourceReport (ADR-013)
│   │   ├── recruiter_csv.py      # row = candidate; dateless is_current experience
│   │   ├── ats_json.py           # declarative field-mapping table
│   │   ├── notes_txt.py          # regex/dict/date-grammar extractors
│   │   └── resume.py             # M7 stretch; reuses notes extractors
│   ├── identity.py               # blocking, union-find, canonical order, guards (ADR-005)
│   ├── merge.py                  # survivorship + phone pass 2 + as-of intervals (ADR-006/009)
│   ├── confidence.py             # noisy-OR + support; set-element rule (ADR-007)
│   ├── projection/
│   │   ├── paths.py              # 4-construct DSL (ADR-011)
│   │   ├── config.py             # load-time validation: paths, types, normalizers
│   │   ├── project.py            # resolve → normalize → on_missing → type-check (ADR-012)
│   │   └── schema.py             # config → JSON Schema; output validation
│   └── report.py                 # run report assembly; pinned JSON writer (ADR-016)
├── configs/
│   ├── default.json              # identity projection of canonical schema
│   └── recruiter_view.json       # the problem statement's example config
├── data/
│   ├── skill_aliases.json
│   └── country_aliases.json
├── samples/                      # official sample inputs when provided; own fixtures until then
├── out/                          # produced outputs — committed (a required deliverable)
└── tests/
    ├── test_normalizers.py … test_e2e_gold.py   (one file per layer, §4)
    └── fixtures/  gold/
```

---

## 2. Build order — milestones with definition of done

Dependency logic: models before everything; normalizers before adapters (adapters emit pass-1-normalized Evidence); identity before merge; projection is independent of stages 1–6 and comes after so it can be tested against real canonical records; CLI last because it is only wiring.

| # | Milestone | Contents | Done when | Est. |
|---|---|---|---|---|
| M0 | Scaffold & models | pyproject, package skeleton, `Evidence`/`CanonicalProfile`/`RunReport`, constants tables, canonical evidence sort key (§3.1) | `pytest` runs green on an empty test; models round-trip JSON | 1h |
| M1 | Normalizers | all of `normalize/`, alias data files | table-driven tests pass: phones (±CC, junk, extensions), all date grammar forms + ambiguous `03/04/2021`, country aliases, skill folds, NFC/casefold, email matching-keys | 2h |
| M2 | Adapters ×3 | base contract + CSV, ATS JSON, notes; detection registry; fault boundaries; own nasty fixtures (§5) | each adapter turns its fixture into expected Evidence atoms; garbage fixtures yield `skipped`/`partial` without a crash | 2h |
| M3 | Identity resolution | blocking keys, union-find with canonical union order, contradiction guard (all-members check, name predicate), multi-identity guard | unit tests: email/phone/soft-key merges; transitive A–B–C refusal; two-people notes file attaches to nothing; refusals identical under shuffled input | 2h |
| M4 | Merge + confidence | survivorship (scalars, atomic location, ordered sets, experience/education sub-merge), years_experience with `as-of`, phone pass 2, confidence math | hand-computed confidence fixtures match to 6 decimals; location chimera impossible by construction; promotion stays two entries | 2.5h |
| M5 | Projection & validation | path DSL, config load-time validation, projector, schema generation, output validation | `on_missing` × `required` matrix passes; `emials[0]` rejected at load; empty array ≠ missing; provenance/confidence re-keyed to output names | 2h |
| M6 | CLI, report, E2E | wiring, pinned JSON writer, run report; run both configs on samples; commit `out/` | both configs produce schema-valid output; determinism suite green (§4); exit codes 0/2 as specified | 1.5h |
| M7 | Stretch | resume adapter (pdfplumber/python-docx → notes extractors); gold-profile test | resume fixture merges into the right cluster; gold byte-compare green | 2h |
| M8 | Deliverables | README, one-pager PDF distilled from DESIGN.md §8 pointers, demo video (§6), repo polish | submission checklist §7 fully ticked | 2h |

Total ≈ 15h; M7 is the designated cut if time compresses (M0–M6 + M8 is a complete, compliant submission).

---

## 3. Implementation notes — decisions made mechanical

Pinning the fiddly parts now so coding never re-opens design questions:

**3.1 Canonical evidence sort key** (ADR-004/016): `(field_path, normalized_value_repr, source_type, source_id, order_index, method)`. Defined once in `models.py`, used everywhere a pool is ordered. `normalized_value_repr` = `json.dumps(value, sort_keys=True, ensure_ascii=False)` so unlike types sort stably.

**3.2 Union-find**: plain dict parent-pointer with path compression; **no union-by-rank** — the representative must be deterministic, so the root is always the lexicographically smallest member id. Union operations pre-sorted by `(key_strength, key_value, source_id)` before applying (ADR-005).

**3.3 Phone pass 2 lives inside merge** (ADR-009): after location survivorship resolves a cluster's country, re-run `phones.normalize(raw, region=cluster_country)` over the cluster's leftover raw phones; successes append Evidence with `method: "phones:pass2_region"` and re-sort the set by G1 ordering. No new blocking keys are derived from pass-2 results.

**3.4 Pinned JSON writer** (`report.py`): `json.dump(obj, f, ensure_ascii=False, sort_keys=True, separators=(",", ": "), indent=2)` to a file opened `newline="\n", encoding="utf-8"`. Every output file goes through this one function — byte-identity on Windows depends on it.

**3.5 as-of derivation** (ADR-016): during extraction, track `max_date_seen` across all parsed dates; `as_of = args.as_of or max_date_seen`; if neither exists (no dates anywhere), `years_experience` stays null rather than inventing a clock. Recorded in `run_report.run.as_of`.

**3.6 Config load = compile step**: `config.py` resolves every `from` path against a hand-declared static map of canonical paths → types (`models.CANONICAL_TYPES`), then checks type + normalizer compatibility (ADR-011). Errors collect and report *all at once* (a config author fixes one list, not one error per run), then exit 2.

**3.7 `--strict` flag** (ADR-013): fault boundaries re-raise instead of containing — for development only; never used in documented run steps.

**3.8 Trust/method tables** (`constants.py`): module-level frozen dicts with a comment block explaining each value's rationale — they will be read aloud in the interview; write them to be read.

---

## 4. Test plan → edge-case traceability

Every §5 edge-case row in DESIGN.md gets at least one test; the mapping is explicit so coverage gaps are visible:

| Test file | Covers | DESIGN §5 rows |
|---|---|---|
| `test_normalizers.py` | date grammar incl. ambiguity, phone junk, country aliases, skill folds, NFC | 6, 7, 12 |
| `test_identity.py` | key merges, transitive guard, multi-identity, name predicate table, shuffled-order refusal stability | 4, 10 |
| `test_merge.py` | survivorship ordering, atomic location, set ordering (`emails[0]`), promotion append, interval union, as-of closing | 1, 5, 11, 13, 14 |
| `test_confidence.py` | hand-computed noisy-OR/support cases, set-element rule, per-source dedupe | 1, 9 |
| `test_projection.py` | 4 path constructs, `on_missing`×`required`, load-time rejections, empty-array, normalize-failure, re-keying | 8, 15 |
| `test_determinism.py` | run twice; shuffled file order; `os.utime`-touched mtimes; two fake `--as-of` values differ *only* in current-job durations | (N1 as a whole) |
| `test_e2e_gold.py` | full run on fixtures vs committed gold outputs, byte-compare; garbage-source run exits 0 | 3 |

---

## 5. Fixture strategy (official samples not yet in hand)

Build own fixtures **now**, shaped exactly by the problem statement's field lists — then when official samples arrive, they drop into `samples/` and only the ATS mapping table and CSV header mapping should need touching (isolated by ADR-002's adapter design). Fixture set, one file per planned nastiness:

- `recruiters.csv` — 4 candidates; one row with national-format phone, one with `LASTNAME, First` name order, one duplicate row, one malformed row (column shift)
- `ats.json` — 3 candidates overlapping the CSV via email; foreign field names; one conflicting title + phone in different format (same person); in-band `updated_at`
- `notes_alice.txt` — prose with email, `+CC` phone, skills incl. one unknown, "Jan 2020 – Present"
- `notes_two_people.txt` — two distinct emails → must trigger the multi-identity guard
- `garbage.json` — truncated JSON; `empty.csv` — header only
- `resume_alice.docx` (M7) — overlapping + conflicting data vs CSV

Gold outputs regenerate via a `make gold` / documented command, reviewed by eye before committing — a gold file nobody read is a tautology, not a test.

---

## 6. Demo video script (≈2 min, storyboard)

1. **0:00–0:20** — repo tree + one-liner of the pipeline; point at DESIGN.md.
2. **0:20–0:50** — run default config on samples; open `profiles.json`; show one field's provenance + alternatives ("the CSV said X, the ATS said Y, here's why Y won and what it did to confidence").
3. **0:50–1:15** — run `recruiter_view.json`; diff the two outputs; show a load-time config-typo rejection (fast, visual).
4. **1:15–1:45** — edge case: `notes_two_people.txt` → run report's `multi_identity_source` flag; explain the transitive-fusion risk it prevents.
5. **1:45–2:00** — design decision I'm proud of: Evidence-first model — provenance isn't logged, it's the data structure.

## 7. Submission checklist (Step 2 requirements → artifacts)

- [ ] End-to-end on sample inputs; schema-valid JSON — default **and** ≥1 custom config (M6)
- [ ] ≥2 source types, one per group — CSV + ATS + notes (M2)
- [ ] Dates/phones normalized; skills canonicalized (M1)
- [ ] Merge with provenance + confidence populated (M4)
- [ ] Output validated; graceful degradation on garbage (M5/M2)
- [ ] CLI surface + README run steps (M6/M8)
- [ ] Tests incl. edge cases (M1–M7); produced outputs committed in `out/` (M6)
- [ ] Assumptions & descopes section in README (M8)
- [ ] One-pager PDF `<FullName>_<Email>_Eightfold.pdf` distilled per DESIGN.md §8 (M8)
- [ ] ~2 min demo video per §6 (M8)

## 8. Sequencing risks

- **Sample inputs arriving late** — mitigated by §5; budget 30 min of adapter-mapping adjustments when they land.
- **`phonenumbers`/`pdfplumber` install friction on Windows** — both are pure-python wheels; resume extras are optional (`pip install .[resume]`) so M0–M6 never depends on them.
- **Time compression** — cut order: M7 resume adapter first, then gold test (keep the determinism suite — it guards the headline claim), never the run report.
