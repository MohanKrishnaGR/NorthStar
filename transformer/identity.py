"""Identity resolution: deterministic blocking + union-find (ADR-005).

Guarantees, in order of importance:
1. Two different people are never silently fused (contradiction guard checks
   the full cross-product of cluster members; multi-identity sources are
   excluded from blocking entirely).
2. Refusals are reproducible: unions execute in canonical sorted order, and
   the union-find representative is always the smallest member id — never
   rank-based, which would depend on arrival order (PLAN.md §3.2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .constants import UNSTRUCTURED_TYPES
from .models import SourceRecord
from .normalize import emails as emails_mod
from .normalize import text

_KEY_STRENGTH = {"email": 0, "phone": 1, "soft": 2}
_TOKEN_RE = re.compile(r"[^\w]+")


@dataclass
class Resolution:
    clusters: list = field(default_factory=list)  # {cluster_id, record_ids, match_keys_used}
    refusals: list = field(default_factory=list)  # {records, key, reason}
    record_flags: dict = field(default_factory=dict)  # record_id -> [flags]


def name_tokens(name: str) -> list[str]:
    return [t for t in _TOKEN_RE.split(text.strip_accents(name)) if t]


def names_compatible(a: str, b: str) -> bool:
    """Deterministic predicate (ADR-005): token sets overlap, where an initial
    matches any token it prefixes. Empty names contradict nothing."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return True
    for x in ta:
        for y in tb:
            if x == y:
                return True
            if len(x) == 1 and y.startswith(x):
                return True
            if len(y) == 1 and x.startswith(y):
                return True
    return False


def _record_keys(rec: SourceRecord, resolution: Resolution) -> list[tuple[str, str]]:
    email_keys = sorted(
        {emails_mod.match_key(e.value) for e in rec.evidence if e.field_path == "emails"}
    )
    phone_keys = sorted(
        {str(e.value) for e in rec.evidence if e.field_path == "phones"}
    )
    if rec.source_type in UNSTRUCTURED_TYPES and (
        len(email_keys) >= 2 or len(phone_keys) >= 2
    ):
        # One-candidate-per-file assumption violated: this source would union
        # into several people's clusters and transitively fuse them. Its keys
        # are withdrawn from blocking; its evidence attaches to no one.
        resolution.record_flags.setdefault(rec.record_id, []).append(
            "multi_identity_source"
        )
        return []
    keys = [("email", k) for k in email_keys] + [("phone", k) for k in phone_keys]
    if not keys:
        name = next(
            (e.value for e in rec.evidence if e.field_path == "full_name"), None
        )
        company = next(
            (
                e.value.get("company")
                for e in rec.evidence
                if e.field_path == "experience"
                and isinstance(e.value, dict)
                and e.value.get("is_current")
                and e.value.get("company")
            ),
            None,
        )
        if name and company:
            keys.append(("soft", f"{text.strip_accents(name)}|{text.strip_accents(company)}"))
    return keys


def resolve(records: list[SourceRecord]) -> Resolution:
    resolution = Resolution()
    by_id = {r.record_id: r for r in records}
    names_of = {
        r.record_id: [e.value for e in r.evidence if e.field_path == "full_name"]
        for r in records
    }

    parent: dict[str, str] = {rid: rid for rid in by_id}
    members: dict[str, set[str]] = {rid: {rid} for rid in by_id}
    keys_used: dict[str, set[str]] = {rid: set() for rid in by_id}

    def find(rid: str) -> str:
        while parent[rid] != rid:
            parent[rid] = parent[parent[rid]]
            rid = parent[rid]
        return rid

    def clusters_compatible(root_a: str, root_b: str) -> bool:
        for ma in sorted(members[root_a]):
            for mb in sorted(members[root_b]):
                for na in names_of[ma]:
                    for nb in names_of[mb]:
                        if not names_compatible(na, nb):
                            return False
        return True

    # Blocking: key -> sorted record ids.
    key_groups: dict[tuple[str, str], set[str]] = {}
    for rid in sorted(by_id):
        for key in _record_keys(by_id[rid], resolution):
            key_groups.setdefault(key, set()).add(rid)

    # Canonical union order (ADR-016): key strength, key value, record id.
    for kind, value in sorted(key_groups, key=lambda k: (_KEY_STRENGTH[k[0]], k[1])):
        group = sorted(key_groups[(kind, value)])
        base = group[0]
        for other in group[1:]:
            ra, rb = find(base), find(other)
            if ra == rb:
                continue
            if not clusters_compatible(ra, rb):
                resolution.refusals.append({
                    "records": sorted([ra, rb]),
                    "key": f"{kind}:{value}",
                    "reason": "suspect_shared_identifier",
                })
                continue
            # Representative = smallest member id, so cluster identity is
            # content-determined, not arrival-order-determined.
            root, child = (ra, rb) if ra < rb else (rb, ra)
            parent[child] = root
            members[root] |= members.pop(child)
            keys_used[root] |= keys_used.pop(child) | {f"{kind}:{value}"}

    roots = sorted({find(rid) for rid in by_id})
    for root in roots:
        resolution.clusters.append({
            "cluster_id": root,
            "record_ids": sorted(members[find(root)]),
            "match_keys_used": sorted(keys_used[find(root)]),
        })
    return resolution
