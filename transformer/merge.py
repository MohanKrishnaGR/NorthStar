"""Merge: field survivorship over a sorted evidence pool (ADR-004/006).

A pure function: (cluster, records, as_of) -> canonical profile dict. Given
the same pool it cannot produce different output — the evidence pool is
canonically sorted, survivorship ordering is total, and every tiebreak ends
in a stable id comparison.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

from . import confidence
from .constants import SOURCE_TRUST, method_reliability, strength
from .models import Evidence, SourceRecord, value_repr
from .normalize import dates
from .normalize import emails as emails_mod
from .normalize import phones as phones_mod
from .normalize import text


def merge_cluster(cluster: dict, records_by_id: dict[str, SourceRecord],
                  as_of: dates.PartialDate | None):
    """Returns (profile_dict, notes) — notes are unparseable leftovers."""
    notes: list[dict] = []
    pool = sorted(
        (e for rid in cluster["record_ids"] for e in records_by_id[rid].evidence),
        key=Evidence.sort_key,
    )
    recency = {
        rid: records_by_id[rid].updated_at or ""
        for rid in cluster["record_ids"]
    }
    by_field: dict[str, list[Evidence]] = {}
    for e in pool:
        by_field.setdefault(e.field_path, []).append(e)

    def ordered(atoms: list[Evidence]) -> list[Evidence]:
        # Survivorship ordering (ADR-006): trust -> method -> in-band recency
        # -> source_id -> order_index, via chained stable sorts (reverse
        # priority first).
        a = sorted(atoms, key=lambda e: (e.source_id, e.record_id, e.order_index))
        a = sorted(a, key=lambda e: recency[e.record_id], reverse=True)
        a = sorted(
            a,
            key=lambda e: (SOURCE_TRUST[e.source_type], method_reliability(e.method)),
            reverse=True,
        )
        return a

    provenance: list[dict] = []
    field_conf: dict[str, float] = {}
    # Per-field evidence detail for the UI bundle (UI_DESIGN §6). Popped by
    # the pipeline before projection — never serialized into profiles/report.
    debug: dict[str, dict] = {}

    def atom_info(a: Evidence) -> dict:
        return {
            "source_id": a.source_id, "source_type": a.source_type,
            "method": a.method, "record_id": a.record_id,
            "value": json.loads(value_repr(a.value)),
            "raw": None if a.raw_value is None else str(a.raw_value)[:300],
            "locator": a.locator, "normalized": a.normalized,
            "strength": round(strength(a.source_type, a.method), 6),
        }

    def prov(field: str, atom: Evidence, alternatives: list) -> None:
        provenance.append({
            "field": field, "source": atom.source_id, "method": atom.method,
            "alternatives": alternatives,
        })

    # ---------------------------------------------------------- scalar fields
    def scalar(field: str) -> str | None:
        atoms = by_field.get(field, [])
        if not atoms:
            return None
        best = ordered(atoms)[0]
        winners = [a for a in atoms if value_repr(a.value) == value_repr(best.value)]
        alts = sorted({value_repr(a.value) for a in atoms} - {value_repr(best.value)})
        prov(field, best, [_unrepr(v) for v in alts])
        trace = confidence.scalar_trace(atoms, winners)
        field_conf[field] = trace["confidence"]
        debug[field] = {"kind": "scalar", "winner": best.value, "trace": trace,
                        "atoms": [atom_info(a) for a in ordered(atoms)]}
        return best.value

    full_name = scalar("full_name")
    headline = scalar("headline")

    # ------------------------------------------------- location: atomic merge
    location = None
    loc_atoms = by_field.get("location", [])
    if loc_atoms:
        # Most complete struct first, then survivorship — never a chimera of
        # subfields no single source claimed (ADR-006).
        def completeness(e: Evidence) -> int:
            return sum(1 for v in e.value.values() if v)

        best = sorted(ordered(loc_atoms), key=completeness, reverse=True)[0]
        winners = [a for a in loc_atoms if value_repr(a.value) == value_repr(best.value)]
        alts = sorted({value_repr(a.value) for a in loc_atoms} - {value_repr(best.value)})
        prov("location", best, [_unrepr(v) for v in alts])
        trace = confidence.scalar_trace(loc_atoms, winners)
        field_conf["location"] = trace["confidence"]
        debug["location"] = {"kind": "scalar", "winner": dict(best.value),
                             "trace": trace,
                             "atoms": [atom_info(a) for a in ordered(loc_atoms)]}
        location = dict(best.value)

    # ------------------------------------------------ sets: emails and phones
    def element_set(field: str, atoms: list[Evidence]) -> list[str]:
        groups: dict[str, list[Evidence]] = {}
        for a in atoms:
            groups.setdefault(str(a.value), []).append(a)
        scored = sorted(
            ((confidence.element_confidence(g), v) for v, g in groups.items()),
            key=lambda cv: (-cv[0], cv[1]),
        )
        values = [v for _, v in scored]
        elements = []
        for i, (conf, v) in enumerate(scored):
            best = ordered(groups[v])[0]
            prov(f"{field}[{i}]", best, [])
            elements.append({"value": v, "confidence": conf,
                             "atoms": [atom_info(a) for a in ordered(groups[v])]})
        if scored:
            # Field-level score = the best-attested element (emails[0]).
            field_conf[field] = scored[0][0]
            debug[field] = {"kind": "set", "elements": elements}
        return values

    emails = element_set("emails", by_field.get("emails", []))

    # Phone pass 2 (ADR-009): retry raw national numbers with the cluster's
    # resolved country. Never re-clusters — one resolution round.
    phone_atoms = list(by_field.get("phones", []))
    cluster_country = (location or {}).get("country")
    for raw_atom in by_field.get("phones_raw", []):
        e164 = phones_mod.to_e164(raw_atom.value, cluster_country)
        if e164:
            phone_atoms.append(Evidence(
                field_path="phones", value=e164, raw_value=raw_atom.raw_value,
                source_id=raw_atom.source_id, source_type=raw_atom.source_type,
                method=f"phones_pass2:{cluster_country}",
                record_id=raw_atom.record_id, order_index=raw_atom.order_index,
                locator=raw_atom.locator,
            ))
        else:
            # Diagnose honestly: a number that *had* region context (+CC or a
            # cluster country) and still failed is invalid, not context-less.
            s = str(raw_atom.value).strip()
            reason = ("invalid_number" if s.startswith("+") or cluster_country
                      else "no_region_context")
            notes.append({
                "source_id": raw_atom.source_id, "field": "phones",
                "raw_value": str(raw_atom.value), "reason": reason,
            })
    phones = element_set("phones", sorted(phone_atoms, key=Evidence.sort_key))

    # ------------------------------------------------------------------ links
    links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    link_confs = []
    for bucket in ("linkedin", "github", "portfolio"):
        atoms = by_field.get(f"links.{bucket}", [])
        if atoms:
            best = ordered(atoms)[0]
            winners = [a for a in atoms if a.value == best.value]
            alts = sorted({str(a.value) for a in atoms} - {str(best.value)})
            prov(f"links.{bucket}", best, alts)
            trace = confidence.scalar_trace(atoms, winners)
            link_confs.append(trace["confidence"])
            debug[f"links.{bucket}"] = {
                "kind": "scalar", "winner": best.value, "trace": trace,
                "atoms": [atom_info(a) for a in ordered(atoms)],
            }
            links[bucket] = best.value
    other_atoms = by_field.get("links.other", [])
    if other_atoms:
        groups: dict[str, list[Evidence]] = {}
        for a in other_atoms:
            groups.setdefault(str(a.value), []).append(a)
        # D4: a context-free classifier can't know "personal site", but the
        # merge has the candidate's name — a domain carrying it earns the
        # portfolio bucket. Explicit links.portfolio evidence (none of the
        # current adapters emit it) would already own the slot and wins.
        promoted = {v: g for v, g in groups.items()
                    if _is_personal_site(v, full_name)}
        if promoted and links["portfolio"] is None:
            atoms_all = sorted((a for g in promoted.values() for a in g),
                               key=Evidence.sort_key)
            best = ordered(atoms_all)[0]
            winners = [a for a in atoms_all if a.value == best.value]
            alts = sorted(set(promoted) - {str(best.value)})
            prov("links.portfolio", best, alts)
            trace = confidence.scalar_trace(atoms_all, winners)
            link_confs.append(trace["confidence"])
            debug["links.portfolio"] = {
                "kind": "scalar", "winner": best.value, "trace": trace,
                "atoms": [atom_info(a) for a in ordered(atoms_all)],
            }
            links["portfolio"] = best.value
            for v in promoted:
                groups.pop(v)
        links["other"] = sorted(groups)
        link_confs.extend(confidence.element_confidence(g) for g in groups.values())
        if groups:
            debug["links.other"] = {"kind": "set", "elements": [
                {"value": v, "confidence": confidence.element_confidence(groups[v]),
                 "atoms": [atom_info(a) for a in ordered(groups[v])]}
                for v in sorted(groups)
            ]}
    if link_confs:
        field_conf["links"] = round(max(link_confs), 6)

    # ----------------------------------------------------------------- skills
    skills_out = []
    skill_atoms = by_field.get("skills", [])
    if skill_atoms:
        groups2: dict[str, list[Evidence]] = {}
        for a in skill_atoms:
            groups2.setdefault(a.value["name"], []).append(a)
        for name in groups2:
            g = groups2[name]
            skills_out.append({
                "name": name,
                "canonical": any(a.value.get("canonical") for a in g),
                "confidence": confidence.element_confidence(g),
                "sources": sorted({a.source_id for a in g}),
            })
        skills_out.sort(key=lambda s: (-s["confidence"], s["name"]))
        field_conf["skills"] = skills_out[0]["confidence"]
        debug["skills"] = {"kind": "set", "elements": [
            {"value": s["name"], "confidence": s["confidence"],
             "canonical": s["canonical"],
             "atoms": [atom_info(a) for a in ordered(groups2[s["name"]])]}
            for s in skills_out
        ]}

    # ------------------------------------------------------------- experience
    experience, exp_confs, exp_intervals = _merge_experience(
        by_field.get("experience", []), ordered, as_of, prov, notes,
        debug, atom_info,
    )
    if exp_confs:
        field_conf["experience"] = round(max(exp_confs), 6)

    # -------------------------------------------------------------- education
    education, edu_confs = _merge_education(
        by_field.get("education", []), ordered, prov, debug, atom_info
    )
    if edu_confs:
        field_conf["education"] = round(max(edu_confs), 6)

    # ------------------------------------------------------- years_experience
    years = _years_from_intervals(exp_intervals)
    stated_atoms = by_field.get("years_experience", [])
    years_atoms = list(stated_atoms)
    if years is not None:
        years_atoms.append(Evidence(
            field_path="years_experience", value=years, raw_value=years,
            source_id="derived:experience", source_type="derived",
            method="derived:experience_intervals_v1", record_id="derived",
        ))
    years_experience = None
    if years_atoms:
        # Derived-from-ranges wins over stated claims (ADR-006); stated values
        # within 1.0y count as agreement, farther ones as contradiction.
        winner_atom = years_atoms[-1] if years is not None else ordered(stated_atoms)[0]
        years_experience = winner_atom.value
        agree = [
            a for a in years_atoms
            if abs(float(a.value) - float(years_experience)) <= 1.0
        ]
        alts = sorted({
            str(a.value) for a in years_atoms
            if value_repr(a.value) != value_repr(years_experience)
        })
        prov("years_experience", winner_atom, alts)
        trace = confidence.scalar_trace(years_atoms, agree)
        field_conf["years_experience"] = trace["confidence"]
        debug["years_experience"] = {
            "kind": "scalar", "winner": years_experience, "trace": trace,
            "atoms": [atom_info(a) for a in years_atoms],
        }

    candidate_id = _candidate_id(cluster, by_field, full_name)

    profile = {
        "candidate_id": candidate_id,
        # Cluster-level cautions ride the profile itself (DEFECTS_PLAN D3):
        # a consumer reading only profiles.json must see them.
        "flags": list(cluster.get("flags", [])),
        "full_name": full_name,
        "emails": emails,
        "phones": phones,
        "location": location,
        "links": links,
        "headline": headline,
        "years_experience": years_experience,
        "skills": skills_out,
        "experience": experience,
        "education": education,
        "provenance": sorted(provenance, key=lambda p: p["field"]),
        "field_confidence": {k: field_conf[k] for k in sorted(field_conf)},
        "overall_confidence": confidence.overall(field_conf),
        "_debug": debug,  # popped by the pipeline; never serialized
    }
    return profile, notes


# ---------------------------------------------------------------- sub-merges


def _same_job(a: dict, b: dict, as_of) -> bool:
    ca, cb = a.get("company"), b.get("company")
    if not ca or not cb or text.strip_accents(ca) != text.strip_accents(cb):
        return False
    a_dated, b_dated = a.get("start") is not None, b.get("start") is not None
    if a_dated and b_dated:
        end_cap = as_of or (9999, 12)
        return dates.overlaps(a["start"], a.get("end"), b["start"], b.get("end"),
                              as_of=end_cap)
    if a.get("is_current") and b.get("is_current"):
        return True
    ta, tb = a.get("title"), b.get("title")
    return bool(ta and tb and text.strip_accents(ta) == text.strip_accents(tb))


def _merge_experience(atoms, ordered, as_of, prov, notes, debug, atom_info):
    if not atoms:
        return [], [], []
    idx_parent = list(range(len(atoms)))

    def find(i):
        while idx_parent[i] != i:
            idx_parent[i] = idx_parent[idx_parent[i]]
            i = idx_parent[i]
        return i

    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            if _same_job(atoms[i].value, atoms[j].value, as_of):
                ri, rj = find(i), find(j)
                if ri != rj:
                    idx_parent[max(ri, rj)] = min(ri, rj)

    groups: dict[int, list[Evidence]] = {}
    for i, a in enumerate(atoms):
        groups.setdefault(find(i), []).append(a)

    entries = []
    intervals = []
    confs = []
    for root in sorted(groups):
        g = groups[root]
        by_pref = ordered(g)

        def pick(key):
            for a in by_pref:
                if a.value.get(key) is not None:
                    return a.value[key]
            return None

        # Precision beats extremity: a month-known date from any source wins
        # over a year-only bound ("2018 - 2021" must not stretch a job that
        # ATS dates precisely at 2021-05 out to December).
        def best_date(cands, bound, pick):
            precise = [d for d in cands if d[1] is not None]
            pool_ = precise or cands
            return pick(pool_, key=lambda d: dates.month_index(d, bound))

        starts = [a.value["start"] for a in g if a.value.get("start")]
        start = best_date(starts, "start", min) if starts else None
        is_current = any(a.value.get("is_current") for a in g)
        end = None
        if not is_current:
            ends = [a.value["end"] for a in g if a.value.get("end")]
            end = best_date(ends, "end", max) if ends else None
        if start and (end or (is_current and as_of)):
            s_idx = dates.month_index(start, "start")
            e_idx = dates.month_index(end or as_of, "end")
            as_of_idx = dates.month_index(as_of, "end") if as_of else None
            raw_range = (f"{pick('company')}: {dates.render(start)}"
                         f" -> {dates.render(end) or 'present'}")

            def note(reason):
                notes.append({
                    "source_id": by_pref[0].source_id, "field": "experience",
                    "raw_value": raw_range, "reason": reason,
                })

            # "Future" only exists relative to as-of (DEFECTS_PLAN D1a):
            # a clock-free engine judges claims against the pinned date.
            if as_of_idx is not None and s_idx > as_of_idx:
                note("future_dated_range")  # aspiration, not history
            elif e_idx < s_idx:
                # Negative months would corrupt the sum; entry still emitted.
                note("inverted_date_range")
            else:
                if as_of_idx is not None and e_idx > as_of_idx:
                    # "Contract through 2031": count only the elapsed part —
                    # the same semantics open-ended jobs already have. A sum
                    # not re-derivable from visible dates must say why.
                    note("future_end_clamped")
                    e_idx = as_of_idx
                intervals.append((s_idx, e_idx))
        entries.append({
            "company": pick("company"),
            "title": pick("title"),
            "start": dates.render(start),
            "end": dates.render(end),
            "is_current": is_current,
            "summary": pick("summary"),
            "_best": by_pref[0], "_atoms": g,
        })
        confs.append(confidence.element_confidence(g))

    entries.sort(key=lambda x: (
        x["start"] is None,
        -(dates.month_index(dates.parse(x["start"]), "start") if x["start"] else 0),
        x["company"] or "",
    ))
    for i, ent in enumerate(entries):
        group_atoms = ent.pop("_atoms")
        prov(f"experience[{i}]", ent.pop("_best"), [])
        debug[f"experience[{i}]"] = {
            "kind": "entry",
            "value": {k: ent[k] for k in ("company", "title", "start", "end",
                                          "is_current")},
            "confidence": confidence.element_confidence(group_atoms),
            "atoms": [atom_info(a) for a in ordered(group_atoms)],
        }
    return entries, confs, intervals


def _merge_education(atoms, ordered, prov, debug, atom_info):
    if not atoms:
        return [], []
    groups: dict[tuple, list[Evidence]] = {}
    for a in atoms:
        key = (text.strip_accents(a.value.get("institution") or ""),
               a.value.get("end_year"))
        groups.setdefault(key, []).append(a)
    entries, confs = [], []
    for key in sorted(groups, key=lambda k: (-(k[1] or 0), k[0])):
        g = groups[key]
        by_pref = ordered(g)

        def pick(k):
            for a in by_pref:
                if a.value.get(k) is not None:
                    return a.value[k]
            return None

        entries.append({
            "institution": pick("institution"), "degree": pick("degree"),
            "field": pick("field"), "end_year": pick("end_year"),
            "_best": by_pref[0], "_atoms": g,
        })
        confs.append(confidence.element_confidence(g))
    for i, ent in enumerate(entries):
        group_atoms = ent.pop("_atoms")
        prov(f"education[{i}]", ent.pop("_best"), [])
        debug[f"education[{i}]"] = {
            "kind": "entry", "value": dict(ent),
            "confidence": confidence.element_confidence(group_atoms),
            "atoms": [atom_info(a) for a in ordered(group_atoms)],
        }
    return entries, confs


def _years_from_intervals(intervals):
    """Union of month intervals -> years, 1 decimal, Decimal ROUND_HALF_UP
    (ADR-016). Overlapping jobs never double-count."""
    if not intervals:
        return None
    merged = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum(e - s + 1 for s, e in merged)
    years = (Decimal(months) / Decimal(12)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return float(years)


def _candidate_id(cluster, by_field, full_name):
    """Content-derived id (ADR-016): smallest strong identifier, kind-prefixed.

    A multi-identity cluster (a notes file naming two people) must NOT seed
    its id from those identifiers — they belong to other people's clusters
    and would collide with their ids. It falls back to its record seed."""
    if "multi_identity_source" in cluster.get("flags", ()):
        return hashlib.sha256(
            f"record:{cluster['cluster_id']}".encode("utf-8")
        ).hexdigest()[:16]
    contested = cluster.get("contested_keys", frozenset())
    email_keys = sorted({
        k for a in by_field.get("emails", [])
        if f"email:{(k := emails_mod.match_key(a.value))}" not in contested
    })
    if email_keys:
        seed = f"email:{email_keys[0]}"
    else:
        phone_keys = sorted({
            str(a.value) for a in by_field.get("phones", [])
            if f"phone:{a.value}" not in contested
        })
        if phone_keys:
            seed = f"phone:{phone_keys[0]}"
        elif full_name:
            company = next((a.value.get("company") for a in by_field.get("experience", [])
                            if a.value.get("company")), "")
            seed = f"name+company:{text.strip_accents(full_name)}|{text.strip_accents(company or '')}"
        else:
            seed = f"record:{cluster['cluster_id']}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _is_personal_site(url: str, full_name: str | None) -> bool:
    """DEFECTS_PLAN D4: a URL is a portfolio when an accent-stripped name
    token (>= 4 chars) appears in the host's *registrable label* — first
    label only, so TLDs like .dev can never match a candidate named Dev."""
    if not full_name:
        return False
    host = urlparse(str(url)).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    label = host.split(".", 1)[0]
    tokens = [t for t in re.split(r"[^a-z0-9]+", text.strip_accents(full_name))
              if len(t) >= 4]
    return any(t in label for t in tokens)


def _unrepr(v: str):
    import json

    try:
        return json.loads(v)
    except (ValueError, TypeError):  # pragma: no cover
        return v
