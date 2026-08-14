# Golden Dataset Design — Candidate Data Transformer

**Purpose:** a fixture corpus + pinned outputs that (a) exercises every pipeline
mechanism at least once, (b) localizes failures — a gold diff should *name* the
broken mechanism, not just say "something changed", and (c) resembles real-world
mess in its proportions, not just its pathologies.
**Status:** implemented 2026-08-13 — `goldens/` (T1 personas + T2 hostile corpus + pinned expected outputs + TRUTH.md), `tools/gen_scale.py` (T3), tests `test_golden_t1/t2.py`, `test_metamorphic.py`, `test_scale.py`. One deviation from §6: the machine-readable truth twin is `tests/test_golden_t1.py` itself — one test per persona, named after it, so a failing test names the broken mechanism directly.

---

## 1. Principles

1. **One mechanism per persona.** Every synthetic person embodies exactly one
   primary nastiness (plus benign variation). When the gold diff shows "The
   Regionless" changed, you know phone pass-2 broke — no debugging safari.
2. **Negative controls are half the dataset.** People who must *not* merge are
   as load-bearing as people who must. A dedup system tested only on positives
   will happily fuse the universe.
3. **Gold pins bytes; the truth sheet pins meaning.** Byte-compare catches any
   drift; a human-readable truth sheet (expected clusters, winners, flags, and
   *why*) makes the gold reviewable. A gold file nobody can explain is a
   tautology, not a test.
4. **Assert relative confidence, not absolute.** Absolute scores are brittle to
   trust-table tuning. The truth sheet asserts *orderings* ("corroborated email
   outranks solo email"); the gold bytes pin the exact numbers as a changelog.
5. **No real people.** Reserved domains (`example.com`, `.test`),
   libphonenumber-valid-but-fictional numbers, invented companies. A take-home
   dataset with a real person's scrapeable identity is a liability.
6. **Normal cases dominate.** Roughly 60% of personas are boring. Aggregate
   behaviors (set ordering, overall-confidence spread, output sorting) only
   get tested when clean data outnumbers the freak show.

## 2. Three-tier architecture

| Tier | Contents | Asserts | Size |
|---|---|---|---|
| **T1 Personas** | ~20 handcrafted people across ~14 files, all 6 source types | full gold byte-compare + truth sheet | small, human-reviewable |
| **T2 Hostile corpus** | file-level garbage that must degrade gracefully | report statuses/reasons only — no profiles expected | ~10 files |
| **T3 Scale batch** | seeded generator → 5,000 candidates, planted ground truth | cluster precision/recall on planted cases, runtime budget, byte-identical rerun at scale | generated, not committed raw |

---

## 3. Stratification matrix

Each T1 persona is a cell in this matrix; the roster in §4 covers every row at
least once.

**A. Source-presence patterns** — all six; structured-only; unstructured-only;
single-source (each type once); disjoint pairs bridged by exactly one key kind.

**B. Match-key topology** — email-only overlap; phone-only; email+phone;
transitive chain A–B–C; soft-key only; singleton (no keys); shared-identifier
contradiction (email kind AND phone kind); multi-identity source; plus-tag /
gmail-dot variants that must still key together.

**C. Conflict types per field** — agreement; benign variant (case, accents,
punctuation, "Sr."/"Senior"); true conflict (different employer); one-sided
absence. All four must appear for at least: name, title, company, location,
linkedin URL.

**D. Format variance** (per-source mess catalog in §5).

**E. Duplication** — exact duplicate row; near-duplicate row (one field
drifted); same person 5+ records; 3 people inside one ATS blob.

**F. Projection strata** — a persona that survives the default config but is
excluded by the example config (`required` email missing); empty arrays vs
nulls; a value that fails per-field normalize at projection time.

**G. Confidence strata** — ceiling (all sources agree), floor (notes-only),
contradiction penalty visible, method-tier separation (labeled vs scanned from
the same file).

## 4. Persona roster (Tier 1)

| # | Persona | Mechanism under test | Sources |
|---|---|---|---|
| 1 | **The Baseline** | clean agreement everywhere; confidence ceiling anchor | all 6 |
| 2 | **The Tagged** | `x+tag@gmail`, `x.y@googlemail` variants → one cluster; originals preserved in output | CSV, ATS, notes |
| 3 | **The Reordered** | "LASTNAME, First", "M. Krishna" initials, José in NFD bytes | CSV, resume |
| 4 | **The Regionless** | national phone, no `+CC`; variant 4b has *no location either* → phone stays out, reported | CSV, ATS |
| 5 | **The Conflicted** | employer/title disagree across 3 sources; alternatives + support penalty visible | CSV, ATS, resume |
| 6 | **The Promoted** | same company, sequential titles + overlapping stint; "Present"; no double-count | ATS, LinkedIn-fixture |
| 7 | **The Year-Only** | every date year-only or ambiguous `03/04/2021`; YYYY rendering; upper-bound years | resume, notes |
| 8 | **The Stated Liar** | claims 15y, ranges derive 5.3y → derived wins, claim in alternatives | ATS |
| 9 | **The Twins A** | same name + company, *different* emails → two clusters (negative control) | CSV, ATS |
| 10 | **The Twins B** | same name + company, *no* strong keys → soft key merges them — the documented false-merge boundary, deliberately visible in gold | CSV ×2 |
| 11 | **The Shared Inbox** | one referral email, two names → refusal, `suspect_shared_identifier` | CSV, ATS |
| 12 | **The Switchboard** | same office phone, two candidates → refusal via the *phone* key kind | CSV, ATS |
| 13 | **The Chain / Broken Chain** | A–B email, B–C phone: compatible → 3-record cluster; variant with incompatible C → refusal | CSV, ATS, notes |
| 14 | **The Gossip File** | notes naming 3 people → `multi_identity_source`, attaches to no one, own non-colliding id | notes |
| 15 | **The Ghost** | notes-only, no email → floor confidence; excluded by example config (projection stratum F) | notes |
| 16 | **The Polyglot** | CJK name spaced two ways, Devanagari skills, `+81` phone | ATS, resume |
| 17 | **The Hoarder** | 30 skills: aliases, "Python 3.11", unknowns, prose with "go over the rest" bait | ATS, notes, GitHub-fixture |
| 18 | **The URL Collector** | two different LinkedIn slugs (conflict), GitHub URL in resume prose, portfolio with tracking params | resume, notes, ATS |
| 19 | **The Time Traveler** | start 2030; end-before-start range; zero-length job | ATS |
| 20 | **The Encoding Victim** | cp1252 é bytes, BOM'd CSV, smart quotes in notes | CSV, notes |

**GitHub/LinkedIn representation.** Live fetch stays descoped (ADR-002), so
these enter as **recorded-response fixtures**: `github_<login>.json` (REST
user + languages payload) and `linkedin_<slug>.json` (export-style profile).
Dataset must include: GitHub `name: null` (login must not be promoted to
full_name); repo languages feeding skills at *low* trust that must **not**
outvote a resume's explicit skills; a LinkedIn headline conflicting with ATS
designation (trust ordering visible).

## 5. Per-source mess catalog

**CSV** — BOM; cp1252; duplicate header column; shifted row; quoted commas in
names; two emails in one cell; phone with `ext. 22`; `"—"` and `"N/A"` as
null-markers (must become null, not the string); trailing blank lines; a
100-char name.

**ATS JSON** — bare object; array; `{"candidates": []}`; unknown extra keys;
`null` vs missing key vs `""` (three different absences, one behavior);
number-typed phone (`9876543210` as JSON int); date fields mixing
`"2021-06"`, `"Jun 2021"`, epoch millis (unparseable → null + report);
skills as comma-joined string instead of array; nested `location: {}` empty
object; duplicated candidate entry (same person twice inside the blob).

**Notes** — labeled and prose-only variants; "Title at Company since X" and
"Company (X - Y)" shapes; a sentence where a year range looks like a phone;
URL mid-sentence with trailing punctuation; skill-bait prose ("we go over the
rest of the spring plan"); emoji; a note that is one 400-character line.

**Resume** — DOCX happy path; PDF whose extraction reorders two columns
(experience lines interleaved — extractor must not invent a merged line);
image-only PDF (skipped + reason); password-protected PDF (skipped + reason);
"Curriculum Vitae" as first line (name heuristic must decline); resume with a
skills table (DOCX tables are currently unread — honest miss, visible in truth
sheet).

**Tier 2 hostile corpus** — truncated JSON; zero-byte file; `.csv` containing
JSON; `.json` containing HTML (an error page saved by mistake); 50MB single-line
text file (runtime guard); file with no extension; UTF-16 file (originally an
"honest miss" — since DEFECTS_PLAN D2 the BOM is sniffed and the file *works*,
which is the right closure for an honest miss); directory named `resume.pdf`.

## 6. Truth sheet + assertion strategy

`goldens/TRUTH.md`, one block per persona:

```
### The Conflicted (P05)
clusters:   [p05.csv#row=2, ats.json#idx=4, resume_p05.docx#file]  (email key)
id seed:    email:conflicted@example.com
winners:    title <- ats.json (trust 0.90) | alternatives: ["Sr. Analyst (csv)", "Analyst (resume)"]
flags:      none
confidence: full_name(P05) < full_name(P01 Baseline)      # contradiction penalty
            emails[0] conf > phones[0] conf                # corroboration count
```

Assertion layers, cheapest first:
1. **Byte gold** — full default-config + example-config outputs (regression).
2. **Truth-sheet structural asserts** — pytest reads a machine-readable
   `truth.json` twin: cluster memberships, flags, id-seed kinds, winner
   sources, relative-confidence inequalities.
3. **Report asserts** — every T2 file's `status` + first error reason;
   `unparseable` reasons exactly named.
4. **Metamorphic asserts** (dataset-wide, no gold needed): shuffling files
   changes nothing; deleting a *corroborating* source never raises any
   confidence; deleting a *contradicting* source never lowers the winner's
   confidence; adding an empty file changes nothing but the report.

## 7. Tier 3: seeded scale generator

`tools/gen_scale.py --n 5000 --seed 7` emits a CSV (all n), an ATS blob
(60% overlap), notes files (5%), plus `manifest.json` ground truth.

Planted structure (all rates parameterized):
- 70% clean singletons · 18% two-source duplicates via email · 6% via phone ·
  3% three-source chains · 2% conflicts (title/company) · 1% pathological
  (shared inboxes, multi-identity notes, twins).
- **Metrics gate:** planted strong-key duplicate recall = 1.0; false-merge
  count on planted near-miss pairs = 0; soft-key merges reported, compared
  against the known twins rate (documented behavior, not hidden).
- **Non-functional gate:** wall-clock budget (e.g. < 60s at n=5000), memory
  sanity, and byte-identical rerun at scale — determinism bugs love to hide
  behind hash-order at volume.
- Manifest, not the 5k files, is committed; CI regenerates from the seed.

## 8. Discoveries this exercise feeds back into the code

Designing the dataset surfaced concrete gaps — pre-req fixes before the gold
is pinned, plus DESIGN §5 rows 16+:

1. **Inverted ranges (The Time Traveler).** An end-before-start range currently
   contributes a *negative* month count to `years_experience` and confuses
   overlap checks. Fix: drop inverted intervals, report
   `inverted_date_range`. Future-dated starts: cap at as-of (report), else
   years go negative relative to as-of.
2. **Misleading unparseable reason.** A `+CC` number that is *invalid* (fails
   `is_valid_number`) currently falls through to reason `no_region_context`
   — wrong diagnosis. Split reasons: `invalid_number` vs `no_region_context`.
3. **CJK name spacing (The Polyglot).** `"田中太郎"` vs `"田中 太郎"`
   tokenizes to non-overlapping token sets → contradiction guard refuses →
   false split. Conservative per the north star, but must be a *visible,
   documented* behavior in the truth sheet; a fix (script-aware substring
   compatibility) is a scoped follow-up.
4. **Null-marker strings** (`"N/A"`, `"—"`, `"-"`): adapters currently pass
   them through as values. Needs a shared null-marker set at intake.
5. **ATS numeric phone** (JSON int): `str()` coercion exists but deserves an
   explicit fixture so it never regresses.
6. **candidate_id collision on refusal-split clusters** *(found while building
   T1)*: two clusters split by the contradiction guard share the contested
   identifier — both would hash it into the *same* candidate_id (The Shared
   Inbox, the CJK pair). Fixed: identifiers involved in a refusal are excluded
   from id seeding; such clusters fall back to name+company or record seeds.
7. **Recorded API payloads were unjoinable** *(found while building T1)*:
   GitHub/LinkedIn fixtures carry no email/phone, so every one became an
   orphan profile. Fixed by ADR-017: `links.github`/`links.linkedin` URLs are
   now a third match-key kind, guard-protected like emails and phones.

## 9. Build order

1. Fixes from §8 (1, 2, 4 are small; 3 documented-only for now).
2. T1 personas + truth sheet; pin gold; wire structural asserts.
3. T2 hostile corpus + report asserts.
4. Metamorphic suite (cheap, high value).
5. T3 generator + manifest metrics + perf gate.

When Eightfold's real sample inputs arrive they become **T0** — run first,
diffed against expectations, and any surprise becomes a new persona. The
golden dataset is how the system earns the claim "handles messy real-world
inputs" *before* meeting them.
