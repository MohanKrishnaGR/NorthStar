"""M6: the determinism suite — guards the headline N1 claim (ADR-016)."""
import os
import random
import shutil
import time
from pathlib import Path

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
AS_OF = (2026, 8)


def sample_files(base=SAMPLES):
    return [p for p in base.iterdir() if p.is_file()]


def snapshot(files, as_of=AS_OF):
    cfg = load(ROOT / "configs" / "default.json")
    result = run_pipeline(files, cfg, as_of=as_of)
    return dumps(result.profiles), dumps(result.report)


def test_same_inputs_byte_identical():
    assert snapshot(sample_files()) == snapshot(sample_files())


def test_shuffled_file_order_byte_identical():
    files = sample_files()
    shuffled = files[:]
    random.Random(42).shuffle(shuffled)
    assert snapshot(files) == snapshot(list(reversed(files)))
    assert snapshot(files) == snapshot(shuffled)


def test_touched_mtimes_byte_identical(tmp_path):
    copy = tmp_path / "samples"
    shutil.copytree(SAMPLES, copy)
    before = snapshot(sample_files(copy))
    stamp = time.time() - 86400 * 365
    for i, p in enumerate(sorted(copy.iterdir())):
        os.utime(p, (stamp + i, stamp + i))  # wildly different mtimes
    assert snapshot(sample_files(copy)) == before


def test_as_of_pins_open_ended_durations():
    profiles_a, _ = snapshot(sample_files(), as_of=(2026, 8))
    profiles_b, _ = snapshot(sample_files(), as_of=(2027, 8))
    assert profiles_a != profiles_b  # current jobs grew by 12 months
    assert '"years_experience": 8.6' in profiles_a
    assert '"years_experience": 9.6' in profiles_b
    # ...but identity is stable across as-of values.
    ids_a = [ln for ln in profiles_a.splitlines() if '"candidate_id"' in ln]
    ids_b = [ln for ln in profiles_b.splitlines() if '"candidate_id"' in ln]
    assert ids_a == ids_b
