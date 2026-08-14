# Observability & Ops Plan

**Targets:** the two weakest PRODUCTION_READINESS scorecard rows — Observability (*weak*) and Ops/packaging (*absent*).
**Date:** 2026-08-14 · **Status: items 1–4 landed** (versioned reference data + report pins + checksum ritual; structured logging with the full event taxonomy incl. `soft_key_merge`; multi-stage Dockerfile + compose + `--host`; 8-job CI + nightly canary; ruff gate). Items 5–6 remain seam/blueprint as planned.

Two principles shape everything below:

1. **The run report is already the telemetry schema.** Every anomaly the engine can detect is already a named field: source statuses, refusals, flags, unparseable reasons, validation exclusions. Observability here is *wiring*, not instrumentation design — logs, metrics, and alerts are all derived views of the report.
2. **Outputs stay clock-free; telemetry may know what time it is.** ADR-016 bans the clock from anything that shapes `profiles.json`. Logs, spans, and durations are not outputs — run_ids, timestamps, and latencies live in telemetry without touching the determinism contract.

---

## 1. Observability

### 1.1 Structured logging — *land now*

Stdlib `logging` with a JSON formatter (zero new dependencies), `--log-format json|text` (text default for CLI humans, json default under `serve`). One `run_id` (uuid) stamped on every record; `serve` adds a `request_id`.

Event taxonomy, derived 1:1 from existing report fields:

| Event | Level | Payload (beyond run_id) |
|---|---|---|
| `run_started` | INFO | config hash, as_of, default_region, engine+scoring versions |
| `source_processed` | INFO / WARN if `partial`·`skipped` | source_id, source_type, status, records, evidence, duration_ms, first error |
| `union_refused` | WARN | key kind, record ids — the fusion guard firing is always worth a line |
| `multi_identity_flagged` | WARN | source_id |
| `soft_key_merge` | WARN | cluster id, size (closes ledger defect #1 as a side effect) |
| `profile_excluded` | INFO | candidate_id, field, problem |
| `unparseable` | DEBUG, sampled | field, reason (counts go to metrics; individual lines are noise) |
| `run_completed` | INFO | profiles, clusters, refusals, duration_ms, output hash |

The output hash in `run_completed` is the determinism canary's hook (§1.4).

### 1.2 Metrics — seam now, backend blueprint

A tiny internal `metrics.py` collecting counters/histograms in-process, emitted at run end: batch pushes once (OTLP/Pushgateway-shaped), `serve` exposes `/api/metrics`. OpenTelemetry as the transport-neutral choice, wrapped so the core has no hard dependency (optional extra `[obs]`, no-op otherwise).

Catalog (name → what it guards):

- `sources_processed_total{source_type,status}` · `unparseable_total{reason}` — **per-connector data quality**; the single most useful production signal.
- `evidence_per_record{source_type}` (histogram) — **schema-drift detector**: an ATS silently renaming a field doesn't error, it just makes evidence counts sag.
- `unions_total{key_kind}` · `refusals_total{key_kind}` · `soft_key_merges_total` · `cluster_size` (histogram) — **identity safety**.
- `field_confidence{field}` · `overall_confidence` (histograms) — **scoring drift**.
- `profiles_emitted_total` · `validation_exclusions_total{problem}` — **consumer-visible output health**.
- `run_duration_seconds` + per-stage durations — capacity planning.

### 1.3 Tracing — blueprint

One trace per run; spans per pipeline stage (per-source extract spans, one resolve span, one merge span, projection span), report anomalies attached as span events. Under `serve`, a request span wraps the run. Same optional-OTel seam as metrics; a ~20-line `trace_stage()` context manager in the pipeline is the only core change.

### 1.4 Alerting — blueprint, with one exception

- **Determinism canary — *land now* as CI:** nightly job re-runs the pinned golden corpus and byte-compares against `goldens/expected/`. Any diff pages. This turns the golden dataset from a test into a production monitor — the highest-value alert this system can have, and it's already 90% built.
- Per-connector: `unparseable_total` rate and `skipped` spikes vs. trailing baseline; `evidence_per_record` sag (schema drift).
- Identity safety: refusal-rate spike (shared-identifier epidemic upstream), soft-key merge rate, and a **giant-cluster guard** (`cluster_size > N` pages immediately — a runaway cluster is the fusion catastrophe in progress).
- Scoring drift: population-stability index on the `overall_confidence` histogram vs. a trailing window — catches trust-table or extractor regressions that no single run can see.
- `serve` SLOs (availability, p95 latency) only matter post-Tier-2 hardening; noted, not planned here.

### 1.5 Run ledger — *land now, minimal*

Append each run report to a ledger directory (`--ledger DIR`): timestamped copies of the JSON the engine already writes. History becomes queryable with `jq` today and a table later. Zero schema work — the report is the schema.

---

## 2. Ops / packaging

### 2.1 Reference data out of code — *land now* (do this first)

Trust tables, method reliabilities, and core-field weights move from `constants.py` into `data/scoring.json` with a `version` field; `skill_aliases.json` / `country_aliases.json` gain version headers. Then:

- `run_report.run` records `engine_version` + `scoring_version` + dictionary versions — ADR-016's pin list, completed. Reproducibility becomes a *citable claim*: "profile X was produced by engine 1.2.0 / scoring 2026.08.1".
- **Change control:** editing reference data = a PR that regenerates gold (confidence values shift by design) with the diff reviewed by eye; CI hash-checks that content changes bump the version.
- This is the largest single upgrade available for the money: it converts "judgment calls in code" into governed, versioned, auditable configuration — the thing §6.2 of PRODUCTION_READINESS said consumers would demand.

### 2.2 Container — *land now*

Multi-stage Dockerfile: Node stage builds the UI template → Python slim runtime stage copies engine + configs + data + template; non-root user; pinned base digests; OCI labels carrying version + git SHA; entrypoint `python -m transformer`; `HEALTHCHECK` hitting `/api/health` when run as `serve`. A small `compose.yaml` for the workspace demo. Samples baked in so `docker run … run --input samples` works out of the box.

### 2.3 CI pipeline (GitHub Actions) — *land now*

Jobs, each named for what its failure means:

1. **lint** — ruff.
2. **tests** — full pytest matrix (3.11/3.12), *excluding* gold/scale so failures localize.
3. **gold-gate** — golden byte-compares + truth-sheet asserts only. A red here means "output meaning changed".
4. **scale-gate** — seeded generator metrics (recall 1.0, zero false merges, budget).
5. **determinism** — run the corpus twice + shuffled, diff bytes.
6. **ui-freshness** — rebuild the template and diff against the committed one; a stale committed artifact fails the build (protects the no-Node-needed guarantee).
7. **docker** — image builds; on tags: push + attach `explorer.html` demo artifact.

### 2.4 Versioning & release — *land now (small)*

Semver + `--version` flag embedding the git SHA; the method-string convention (`regex:email_v1`) gets its written rule: *any behavior change to an extractor bumps its version*, so confidence provenance stays comparable across releases. CHANGELOG kept by hand — the ADR discipline already produces the material.

### 2.5 Deploy story — blueprint

Two shapes, both downstream of the same image:
- **Batch job** (the natural first deployment): K8s CronJob / Argo step — inputs from object storage, `profiles.json` + report back to storage, report appended to the ledger, metrics pushed. Determinism makes retries free and idempotent.
- **Service** (`serve` hardened per PRODUCTION_READINESS Tier 2 — authn/z, tenancy, real ASGI): explicitly out of this plan's scope; this plan only promises the container it will run in.
- Projection configs deploy as versioned artifacts per consumer, reviewed like code — the compile-step validation already refuses bad ones at startup.

---

## 3. What deliberately stays out

No Prometheus/Grafana instances or dashboards in the repo, no K8s manifests, no log-shipping config — those belong to the platform that adopts the engine, and shipping toy versions would be résumé decoration. The repo lands *seams and gates*: structured events, a metrics catalog with one emitter, versioned reference data, a container, and a CI pipeline whose job names read as quality claims.

## 4. Interaction with existing guarantees

- Gold bytes change **once** (report gains version fields) — regenerated and reviewed as part of §2.1, then pinned again.
- Determinism is untouched: telemetry is additive and out-of-band; the canary *enforces* the contract nightly instead of trusting it.
- The ledger defect list shrinks: `soft_key_merge` becomes an explicit WARN + metric as part of §1.1.

## 5. Sequencing

| # | Item | Effort | Repo-now? |
|---|---|---|---|
| 1 | §2.1 reference data + versions in report (+ one gold regen) | ~half day | yes |
| 2 | §1.1 structured logging + soft-key event | ~half day | yes |
| 3 | §2.2 Dockerfile + compose | ~2h | yes |
| 4 | §2.3 CI workflow (7 jobs) + §1.4 nightly canary | ~half day | yes |
| 5 | §1.2/1.3 metrics + tracing seams (optional-OTel) | ~1 day | seam only |
| 6 | §1.4 alert rules, §2.5 deploy shapes | — | blueprint (this doc) |

Total repo-landable: **~2 focused days**, after which the two scorecard rows read *Adequate (demo-scale)* honestly — logs, metrics seam, canary, container, CI, governed reference data — with the rest deliberately delegated to the adopting platform.
