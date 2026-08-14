"""CLI surface (ADR-014). Exit codes (ADR-013):
0 = profiles emitted (report may contain warnings)
2 = unusable config, bad arguments, or zero readable sources
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import telemetry
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
    servep = sub.add_parser("serve",
                            help="local workspace UI: upload sources, edit "
                                 "the config, run, explore")
    servep.add_argument("--port", type=int, default=8765)
    servep.add_argument("--host", default="127.0.0.1",
                        help="bind address (0.0.0.0 inside a container)")
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
    runp.add_argument("--emit-ui", default=None, metavar="PATH",
                      help="also write a self-contained explorer HTML "
                           "(requires the built template in ui/dist)")
    for p in (runp, servep):
        p.add_argument("--log-format", choices=("text", "json"), default=None,
                       help="structured log format on stderr "
                            "(default: text for run, json for serve)")
        p.add_argument("--log-level", default="warning",
                       choices=("debug", "info", "warning", "error"),
                       help="log verbosity (default: warning — quiet runs "
                            "log only anomalies)")
    args = ap.parse_args(argv)

    if args.cmd == "serve":
        from .server import serve

        telemetry.setup(args.log_format or "json", args.log_level)
        return serve(args.port, host=args.host)

    telemetry.setup(args.log_format or "text", args.log_level)
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

    template = None
    if args.emit_ui:
        template = (Path(__file__).resolve().parent.parent / "ui" / "dist"
                    / "explorer_template.html")
        if not template.exists():
            print("--emit-ui needs the built template at ui/dist/"
                  "explorer_template.html (run: python tools/build_ui.py)",
                  file=sys.stderr)
            return 2

    result = run_pipeline(
        inputs, cfg, default_region=args.default_region, as_of=as_of,
        strict=args.strict, collect_ui=bool(args.emit_ui),
    )
    if result.readable_sources == 0:
        print("no readable sources in input", file=sys.stderr)
        return 2

    write_json(args.out, result.profiles)
    write_json(args.report, result.report)
    if args.emit_ui:
        import json as _json

        # "</" must not terminate the inline <script> holding the data.
        payload = _json.dumps(result.ui_bundle, ensure_ascii=False,
                              sort_keys=True).replace("</", "<\\/")
        html = template.read_text(encoding="utf-8").replace(
            "\"__RUN_DATA_JSON__\"", payload)
        out_path = Path(args.emit_ui)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        print(f"explorer -> {args.emit_ui}")
    excluded = len(result.report["validation"])
    print(
        f"{len(result.profiles)} profile(s) -> {args.out}"
        + (f" ({excluded} excluded by validation, see report)" if excluded else "")
    )
    print(f"run report -> {args.report}")
    return 0
