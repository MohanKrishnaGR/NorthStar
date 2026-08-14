"""Structured logging: derived views of the run report (OPS_PLAN §1.1).

The rule that keeps this compatible with ADR-016: outputs stay clock-free;
telemetry may know what time it is. Run ids, timestamps, and durations live
in these log records and never in profiles.json or the run report.

Events go to stderr. Formats: "text" for humans at a terminal (default for
the CLI), "json" for collectors (default under `serve`). Default level is
WARNING so a clean run stays quiet — anomalies (skipped sources, refused
unions, soft-key merges) are exactly the lines that appear.
"""
from __future__ import annotations

import json
import logging
import sys

_LOGGER = "transformer"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        doc.update(getattr(record, "fields", {}))
        return json.dumps(doc, ensure_ascii=False, sort_keys=True)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", {})
        kv = " ".join(f"{k}={fields[k]}" for k in sorted(fields))
        head = f"{record.levelname.lower():7} {record.getMessage()}"
        return f"{head}  {kv}".rstrip()


def setup(fmt: str = "text", level: str = "warning") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    logger = logging.getLogger(_LOGGER)
    logger.handlers[:] = [handler]
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))
    logger.propagate = False


def event(name: str, _level: int = logging.INFO, **fields) -> None:
    """One structured event; fields must be JSON-serializable scalars."""
    logging.getLogger(_LOGGER).log(_level, name, extra={"fields": fields})
