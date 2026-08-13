# UI Design — The Glass-Box Profile Explorer

**Status:** implemented 2026-08-14 (Tier A + identity panel) — React + Vite in `ui/`, Material 3 baseline tokens (light/dark), single-file template inlined by `tools/build_ui.py`, emitted by `--emit-ui`. Engine enablers landed per §6 (locators, confidence traces, UI bundle, gold bytes untouched). Deviations from this plan: the identity graph ships as a cluster panel with key chips + refusal cards rather than an SVG node graph; the live config playground (Tier B/C) and what-if source toggles remain unbuilt — excluded output *is* visible (excluded candidates appear in the batch view with a badge). The linked claude.ai design project was empty at build time, so the token set is Material 3 baseline as requested ("like Material 3"); the built system can be synced into that project on request.
· 2026-08-14 · companion to DESIGN.md (17 ADRs) and GOLDEN_DATASET.md
**Reference pattern:** Landing AI's document-extraction UI — output on one side, and selecting any extracted field highlights the exact region of the source it came from. Grounding, both directions.

---

## 1. Thesis: the UI is a proof artifact, not decoration

The problem statement explicitly deprioritizes UI polish. That is not a reason to skip a UI — it is the design constraint for one: **every pixel must express the engine**. The UI's job is to make the four graded qualities *visible and navigable*:

- **Provenance** → click a value, see exactly where it came from (grounded highlight in the source).
- **Confidence** → every score expands into arithmetic a reviewer can redo on screen.
- **Merge/conflict policy** → the identity graph and the survivorship "tournament" are drawn, not described.
- **Robustness** → skipped garbage, flags, and honest nulls are first-class UI states, not hidden rows in a report file.

The interview line this UI earns: *"I didn't add explainability to the UI — the UI is just the Evidence model rendered. A merge-as-you-go system could not retrofit this screen."* The Evidence-atom architecture (ADR-004) is what makes the whole thing nearly free.

## 2. The core pattern: grounded provenance

Two panes, hard-linked:

```
┌────────────────────────────────────┬──────────────────────────────────────┐
│  SOURCE DOCK (tabs per file)       │  CANONICAL PROFILE                   │
│                                    │                                      │
│  recruiters.csv   [partial ⚠]      │  Avery Stone            ●●●●○ 0.81   │
│  ┌──────────────────────────────┐  │  ✉ avery.stone@example.com  ▸why     │
│  │ name    email        phone   │  │  ☎ +1 415 555 2671         ▸why     │
│  │ Avery.. ▓avery.st..▓ +1 41.. │◀─┼── selected field grounds here        │
│  └──────────────────────────────┘  │                                      │
│  ats.json         [ok]             │  EXPERIENCE                          │
│  notes_p01.txt    [ok]             │  ▓Staff Data Engineer▓ · Marigold    │
│  garbage.json     [skipped ✖ why]  │  2021-02 → present                   │
│                                    │                                      │
├────────────────────────────────────┴──────────────────────────────────────┤
│  EVIDENCE INSPECTOR (docked bottom, opens on selection)                   │
│  full_name = "Avery Stone"   won over: "Fern, Alice" (recruiters.csv#3)   │
│  trust 0.90 × method 1.00 → s=0.90 ─┐                                     │
│  trust 0.85 × method 1.00 → s=0.85 ─┼─ agreement 1−(0.10·0.15) = 0.985    │
│  support 1.75 / 2.20 = 0.795        └─ confidence 0.985 × 0.795 = 0.783   │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Output → source:** clicking any profile field scrolls every contributing source pane to the evidence and highlights *all* spans — winner in solid accent, losing alternatives in a hatched variant. The user literally sees the conflict.
- **Source → output:** clicking any highlighted span in a source pulses the profile field it fed and opens the inspector. Un-highlighted source text is, by definition, text the engine ignored — visible honesty about extraction recall.
- Sources render natively: CSV as a grid, JSON pretty-printed with collapsible nodes, notes/resume as text. A skipped file still gets a tab — showing its error reason *is* the robustness demo.

## 3. Zoom levels (batch → candidate → field → atom)

1. **Batch view** — all candidates as rows: name, confidence sparkbar, source-count chips, flag badges (`multi_identity`, `suspect_shared_identifier`, `soft_key_merge`), dup/refusal indicators. Sortable by confidence — the "who should a recruiter trust least" question answered in one glance.
2. **Candidate view** — the two-pane grounding screen above.
3. **Field view** — the Evidence Inspector: winner, alternatives, per-source strengths, the agreement/support arithmetic, and the survivorship ordering shown as a mini-tournament (trust → method → recency → tiebreak, with the deciding rung highlighted).
4. **Atom view** — the raw span in situ: exact cell / JSON path / character range, method chip (`regex:email_v1`), normalized-vs-raw toggle.

Progressive disclosure everywhere: hover = peek, click = pin, `Esc` walks back up a level.

## 4. Component inventory — and what each one *expresses*

| Component | What it makes visible | Engine feature it sells |
|---|---|---|
| Source dock with status chips | ok / partial / skipped + reason per file | fault boundaries (ADR-013) |
| Grounding highlights | field ↔ raw span, winner vs alternatives | Evidence atoms (ADR-004) |
| Evidence Inspector | the confidence math, expandable, auditable | noisy-OR scoring (ADR-007) |
| Survivorship tournament | *why this value won*, rung by rung | ordering (ADR-006) |
| Identity graph | records as nodes; email/phone/link/soft edges styled by strength; **refused unions as red dashed edges with the guard's reason**; multi-identity sources in a quarantine lane | resolution + guards (ADR-005/017) |
| Config playground | live projection-config editor: toggle fields, remap `from`, switch `on_missing`; load-time errors inline at the offending line; output diff vs default | projection compile step (ADR-011/012) |
| Honest-empty states | null fields say *why* ("phone withheld — no region context ▸raw value") linked to the unparseable entry | never-guess policy |
| Pipeline strip | detect → … → validate with per-stage counts for this run | the architecture itself |
| Determinism chip | output hash displayed; "re-run" reproduces the identical hash live | ADR-016 |
| What-if panel (stretch) | toggle a source off → watch confidences move (never up for corroborators) | metamorphic invariants |

## 5. Everything the user can do

Feed inputs (drop files onto the dock), pick or edit the projection config, set `--as-of` / `--default-region` from a run bar, run, then explore: ground any field, audit any score, walk any cluster, diff any two configs' outputs, export exactly what the CLI writes (`profiles.json` + `run_report.json` — the UI adds nothing the CLI doesn't produce, and says so).

## 6. Engine changes required (small, and each defensible alone)

1. **`Evidence.locator`** — `{kind: "cell"|"jsonpath"|"span", ...}`: row/column for CSV, JSON path for ATS/fixtures, character offsets for notes/resume (the regex extractors already have match spans; today they're thrown away).
2. **Confidence trace** — persist the per-source strengths and agreement/support terms (computed today, then discarded) into an optional `confidence_trace` block.
3. **`--emit-ui` flag** — the CLI writes a single self-contained `explorer.html` with the run's data inlined. The CLI ships its own explainer.
4. **`soft_key_merge` flag** (already on the defect list) so the batch view can badge the weakest merges.

## 7. Architecture: static-first, three delivery tiers

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Static self-contained HTML** (data inlined by `--emit-ui`) | zero install, works from the repo, nothing to break mid-interview, no server to defend | config playground limited to precomputed runs | **Tier A — build this** |
| Thin FastAPI wrapper (`/run` endpoint) | live re-runs: upload + config edits truly interactive | a server to write, secure, and explain | Tier B, optional |
| Pyodide (real engine in-browser) | spectacular "zero install, full engine" story | heavyweight, risky, hard to defend line-by-line | note as considered, rejected |

No framework, or at most a micro-library: a single `explorer.html` with vanilla JS. In a take-home you own every line; 600 lines of readable vanilla beats a build chain.

**Tier A (≈ half day):** static explorer — batch view, grounding, inspector with math, flags, honest-empty states. This alone clears the bar.
**Tier B (≈ +half day):** identity graph (SVG, ~edges from the merge report), config playground against precomputed variant runs, determinism chip.
**Tier C (stretch):** FastAPI live runs with drag-and-drop inputs; what-if source toggles.

## 8. Demo choreography (the 2-minute video, upgraded)

1. **0:00–0:20** — CLI first, deliberately: run both configs in the terminal. *"The problem says CLI is sufficient — here it is. The UI you're about to see is that run report, made navigable."*
2. **0:20–0:50** — open `explorer.html`: batch view → Avery. Click her phone → both sources highlight, including the ATS raw `(415) 555-2671` resolved by pass-2. Expand the math.
3. **0:50–1:20** — click `full_name` on Grace: the losing "Grace N. Obi" alternative highlighted in the CSV, tournament shows why ATS won, confidence visibly penalized vs Avery's.
4. **1:20–1:45** — the edge case: gossip notes file in the quarantine lane of the identity graph, red refused edges on the shared-inbox pair. *"This file names two people — the engine refuses to guess which one it is."*
5. **1:45–2:00** — the config playground reshapes output live; close on the determinism chip: same hash, every run.

## 9. What deliberately stays out (say so in the README)

Auth, persistence, editing profile values by hand (the UI *never* mutates engine output — it would break the provenance contract), mobile layout, dark-mode theming beyond system default, virtualized rendering for >10k candidates (batch view paginates; the engine scales, the demo doesn't need to).

## 10. Build order

1. Engine: locators + confidence trace + `--emit-ui` bundle (tests: locator round-trip, trace matches scores).
2. Tier A explorer against the T1 golden run — the 20 personas are the perfect demo corpus (every UI state has a persona that exercises it: P05 conflicts, P14 quarantine, P04b honest-empty, P19 degenerate dates).
3. Tier B graph + playground.
4. Re-cut the demo video per §8.
