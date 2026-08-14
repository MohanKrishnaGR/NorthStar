"""Record reference-data checksums (OPS_PLAN §2.1 change control).

Run after any deliberate change to data/*.json — having ALSO bumped the
file's "version" field. tests/test_reference_data.py fails when content
drifts from these records, which is exactly the point: reference data only
changes through this ritual, with the gold diff reviewed alongside.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "transformer" / "data"
TRACKED = ("scoring.json", "skill_aliases.json", "country_aliases.json")


def main() -> None:
    records = {}
    for name in TRACKED:
        p = DATA / name
        blob = p.read_bytes()
        doc = json.loads(blob)
        records[name] = {
            "version": doc["version"],
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    out = DATA / "CHECKSUMS.json"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(records, f, indent=2, sort_keys=True)
        f.write("\n")
    for name, rec in records.items():
        print(f"{name}: v{rec['version']} {rec['sha256'][:12]}…")


if __name__ == "__main__":
    main()
