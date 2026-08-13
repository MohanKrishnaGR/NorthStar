"""Tier-3 seeded scale generator (GOLDEN_DATASET §7).

Emits a CSV + ATS blob + notes files with *planted* ground truth, plus a
manifest declaring what must merge, what must stay separate, and what must be
isolated. Deterministic from (n, seed): CI regenerates instead of committing
thousands of fixture rows.

    python tools/gen_scale.py --n 5000 --seed 7 --out /tmp/t3
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from random import Random

from transformer.normalize.phones import to_e164

FIRST = ["Ana", "Raj", "Mei", "Tom", "Sara", "Ivan", "Lila", "Omar", "Nina",
         "Kofi", "Vera", "Hugo", "Ines", "Yuki", "Ravi", "Cleo", "Egon",
         "Dara", "Milo", "Zia"]
LAST = ["Torres", "Gupta", "Chen", "Novak", "Okafor", "Silva", "Haddad",
        "Vogel", "Iyer", "Marsh", "Kimura", "Duarte", "Farkas", "Osei",
        "Bianchi", "Reyes", "Kaur", "Lindt", "Moreau", "Petrov"]
COMPANIES = ["Marigold Data", "Kite Systems", "Helios Retail", "Vega Bank",
             "Pixelforge", "Streamline AI", "Copper Analytics", "Nimbus Press",
             "Aurora Labs", "Datapile", "Quill Media", "Vertex Cloud"]
TITLES = ["Data Engineer", "Backend Engineer", "Analyst", "Product Manager",
          "SRE", "QA Engineer", "Designer", "ML Engineer"]


def _phone_pool(count: int) -> list[str]:
    """Deterministic pool of libphonenumber-valid E.164 numbers."""
    pool = []
    k = 0
    while len(pool) < count:
        cand = f"+9198765{k:05d}"
        if to_e164(cand):
            pool.append(cand)
        k += 1
    return pool


def generate(n: int, seed: int, outdir: Path) -> dict:
    rng = Random(seed)
    outdir.mkdir(parents=True, exist_ok=True)
    csv_rows: list[list[str]] = []
    ats: list[dict] = []
    groups: list[dict] = []
    expected_clusters = 0
    phones = _phone_pool(n)
    patho_rotation = 0

    def csv_id() -> str:
        return f"gen_roster.csv#row={len(csv_rows) + 1}"

    def add_csv(name, email, phone, company, title) -> str:
        rid = csv_id()
        csv_rows.append([name, email, phone, company, title])
        return rid

    def add_ats(entry) -> str:
        rid = f"gen_ats.json#idx={len(ats)}"
        ats.append(entry)
        return rid

    for i in range(n):
        first = FIRST[rng.randrange(len(FIRST))]
        last = LAST[rng.randrange(len(LAST))]
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}.{i:05d}@example.com"
        company = COMPANIES[rng.randrange(len(COMPANIES))]
        title = TITLES[rng.randrange(len(TITLES))]
        phone = phones[i]
        r = rng.random()

        if r < 0.70:  # clean singleton
            rid = add_csv(name, email, "", company, title)
            groups.append({"kind": "clean", "expect": "merged", "records": [rid]})
            expected_clusters += 1
        elif r < 0.88:  # email duplicate across sources
            a = add_csv(name, email, "", company, title)
            b = add_ats({"candidateName": name, "emailAddress": email,
                         "currentEmployer": company, "designation": title})
            groups.append({"kind": "email_dup", "expect": "merged",
                           "records": [a, b]})
            expected_clusters += 1
        elif r < 0.94:  # phone bridges two different emails
            a = add_csv(name, email, phone, company, title)
            b = add_ats({"candidateName": name,
                         "emailAddress": f"{first.lower()}{i:05d}@example.org",
                         "phoneNumber": phone, "currentEmployer": company})
            groups.append({"kind": "phone_dup", "expect": "merged",
                           "records": [a, b]})
            expected_clusters += 1
        elif r < 0.97:  # three-source chain: email joins A-B, phone joins B-C
            a = add_csv(name, email, "", company, title)
            b = add_ats({"candidateName": name, "emailAddress": email,
                         "phoneNumber": phone})
            note = outdir / f"gen_note_{i:05d}.txt"
            pretty = f"+91 {phone[3:8]} {phone[8:]}"
            note.write_text(f"Referral call at {pretty}. Solid engineer.\n",
                            encoding="utf-8")
            groups.append({"kind": "chain", "expect": "merged",
                           "records": [a, b, f"{note.name}#file"]})
            expected_clusters += 1
        elif r < 0.99:  # same person, conflicting title/company variant
            a = add_csv(name, email, "", company, title)
            b = add_ats({"candidateName": name, "emailAddress": email,
                         "currentEmployer": company + " Group",
                         "designation": "Senior " + title})
            groups.append({"kind": "conflict", "expect": "merged",
                           "records": [a, b]})
            expected_clusters += 1
        else:
            patho_rotation += 1
            if patho_rotation % 3 == 0:  # shared inbox: two people, one email
                other = f"{FIRST[(i + 7) % len(FIRST)]} {LAST[(i + 11) % len(LAST)]}"
                shared = f"referrals.{i:05d}@agency.example"
                a = add_csv(name, shared, "", company, title)
                b = add_ats({"candidateName": other, "emailAddress": shared})
                groups.append({"kind": "shared_inbox", "expect": "separate",
                               "records": [a, b]})
                expected_clusters += 2
            elif patho_rotation % 3 == 1:  # twins: same name+company, own emails
                a = add_csv(name, email, "", company, title)
                b = add_csv(name, f"twin.{i:05d}@example.org", "", company, title)
                groups.append({"kind": "twins", "expect": "separate",
                               "records": [a, b]})
                expected_clusters += 2
            else:  # gossip note naming two people
                a = add_csv(name, email, "", company, title)
                note = outdir / f"gen_gossip_{i:05d}.txt"
                note.write_text(
                    f"Sweep: {email} and stranger.{i:05d}@example.net both open.\n",
                    encoding="utf-8",
                )
                groups.append({"kind": "gossip", "expect": "isolated",
                               "records": [a, f"{note.name}#file"]})
                expected_clusters += 2  # the person + the isolated note

    with open(outdir / "gen_roster.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["name", "email", "phone", "current_company", "title"])
        w.writerows(csv_rows)
    with open(outdir / "gen_ats.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"candidates": ats}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    manifest = {"n": n, "seed": seed, "expected_clusters": expected_clusters,
                "groups": groups}
    with open(outdir / "manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    m = generate(args.n, args.seed, Path(args.out))
    print(f"generated n={args.n} seed={args.seed}: "
          f"{len(m['groups'])} groups, {m['expected_clusters']} expected clusters")


if __name__ == "__main__":
    main()
