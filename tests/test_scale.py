"""T3 scale gate (GOLDEN_DATASET §7): planted recall, zero false merges,
runtime budget, and byte-identical rerun at volume — hash-order bugs love
hiding behind scale."""
import sys
import time
from pathlib import Path

from transformer.pipeline import run_pipeline
from transformer.projection.config import load
from transformer.report import dumps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from gen_scale import generate  # noqa: E402

N, SEED = 1200, 7  # CI-sized; the CLI form runs 5000 in the same budget shape


def test_scale_recall_precision_budget_determinism(tmp_path):
    manifest = generate(N, SEED, tmp_path)
    files = [p for p in tmp_path.iterdir() if p.is_file() and p.name != "manifest.json"]
    cfg = load(ROOT / "configs" / "default.json")

    t0 = time.monotonic()
    run = run_pipeline(files, cfg, as_of=(2026, 8))
    elapsed = time.monotonic() - t0

    cluster_of = {}
    for c in run.report["merges"]["clusters"]:
        for rid in c["record_ids"]:
            cluster_of[rid] = c["cluster_id"]

    failures = []
    for g in manifest["groups"]:
        roots = [cluster_of[r] for r in g["records"]]
        if g["expect"] == "merged" and len(set(roots)) != 1:
            failures.append(("split", g))
        elif g["expect"] == "separate" and len(set(roots)) != len(roots):
            failures.append(("fused", g))
        elif g["expect"] == "isolated":
            note = [r for r in g["records"] if r.endswith("#file")][0]
            others = [r for r in g["records"] if r != note]
            if any(cluster_of[note] == cluster_of[o] for o in others):
                failures.append(("attached", g))

    # Planted strong-key recall must be 1.0 and false merges exactly 0 —
    # these are the headline claims of the identity design.
    assert not failures, f"{len(failures)} planted expectations violated: {failures[:3]}"
    assert len(run.profiles) == manifest["expected_clusters"]
    assert elapsed < 30, f"n={N} took {elapsed:.1f}s — over budget"

    rerun = run_pipeline(files, cfg, as_of=(2026, 8))
    assert dumps(run.profiles) == dumps(rerun.profiles)
    assert dumps(run.report) == dumps(rerun.report)
