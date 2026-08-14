"""End-to-end orchestration: files + config -> profiles + run report.

Stage order per DESIGN §2: detect -> extract -> normalize(pass 1, inside
adapters) -> resolve identity -> merge (incl. phone pass 2) -> score ->
project -> validate. Input file order never matters: files are sorted, and
every downstream stage re-sorts what it consumes.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, identity, merge, telemetry
from .adapters import detect_adapter
from .adapters.base import run_adapter
from .constants import SCORING_VERSION
from .normalize import country as country_mod
from .normalize import dates
from .normalize import skills as skills_mod
from .projection import schema as schema_mod
from .projection.config import Config
from .projection.project import project
from .report import dumps as _dumps


@dataclass
class RunResult:
    profiles: list = field(default_factory=list)  # projected, sorted
    report: dict = field(default_factory=dict)
    readable_sources: int = 0
    ui_bundle: dict | None = None  # only when collect_ui=True (UI_DESIGN §6)


def run_pipeline(input_paths: list[Path], cfg: Config, *,
                 default_region: str | None = None,
                 as_of: dates.PartialDate | None = None,
                 strict: bool = False,
                 collect_ui: bool = False) -> RunResult:
    ctx = {"default_region": default_region, "strict": strict}
    files = sorted(input_paths, key=lambda p: p.name)  # order-independence

    # Telemetry only (OPS_PLAN §1.1): ids/clocks never reach outputs.
    run_id = uuid.uuid4().hex[:12]
    t0 = time.monotonic()
    telemetry.event("run_started", run_id=run_id, inputs=len(files),
                    engine_version=__version__,
                    scoring_version=SCORING_VERSION)

    source_results = []
    unrecognized = []
    records = []
    src_paths: dict[str, Path] = {}
    for path in files:
        adapter = detect_adapter(path)
        if adapter is None:
            unrecognized.append(path.name)
            continue
        res = run_adapter(adapter, path, ctx)
        src_paths[res.source_id] = path
        source_results.append(res)
        records.extend(res.records)
        telemetry.event(
            "source_processed",
            _level=logging.INFO if res.status == "ok" else logging.WARNING,
            run_id=run_id, source_id=res.source_id,
            source_type=res.source_type, status=res.status,
            records=res.records_read,
            evidence=sum(len(r.evidence) for r in res.records),
            error=res.errors[0] if res.errors else None,
        )

    if as_of is None:
        as_of, tier = _derive_as_of(records)  # content-derived (ADR-016)
        if as_of is not None and tier == "claims":
            # No record timestamps exist, so "now" rests on employment
            # claims — one future-dated claim can drag it (DEFECTS_PLAN D1b).
            telemetry.event("as_of_derived_from_claims",
                            _level=logging.WARNING, run_id=run_id,
                            as_of=dates.render(as_of))

    resolution = identity.resolve(records)
    records_by_id = {r.record_id: r for r in records}
    for refusal in resolution.refusals:
        telemetry.event("union_refused", _level=logging.WARNING,
                        run_id=run_id, key=refusal["key"],
                        records=" vs ".join(refusal["records"]))
    for rid, flags in sorted(resolution.record_flags.items()):
        if "multi_identity_source" in flags:
            telemetry.event("multi_identity_flagged", _level=logging.WARNING,
                            run_id=run_id, record_id=rid)

    sch = schema_mod.build(cfg)
    keyed_profiles = []
    validation = []
    unparseable = []
    for src in source_results:
        unparseable.extend(dict(u, source_id=src.source_id) for u in src.unparseable)

    contested = resolution.contested_keys
    candidates_ui = []
    clusters_out = []  # augmented clusters (with flags) for the report
    for cluster in resolution.clusters:
        cluster = dict(cluster)
        cluster["contested_keys"] = contested
        flags = {
            f for rid in cluster["record_ids"]
            for f in resolution.record_flags.get(rid, [])
        }
        if len(cluster["record_ids"]) > 1 and any(
            k.startswith("soft:") for k in cluster["match_keys_used"]
        ):
            # The weakest merge kind, visible everywhere a consumer looks (D3).
            flags.add("soft_key_merge")
        cluster["flags"] = sorted(flags)
        clusters_out.append(cluster)
        profile, notes = merge.merge_cluster(cluster, records_by_id, as_of)
        debug = profile.pop("_debug", {})
        unparseable.extend(notes)
        out, errors, proj_notes = project(profile, cfg)
        unparseable.extend(
            dict(n, candidate_id=profile["candidate_id"]) for n in proj_notes
        )
        if collect_ui:
            candidates_ui.append({
                "candidate_id": profile["candidate_id"],
                "canonical": profile,
                "debug": debug,
                "cluster": {
                    "record_ids": cluster["record_ids"],
                    "match_keys_used": cluster["match_keys_used"],
                    "flags": cluster["flags"],
                },
                "excluded": bool(errors),
                "validation": errors,
            })
        if "soft_key_merge" in cluster["flags"]:
            telemetry.event("soft_key_merge", _level=logging.WARNING,
                            run_id=run_id,
                            candidate_id=profile["candidate_id"],
                            records=len(cluster["record_ids"]))
        if errors:
            telemetry.event("profile_excluded", run_id=run_id,
                            candidate_id=profile["candidate_id"],
                            problems="; ".join(
                                f"{e['field']}: {e['problem']}" for e in errors))
            validation.extend(
                dict(e, candidate_id=profile["candidate_id"]) for e in errors
            )
            continue
        schema_errors = schema_mod.validate(out, sch)
        if schema_errors:  # defense in depth: projector and schema disagree
            validation.extend(
                {"candidate_id": profile["candidate_id"], "field": "<schema>",
                 "problem": msg}
                for msg in schema_errors
            )
            continue
        keyed_profiles.append((profile["candidate_id"], out))

    keyed_profiles.sort(key=lambda kv: kv[0])

    flags_by_source: dict[str, set] = {}
    for rid, flags in resolution.record_flags.items():
        sid = records_by_id[rid].source_id
        flags_by_source.setdefault(sid, set()).update(flags)

    report = {
        "run": {
            "as_of": dates.render(as_of),
            "default_region": default_region,
            "config_fields": [f.path for f in cfg.fields],
            # The complete reproducibility pin (ADR-016 + OPS_PLAN §2.1):
            # same inputs + these versions => byte-identical outputs.
            "engine_version": __version__,
            "scoring_version": SCORING_VERSION,
            "dictionary_versions": {
                "skill_aliases": skills_mod.version(),
                "country_aliases": country_mod.version(),
            },
        },
        "sources": [
            {
                "source_id": s.source_id,
                "source_type": s.source_type,
                "status": s.status,
                "records_read": s.records_read,
                "evidence_emitted": sum(len(r.evidence) for r in s.records),
                "errors": s.errors,
                "flags": sorted(set(s.flags) | flags_by_source.get(s.source_id, set())),
            }
            for s in source_results
        ],
        "unrecognized_files": unrecognized,
        "merges": {
            "clusters": [
                {
                    "cluster_id": c["cluster_id"],
                    "record_ids": c["record_ids"],
                    "match_keys_used": c["match_keys_used"],
                    "flags": c["flags"],
                }
                for c in clusters_out
            ],
            "refusals": resolution.refusals,
        },
        "validation": sorted(
            validation, key=lambda v: (v["candidate_id"], v["field"])
        ),
        "unparseable": sorted(
            unparseable,
            key=lambda u: (u.get("source_id", ""), u.get("candidate_id", ""),
                           u["field"], u["raw_value"]),
        ),
    }
    unparse_counts: dict[str, int] = {}
    for u in unparseable:
        unparse_counts[u["reason"]] = unparse_counts.get(u["reason"], 0) + 1
    if unparse_counts:
        telemetry.event("unparseable_summary", run_id=run_id, **unparse_counts)
    telemetry.event(
        "run_completed", run_id=run_id,
        profiles=len(keyed_profiles), clusters=len(resolution.clusters),
        refusals=len(resolution.refusals),
        excluded=len({v["candidate_id"] for v in validation}),
        duration_ms=int((time.monotonic() - t0) * 1000),
        output_hash=hashlib.sha256(
            _dumps([out for _, out in keyed_profiles]).encode("utf-8")
        ).hexdigest()[:16],
    )

    ui_bundle = None
    if collect_ui:
        candidates_ui.sort(key=lambda c: c["candidate_id"])
        ui_bundle = {
            "run": dict(report["run"], profiles=len(keyed_profiles)),
            "sources": [
                dict(s, content=_source_content(src_paths.get(s["source_id"])))
                for s in report["sources"]
            ],
            "unrecognized_files": unrecognized,
            "merges": report["merges"],
            "validation": report["validation"],
            "unparseable": report["unparseable"],
            "profiles": [out for _, out in keyed_profiles],
            "candidates": candidates_ui,
        }
    return RunResult(
        profiles=[out for _, out in keyed_profiles],
        report=report,
        readable_sources=sum(1 for s in source_results if s.status != "skipped"),
        ui_bundle=ui_bundle,
    )


_CONTENT_CAP = 200_000


def _source_content(path: Path | None) -> dict | None:
    """Raw text of a source for the UI's grounding pane. For binary resume
    formats this is the *extracted* text — exactly what the engine saw."""
    if path is None:
        return None
    kind = {".csv": "csv", ".json": "json"}.get(path.suffix.lower(), "text")
    try:
        if path.suffix.lower() == ".docx":
            from .adapters.resume import _docx_text

            text = _docx_text(path)
        elif path.suffix.lower() == ".pdf":
            from .adapters.resume import _pdf_text

            text = _pdf_text(path)
        else:
            from .adapters.base import read_text

            text = read_text(path)
    except Exception as e:
        return {"kind": "text", "text": f"(unreadable: {type(e).__name__})"}
    return {"kind": kind, "text": text[:_CONTENT_CAP]}


def _derive_as_of(records) -> tuple[dates.PartialDate | None, str]:
    """Two-tier derived as-of (DEFECTS_PLAN D1b), both tiers content-derived
    so determinism holds and the clock stays untouched (ADR-016):

    1. Record timestamps (ATS updated_at) — metadata about *when data was
       recorded*, which is what "now" actually means.
    2. Claim dates (experience/education) — the fallback, honest but
       draggable by a future-dated claim; the caller logs a WARN.

    No dates at all -> (None, ...) and open-ended durations stay null."""
    ts_best = None
    for rec in records:
        if rec.updated_at:
            d = dates.parse(rec.updated_at)
            if d and (ts_best is None or dates.month_index(d, "end") >
                      dates.month_index(ts_best, "end")):
                ts_best = d
    if ts_best is not None:
        return ts_best, "timestamps"
    best = None
    for rec in records:
        candidates = []
        for e in rec.evidence:
            if e.field_path == "experience" and isinstance(e.value, dict):
                candidates.extend([e.value.get("start"), e.value.get("end")])
            elif e.field_path == "education" and isinstance(e.value, dict):
                if e.value.get("end_year"):
                    candidates.append((e.value["end_year"], None))
        for d in candidates:
            if d and (best is None or dates.month_index(d, "end") >
                      dates.month_index(best, "end")):
                best = d
    return best, "claims"
