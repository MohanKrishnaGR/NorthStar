"""O2: structured logging — events are derived views of the run report."""
import json
import logging
from pathlib import Path

import pytest

from transformer import telemetry
from transformer.pipeline import run_pipeline
from transformer.projection.config import load

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def events(caplog):
    # telemetry.setup() (called by CLI tests earlier in the session) turns
    # propagation off; restore it so caplog's root handler sees our events.
    logger = logging.getLogger("transformer")
    old_propagate, old_handlers = logger.propagate, logger.handlers[:]
    logger.propagate, logger.handlers[:] = True, []
    caplog.set_level(logging.INFO, logger="transformer")
    try:
        files = [p for p in (ROOT / "samples").iterdir() if p.is_file()]
        run_pipeline(files, load(ROOT / "configs" / "default.json"),
                     as_of=(2026, 8))
        return [(r.levelname, r.getMessage(), getattr(r, "fields", {}))
                for r in caplog.records]
    finally:
        logger.propagate, logger.handlers[:] = old_propagate, old_handlers


def by_name(events, name):
    return [e for e in events if e[1] == name]


def test_anomalies_log_at_warning(events):
    skipped = [e for e in by_name(events, "source_processed")
               if e[2]["source_id"] == "garbage.json"]
    assert skipped and skipped[0][0] == "WARNING"
    flagged = by_name(events, "multi_identity_flagged")
    assert flagged and flagged[0][0] == "WARNING"
    assert flagged[0][2]["record_id"] == "notes_two_people.txt#file"


def test_run_completed_carries_output_hash_and_counts(events):
    done = by_name(events, "run_completed")
    assert len(done) == 1
    fields = done[0][2]
    assert fields["profiles"] == 4 and fields["refusals"] == 0
    assert len(fields["output_hash"]) == 16
    assert fields["duration_ms"] >= 0
    # Determinism carries into telemetry: same inputs, same output hash.
    files = [p for p in (ROOT / "samples").iterdir() if p.is_file()]
    logger = logging.getLogger("transformer")
    handler_records = []

    class Capture(logging.Handler):
        def emit(self, record):
            handler_records.append(record)

    cap = Capture()
    logger.addHandler(cap)
    try:
        run_pipeline(files, load(ROOT / "configs" / "default.json"),
                     as_of=(2026, 8))
    finally:
        logger.removeHandler(cap)
    done2 = [r for r in handler_records if r.getMessage() == "run_completed"]
    assert done2[0].fields["output_hash"] == fields["output_hash"]


def test_json_formatter_emits_parseable_lines():
    record = logging.LogRecord("transformer", logging.WARNING, "", 0,
                               "union_refused", None, None)
    record.fields = {"key": "email:x@y.com", "run_id": "abc123def456"}
    line = telemetry.JsonFormatter().format(record)
    doc = json.loads(line)
    assert doc["event"] == "union_refused"
    assert doc["level"] == "warning" and doc["key"] == "email:x@y.com"
    assert "ts" in doc


def test_default_level_keeps_clean_runs_quiet(capsys):
    telemetry.setup("text", "warning")
    telemetry.event("run_started", run_id="x", inputs=3)  # INFO: swallowed
    telemetry.event("soft_key_merge", _level=logging.WARNING,
                    run_id="x", candidate_id="c", records=2)
    err = capsys.readouterr().err
    assert "run_started" not in err
    assert "soft_key_merge" in err and "candidate_id=c" in err
