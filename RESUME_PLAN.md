# Resume Handling — Implementation Plan

**Scope:** the six findings from the resume evaluation, closing the two
below-the-bar gaps (untested PDF path, missing education extraction) and the
four cheap recall wins — without breaking the ADR-003 stance: deterministic
rules, precision over recall, misses become honest nulls.
**Date:** 2026-08-14 · **Status: R1–R6 all landed** — minimal-PDF writer + P21 persona (28/24 counts), education + block-experience grammars with their negative tables, DOCX tables, pipe-split names, PDF hygiene; one gold regeneration; 198 tests. One tightening vs. this plan: the education guard requires an institution match outright (year alone insufficient) — "MS Office 2016 certified" forced the stricter rule.

Guiding rule for every new grammar here: **each pattern ships with its
false-positive guard named in advance.** A recall win that invents data would
cost more than it earns.

---

## R1 — Real-PDF fixture + happy-path coverage *(the audit's #2 gap)*

**Mechanism.** A hand-rolled minimal PDF writer — no new dependency — added to
`tools/build_t1_binary_fixtures.py`: PDF 1.4, Helvetica, one content stream per
page (`BT … Tj T* … ET`), correct xref. ~50 lines, ASCII-only content,
multi-page capable (R6 needs two pages). Parens/backslash escaped.

**Fixture.** New golden persona **P21 "The Portable" (Wale Adeyemi)** —
`resume_p21.pdf`, single-column: name line, pipe-separated contact line,
email, one block-form experience (shared surface with R3), education line
(shared with R2), skills line. A **new, self-contained person**: existing
personas' expectations stay untouched; profile counts move 27→28 (default)
and 23→24 (recruiter_view).

**Tests.** Assert-separation keeps failures legible even though the fixture
carries several features: `test_p21_pdf_acquisition` asserts only
status=ok + extracted text + name/email (pure PDF path); the R2/R3 grammars
get their own test functions and their own unit tables. T2's `fake.pdf`
(failure path) stays.

## R2 — Education extractor *(schema promises it; resumes are where it lives)*

**Mechanism** (shared scanner, so notes benefit too): a degree-line grammar —
degree token (`B.Tech|B.E|B.S|B.Sc|M.S|M.Sc|M.Tech|M.Eng|MBA|Ph.D|B.A|M.A…`),
optional `in <Field>` capture, institution as a capitalized run anchored by
comma/at/from or an institution keyword, trailing 4-digit `end_year`. Emits an
education struct with method `regex:education_line_v1` (existing `regex`
reliability family — **no scoring.json change, no checksum ritual**).

**The named false-positive guard:** a bare degree token never fires — the line
must also contain a year OR an institution keyword
(`university|institute|college|school|iit|iim|bits`). This is what keeps
`"Skills: MS Office, Excel"` from becoming an M.S. degree.

**Coverage.** Unit table: "B.Tech in Computer Science, IIT Bombay, 2018" ·
"M.S. Computer Science — Stanford University (2020)" · "MBA, IIM Ahmedabad
2015" · negative: "MS Office, Excel" · negative: "BS detector" prose. Golden
touch: P07's resume gains one education line (its year-only-dates mechanism
untouched; a new assert covers the new line).

## R3 — Block-form experience *(the dominant resume shape)*

**Mechanism** (shared scanner): a two-line pairing rule. Line *i+1* qualifies
as a **pure range line** when `parse_range` matches AND the matched range
spans ≥60% of the line's non-space characters — that dominance threshold is
the guard preventing prose that merely *mentions* dates ("Joined in Jan 2020
after the merger…") from consuming its previous line. Then line *i* is the
header: split on ` — `/` – `/` | `/`,` into two segments; the segment carrying
a company-suffix keyword (`Inc|Ltd|Labs|Systems|Technologies|Analytics|
Studio|Group…`) is the company, else first=company, second=title (a stated
convention — provenance keeps the raw line, so a wrong guess is auditable,
never silent). Method `regex:experience_block_v1`.

**Double-emit guard:** lines consumed by the existing single-line
"Title at Company <range>" pattern are marked and skipped by the block rule.

**Coverage.** Unit table: "Pixelforge — Frontend Lead\nJan 2023 – Present" ·
"Senior Analyst | Helios Retail\n2019 - 2021" · negatives (prose+dates,
range-first ordering). Golden: P21 carries one block entry, asserted in its
own test function.

## R4 — DOCX tables *(five-line fix, top-3 resume pattern)*

`_docx_text` walks `doc.tables` after paragraphs: cells joined with ` | `,
rows with newlines, appended after the paragraph text. Stated limitation:
table text lands *at the end* rather than at its visual position
(python-docx's document order costs an XML walk this plan doesn't buy);
span locators still ground correctly because scanning runs over our own
joined text. Golden touch: P01's resume gains a two-cell skills table
(`Terraform | Airflow`) — its superset-style asserts absorb this without
edits; one new assert pins the table-sourced skill.

## R5 — Contact-line names *(trivial, common)*

Before the first-line name heuristic: split the line on `|`, `·`, `•`, take
the first segment. "Tosin Adeyemi | Frontend Lead" → name from segment one,
locator covering just that segment. Golden touch: P18's resume first line
becomes "Tomas Eder | Frontend Lead" — his existing name assert now proves
the feature.

## R6 — PDF text hygiene *(bounded; two-column stays descoped)*

- **De-hyphenation:** join `(\w)-\n(\w)` only when both sides are lowercase
  letters — heals "Engi-neer" without mangling "co-\nFounder".
- **Repeated header/footer removal:** a line that appears byte-identically on
  every page of a multi-page PDF and is ≤60 chars keeps its first occurrence
  only. Deterministic, conservative, multi-page-only.
- **Explicitly NOT attempted:** two-column layout reconstruction, OCR,
  x-tolerance tuning. Named descope: layout-aware parsing is the ML-extractor
  seat ADR-003 reserved; a heuristic here would be wrong-but-confident about
  *reading order*, the worst place to guess.
- Coverage: a two-page fixture from the R1 writer with a repeated header and
  a hyphen-split word; unit asserts on the cleaned text.

---

## Sequencing

| # | Item | Effort | Depends on |
|---|---|---|---|
| 1 | R1 PDF writer + P21 fixture + acquisition test | ~2h | — |
| 2 | R5 contact-line names (+ P18 fixture touch) | ~30m | — |
| 3 | R4 DOCX tables (+ P01 fixture touch) | ~45m | — |
| 4 | R2 education grammar + unit table (+ P07 touch) | ~1.5h | — |
| 5 | R3 block grammar + unit table (+ P21 content) | ~2h | R1 |
| 6 | R6 hygiene + two-page fixture | ~1h | R1 |
| 7 | **One** gold regeneration; TRUTH.md P21 row + touched-persona notes; aggregate counts 27→28 / 23→24; audit + evaluation docs updated; commit | ~45m | all |

**Non-impacts, stated:** no reference-data changes (new method strings reuse
the `regex` family → no scoring version bump, no checksum ritual); no
identity/merge changes (new evidence flows through existing survivorship);
determinism untouched (all grammars are pure functions of file bytes); the
explorer needs zero changes (new atoms arrive with spans and ground like any
others).

**Success criteria:** PDF happy path exercised in golden CI; `education`
populated from a resume in gold; block-form experience extracted; every new
grammar's negative cases pinned in unit tables; suite green with one
reviewed gold diff.
