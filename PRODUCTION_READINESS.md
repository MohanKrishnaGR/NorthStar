# Production-Readiness & Platform-Integration Assessment

**Subject:** candidate-transformer (engine + golden dataset + explorer UI, 181 tests)
**Question 1:** is this production-ready? **Question 2:** what would it take to run it as a service inside the Eightfold platform?
**Date:** 2026-08-14 · honest by construction — this document is the take-home's own risk register.

---

## 1. Verdict up front

**As a service today: no — and deliberately.** It is a single-machine batch engine with a demo surface; it has no persistence, no tenancy, no incremental processing, and its interactive mode is explicitly a localhost demo.

**As an engine core to *build* the service around: unusually ready.** The three properties production data platforms retrofit at great pain — pure-function merging over an immutable evidence log, per-value provenance, and regression gates with planted ground truth — are already the architecture, not aspirations. The honest summary for an interviewer: *the seams are in the right places; the service hardening is real but mechanical; nothing structural has to be undone.*

## 2. Scorecard

| Dimension | State | Evidence |
|---|---|---|
| Correctness engineering | **Strong** | 181 tests; byte-pinned gold; metamorphic invariants; seeded scale gate (planted recall 1.0, zero false merges) |
| Determinism / reproducibility | **Strong** | no clock, no fs-metadata, content-derived ids, byte-identical reruns under shuffle/mtime perturbation |
| Explainability | **Strong** | Evidence atoms, per-field provenance + alternatives, auditable confidence arithmetic, grounded UI |
| Extension seams | **Strong** | adapter registry, declarative mappings, projection configs, versioned method strings |
| Robustness (file-level) | **Strong** | hostile corpus: every garbage shape degrades to a named report entry |
| Persistence | **Absent** | everything is in-memory per run; no evidence store, no profile store, no run history |
| Incremental processing | **Absent** | every run re-merges the world; no retraction, no cluster maintenance, no GDPR-erasure path |
| Scale | **Bounded** | comfortable at 10⁴ single-machine; Eightfold operates at 10⁷–10⁸ profiles — needs sharded identity resolution |
| Security / tenancy | **Absent** | no authn/authz, no tenant isolation, PII in plaintext, `serve` is localhost-demo only |
| Observability | **Adequate (demo-scale)** — was *Weak* | structured JSON/text event logs derived from the report taxonomy; output-hash in `run_completed`; nightly determinism canary in CI; metrics/tracing backends remain blueprint (OPS_PLAN §1.2–1.3) |
| Ops / packaging | **Adequate (demo-scale)** — was *Absent* | multi-stage container + compose; 8-job CI (lint/tests/gold/scale/determinism/ui-freshness/docker-smoke/demo) + nightly canary; reference data versioned+checksummed with versions pinned in every run report; deploy shapes remain blueprint (OPS_PLAN §2.5) |
| Extraction quality at real-world variance | **Honest but low-recall** | rule-based by design; production resume/notes parsing needs the ML extractor slot ADR-003 reserved |

## 3. What transfers as-is (the assets)

1. **The evidence-log architecture.** Profiles are already a *pure materialized view* of an append-only evidence pool. That is exactly the shape a platform service wants: the evidence store becomes the system of record; profiles re-materialize on demand. GDPR right-to-erasure — hard in merge-as-you-go systems — reduces here to "tombstone the evidence, re-derive the view."
2. **Determinism as reproducibility.** In production this becomes: every materialization pinned to (engine version, trust-table version, dictionary version, as-of). Same guarantee, now versioned — an audit answer, not just a test trick.
3. **The compliance posture.** Hiring tech is regulated territory (NYC Local Law 144, EU AI Act high-risk class). Per-value provenance, visible alternatives, auditable scores, and never-guess normalization are *the* properties auditors ask for, and here they are load-bearing rather than bolted on.
4. **The golden-dataset discipline.** T1 personas + truth sheet + metamorphic suite + planted-truth generator convert directly into a CI quality gate for connector and model changes — most production pipelines never get this.
5. **The projection layer.** Runtime configs with compile-step validation are already the right shape for per-consumer/per-tenant output contracts.

## 4. The gap inventory (what "productionize" actually means)

**Tier 1 — hours-to-days (mechanical):**
- Containerize; CI workflow running the full suite incl. gold + scale gates; structured logging (the run report already enumerates the events worth logging); close the 4 open ledger defects; version the trust tables and alias dictionaries as reviewed reference data instead of code constants.

**Tier 2 — weeks (the real service work):**
- **Evidence store** (append-only, per-tenant, tombstones) + profile store as materialized views; idempotent re-ingestion.
- **Incremental identity resolution:** new evidence touches only clusters sharing its match keys; retraction may *split* clusters — the hard case union-find alone doesn't handle; needs a re-cluster-affected-partition routine (the deterministic pure merge makes this safe to re-run, which is the saving grace).
- **AuthN/Z + tenancy;** encrypt at rest; access audit log. Kill the data-inlined `explorer.html` for real PII — a self-contained HTML file full of candidate data is a leak vector; the explorer must read from an authorized API instead (the serve-mode split already points there).
- **API surface:** the stdlib demo server is replaced by a real service (the `/api/run` contract and compile-step config validation carry over unchanged).
- **Observability:** metrics on merge rates, refusal rates, unparseable rates per connector — the report fields *are* the metric catalog.

**Tier 3 — months (platform-scale):**
- **Sharded resolution at 10⁸:** strong-key sharding is natural (hash email/phone/link keys); soft-key blocking across shards and cross-shard contradiction guards are genuine distributed-systems work.
- **Connector breadth:** real Workday/Greenhouse/SAP payloads are messier than any fixture; the declarative mapping seam is right, but each connector is owned, tested surface — the golden-persona pattern becomes per-connector contract tests.
- **ML extraction integration:** slot the platform's resume/notes parsers in as high-recall, lower-reliability Evidence emitters beside the deterministic rules (ADR-003 reserved exactly this seat, with recorded outputs preserving replayability).
- **i18n at global scale:** script-aware name compatibility (the documented CJK false-split), transliteration matching, locale-aware date rules.

## 5. Where it would sit in the Eightfold platform

Realistically not a standalone product — Eightfold already ingests, enriches, and deduplicates profiles. The defensible integration story is a **merge/provenance/confidence layer** inside the ingestion path:

```
connectors (existing) ──► evidence store (this engine's model)
                             │  incremental identity resolution + guards
                             ▼
                    canonical profiles (materialized views)
                             │  projection configs per consumer
                             ▼
        search/matching · analytics · compliance/audit UI ("why this value")
```

Its differentiated imports are (a) the evidence/provenance/confidence data model, (b) the refusal-over-guess identity guards, and (c) the golden-dataset CI gate — all three are upgrades to any pipeline that currently merges destructively. The explorer becomes the "explain this profile" panel that recruiters and auditors both get.

## 6. The three questions to ask before committing the roadmap

1. **Retraction semantics:** when a source is deleted, do downstream consumers see profiles *shrink*? (The architecture supports it; the product decision is non-trivial.)
2. **Confidence contract:** scores shift when trust tables or extractors change — do consumers get pinned scoring versions, or live drift with change logs?
3. **Where does ML sit in trust?** A learned extractor's reliability is not a constant; per-field calibration data would replace the hand-set method table — the arithmetic stays auditable either way.

## 7. Bottom line

- **Ship today:** as an embedded library/batch stage behind an existing service boundary — yes, after Tier 1.
- **Run as a tenant-facing service:** after Tier 2 (~weeks of focused work), with Tier 3 as the scale roadmap.
- **The interview claim this supports:** not "it's production-ready" but the stronger, truer one — *"every production requirement lands on a seam this design already cut, and I can show you the seam."*
