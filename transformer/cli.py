"""CLI surface (ADR-014). Exit codes (ADR-013):
0 = profiles emitted (report may contain warnings)
2 = unusable config, bad arguments, or zero readable sources
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .normalize import dates
from .pipeline import run_pipeline
from .projection.config import ConfigError, load
from .report import write_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="transformer",
        description="Multi-source candidate data transformer",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    runp = sub.add_parser("run", help="run the pipeline end-to-end")
    runp.add_argument("--input", required=True,
                      help="input directory (or a single source file)")
    runp.add_argument("--config", required=True, help="projection config JSON")
    runp.add_argument("--out", required=True, help="profiles output path")
    runp.add_argument("--report", required=True, help="run report output path")
    runp.add_argument("--as-of", dest="as_of", default=None,
                      help="YYYY-MM pin for open-ended durations "
                           "(default: latest date observed in the inputs)")
    runp.add_argument("--default-region", default=None,
                      help="ISO region for phones without +CC (e.g. IN); "
                           "no value means such phones are never guessed")
    runp.add_argument("--strict", action="store_true",
                      help="development aid: re-raise adapter errors")
    args = ap.parse_args(argv)

    try:
        cfg = load(args.config)
    except ConfigError as e:
        print("config error:", file=sys.stderr)
        for msg in e.errors:
            print(f"  - {msg}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    as_of = None
    if args.as_of:
        as_of = dates.parse(args.as_of)
        if as_of is None:
            print(f"--as-of {args.as_of!r} is not a parseable date", file=sys.stderr)
            return 2

    root = Path(args.input)
    if root.is_dir():
        inputs = [p for p in root.iterdir() if p.is_file()]
    elif root.is_file():
        inputs = [root]
    else:
        print(f"input not found: {root}", file=sys.stderr)
        return 2

    result = run_pipeline(
        inputs, cfg, default_region=args.default_region, as_of=as_of,
        strict=args.strict,
    )
    if result.readable_sources == 0:
        print("no readable sources in input", file=sys.stderr)
        return 2

    write_json(args.out, result.profiles)
    write_json(args.report, result.report)
    excluded = len(result.report["validation"])
    print(
        f"{len(result.profiles)} profile(s) -> {args.out}"
        + (f" ({excluded} excluded by validation, see report)" if excluded else "")
    )
    print(f"run report -> {args.report}")
    return 0
