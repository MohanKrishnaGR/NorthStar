"""The single pinned JSON writer (ADR-016, PLAN §3.4).

Every output file goes through write_json: UTF-8, \\n newlines, sorted keys,
fixed separators. Byte-identical reruns on Windows depend on this function
being the only door out.
"""
from __future__ import annotations

import json
from pathlib import Path


def dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                      separators=(",", ": "))


def write_json(path: str | Path, obj: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(obj))
        f.write("\n")
