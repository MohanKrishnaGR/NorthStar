"""M7: gold-output test — the committed out/ files must match what the code
produces today, byte for byte. If a change legitimately alters output,
regenerate via the two README run commands and review the diff by eye."""
from pathlib import Path

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def _regen(config_name):
    cfg = load(ROOT / "configs" / config_name)
    files = [p for p in SAMPLES.iterdir() if p.is_file()]
    return run_pipeline(files, cfg)  # as-of derived from inputs, like the CLI


def _committed(name):
    return (ROOT / "out" / name).read_text(encoding="utf-8")


def test_default_profiles_match_committed_gold():
    result = _regen("default.json")
    assert dumps(result.profiles) + "\n" == _committed("profiles_default.json")
    assert dumps(result.report) + "\n" == _committed("run_report_default.json")


def test_recruiter_view_profiles_match_committed_gold():
    result = _regen("recruiter_view.json")
    assert dumps(result.profiles) + "\n" == _committed("profiles_recruiter_view.json")
    assert dumps(result.report) + "\n" == _committed("run_report_recruiter_view.json")
