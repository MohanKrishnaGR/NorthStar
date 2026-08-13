"""End-to-end orchestration: files + config -> profiles + run report.

Stage order per DESIGN §2: detect -> extract -> normalize(pass 1, inside
adapters) -> resolve identity -> merge (incl. phone pass 2) -> score ->
project -> validate. Input file order never matters: files are sorted, and
every downstream stage re-sorts what it consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import identity, merge
from .adapters import detect_adapter
from .adapters.base import run_adapter
from .normalize import dates
from .projection import schema as schema_mod
from .projection.config import Config
from .projection.project import project


@dataclass
class RunResult:
    profiles: list = field(default_factory=list)  # projected, sorted
    report: dict = field(default_factory=dict)
    readable_sources: int = 0


def run_pipeline(input_paths: list[Path], cfg: Config, *,
                 default_region: str | None = None,
                 as_of: dates.PartialDate | None = None,
                 strict: bool = False) -> RunResult:
    ctx = {"default_region": default_region, "strict": strict}
    files = sorted(input_paths, key=lambda p: p.name)  # order-independence

    source_results = []
    unrecognized = []
    records = []
    for path in files:
        adapter = detect_adapter(path)
        if adapter is None:
            unrecognized.append(path.name)
            continue
        res = run_adapter(adapter, path, ctx)
        source_results.append(res)
        records.extend(res.records)

    if as_of is None:
        as_of = _max_observed_date(records)  # content-derived (ADR-016)

    resolution = identity.resolve(records)
    records_by_id = {r.record_id: r for r in records}

    sch = schema_mod.build(cfg)
    keyed_profiles = []
    validation = []
    unparseable = []
    for src in source_results:
        unparseable.extend(dict(u, source_id=src.source_id) for u in src.unparseable)

    for cluster in resolution.clusters:
        cluster = dict(cluster)
        cluster["flags"] = sorted({
            f for rid in cluster["record_ids"]
            for f in resolution.record_flags.get(rid, [])
        })
        profile, notes = merge.merge_cluster(cluster, records_by_id, as_of)
        unparseable.extend(notes)
        out, errors, proj_notes = project(profile, cfg)
        unparseable.extend(
            dict(n, candidate_id=profile["candidate_id"]) for n in proj_notes
        )
        if errors:
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
                }
                for c in resolution.clusters
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
    return RunResult(
        profiles=[out for _, out in keyed_profiles],
        report=report,
        readable_sources=sum(1 for s in source_results if s.status != "skipped"),
    )


def _max_observed_date(records) -> dates.PartialDate | None:
    """Latest date appearing anywhere in the inputs — the deterministic
    default for as-of. If the inputs carry no dates at all, stays None and
    open-ended durations stay null (no clock is ever consulted)."""
    best = None
    for rec in records:
        candidates = []
        if rec.updated_at:
            candidates.append(dates.parse(rec.updated_at))
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
    return best
