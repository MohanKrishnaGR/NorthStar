# Defect-Closure Plan — the four open items

**Scope:** ledger bucket A (future-dated ranges + as-of drag · UTF-16 · gossip
profile marking · dead portfolio bucket). ~3.5 focused hours, one gold
regeneration at the end, one Pages redeploy.
**Date:** 2026-08-14 · **Status: all four landed** — as-of–relative future
discipline with `future_end_clamped`, two-tier derived as-of (T1's derived
default sanitized from 2030-01 to timestamps-tier 2026-06), UTF-16 BOM decode
(T2's fixture now extracts Ute Sechzehn), end-to-end `flags` on profiles and
report clusters (gossip + soft-key labeled in output), and name-aware
portfolio promotion (Avery/Tomas/Alice). One gold regen; 209 tests. Bucket A
is empty. · The named-guard discipline continues: each fix states
its semantic decision *before* code, because three of these four are places
where a sloppy fix would trade one wrong-but-confident for another.

---

## D1 — Future-dated closed ranges + derived as-of drag *(one root, two fixes)*

The root: a clock-free engine (ADR-016) has no notion of "the future" — so
"future" must be *defined relative to as-of*, and the as-of default must not
be movable by the very claims it judges.

**D1a — interval discipline in `_merge_experience`** (as-of–relative):
- Start beyond as-of → interval dropped, existing reason `future_dated_range`
  now covers closed ranges too. Entry still emitted with its stated dates
  (honest display; only the *sum* refuses it).
- Starts in the past, *ends* beyond as-of (a "contract through 2031" claim) →
  **clamp the end to as-of** and count only elapsed months — the same
  semantics open-ended jobs already have — reported under a new reason
  `future_end_clamped`, because a years total that can't be re-derived from
  the visible dates must say why.
- No as-of (a corpus with no dates at all can't reach this code) → guard,
  no clamp.

**D1b — two-tier derived as-of.** Today: max date observed anywhere, so one
future-dated *claim* drags "now" to 2030 (we watched T1 derive `as-of
2030-01` live). Fix: derivation prefers **record timestamps** (ATS
`updated_at` — metadata about *when it was recorded*, not claims about
employment) and falls back to claim-dates only when no timestamps exist.
T1's derived default becomes 2026-06 (sane); the samples corpus is unchanged
(its 2026-05 already comes from `updated_at`). Residual honesty: a
timestamp-free corpus is still claim-driven and thus still draggable —
documented, plus a WARN telemetry event when the derived as-of exceeds every
in-band timestamp. Determinism intact: both tiers are content-derived.

**Coverage:** P19 (Uma) gains one fully-future *closed* range — her `0.1`
years must not move; the clamp case is a `test_merge` unit (persona churn
avoided). Golden runs pin `--as-of` explicitly, so gold moves only where
fixtures do. README's as-of tip updated.

## D2 — UTF-16: decode it, don't grade it "ok"

`read_text` gains a BOM sniff ahead of the existing chain — bytes read once,
then: UTF-16 BOM → `utf-16`; else `utf-8-sig`; else `cp1252`. Deterministic
order preserved; no chardet-style guessing (content sniffing beyond a BOM is
exactly the wrong-but-confident trap).

**Consequence embraced:** T2's `utf16.txt` stops being an "honest miss" and
becomes a *working input* — Ute Sechzehn's name and email now extract, the
hostile-corpus profile count goes 1 → 2, and the T2 test flips from
asserting zero evidence to asserting extraction. GOLDEN_DATASET §5's line
about UTF-16 is updated: the right closure for an honest miss is to stop
missing.

## D3 — Flags travel with the profile (and finish the soft-key story)

The gossip quasi-profile is flagged everywhere *except* the one artifact a
downstream consumer actually reads. Fix: one flags pipeline, end to end —

- `flags: string[]` becomes a canonical profile field (schema refinement the
  problem invites): `merge_cluster` copies the cluster's flags onto the
  profile; `CANONICAL_TYPES` gains `flags`; the default config projects it.
- While the plumbing is open, `soft_key_merge` is **computed as a cluster
  flag** in the pipeline (any `soft:` match key on a multi-record cluster) —
  so the weakest merge kind is now visible in `profiles.json`, the report's
  `merges.clusters` entries, the UI badge, *and* the existing WARN event.
  That retires the last footnote on old defect #1.
- The report's cluster entries gain the same `flags` list (they currently
  carry keys but not flags).

**Non-decision, stated:** the quasi-profile is *marked*, not suppressed —
suppressing would orphan its report entries and hide data that a reviewer
may need to trace; a labeled artifact beats a missing one.

## D4 — `links.portfolio`: earn the bucket instead of deleting it

A context-free URL classifier can't know "personal site," but the **merge
stage has context**: the candidate's name. Reclassification rule, applied to
`links.other` atoms at merge: the URL moves to `portfolio` when any
accent-stripped name token of **≥ 4 characters** is a substring of the
host's *registrable label* (first label only — TLDs like `.dev` are never
matched, so a candidate named "Dev" can't false-positive on every `.dev`
domain). `averystone.dev` (avery), `tomas.dev` (tomas), `alicefern.dev`
(alice) → portfolio; `twitter.com/alice` stays `other` (host label carries
no name token). No name → nothing moves. Provenance re-keys to
`links.portfolio` naturally since it's built at merge.

**Coverage:** golden expectations for Avery/Tomas/Alice move from `other` →
`portfolio` (several assert updates); a negative unit pins the
platform-host case and the short-token guard.

---

## Sequencing & blast radius

| # | Fix | Touches | Gold impact |
|---|---|---|---|
| 1 | D2 BOM decode | `adapters/base.py`, T2 test | T2 asserts only (no pinned bytes) |
| 2 | D1a + D1b | `merge.py`, `pipeline.py`, P19 fixture, unit tests | P19 row only |
| 3 | D3 flags | `models/merge/pipeline`, `configs/default.json`, schema docs | every default profile gains `flags` (broad, mechanical) |
| 4 | D4 portfolio | `merge.py`, unit + golden asserts | 3 personas' links move |
| 5 | **One** gold regen; TRUTH/GOLDEN_DATASET/README touches; suite; emit; commit; push; CI + Pages verify | — | reviewed once |

**Interactions:** D3 and D4 both edit `merge.py` — land D3's plumbing first
so D4's re-keyed provenance rides it. `recruiter_view` (the problem's example
config) is untouched by all four. Reference data untouched — no version
bump, no checksum ritual. The explorer needs zero code changes (batch badges
already read flags; the bundle simply gets them in one more place).

**Definition of done:** ledger bucket A empty; the only remaining opens are
the policy bucket (display names, CJK, recall bounds, named descopes) and
the two hygiene items (LICENSE, dual version declaration) — which are
decisions, not defects.
