"""
Historical benchmark comparability (suite v2).

The product extension is purely additive: no existing field changed value and
no existing expectation was relaxed. That claim has to be *checked*, not
asserted, or "the scorer changed and moved the numbers" becomes a matter of
trust (docs/PRODUCT_BENCHMARK_DESIGN.md §5.4).

So this re-scores the stored O1 run with the current scorer and compares
against the v1 scores recorded at the time. Any difference means the
extension was not additive after all.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUN = ROOT / "docs" / "phase_f" / "run_o1_concurrent.json"
BASELINE = ROOT / "docs" / "phase_f" / "analysis_scores_o1.json"
SCORER = ROOT / "scripts" / "phase_f" / "score_analysis.py"

pytestmark = pytest.mark.skipif(
    not (RUN.exists() and BASELINE.exists() and SCORER.exists()),
    reason="the stored v1 run or its baseline scores are not present",
)


def _rescore() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "scored.json"
        result = subprocess.run(
            [sys.executable, str(SCORER), "--run", str(RUN), "--out", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        return json.loads(out.read_text())


def _summary(scored: dict) -> dict:
    """The published v1 metrics, in the form they were reported."""
    cases = scored["cases"]
    return {
        "device": sum(
            1 for c in cases
            if c["composition_contract"]["device"]["verdict"] in ("exact", "acceptable")
        ),
        "text_mode": sum(
            1 for c in cases
            if c["creative_project_profile"]["primary_text_mode"]["verdict"] == "exact"
        ),
        "zones_matched": sum(
            c["composition_contract"].get("zones", {}).get("matched", 0) for c in cases
        ),
        "zone_roles_exact": sum(
            c["composition_contract"].get("zones", {}).get("role_exact", 0) for c in cases
        ),
        "ownership_exact": sum(c["text_ownership"].get("exact", 0) for c in cases),
        "ownership_expected": sum(c["text_ownership"].get("expected_blocks", 0) for c in cases),
    }


def test_every_v1_metric_is_unchanged_under_the_extended_suite():
    """
    The comparability guarantee. If this fails, scores measured before the
    extension can no longer be compared with scores measured after it, and
    every historical figure in the Phase F and optimisation reports becomes
    unsafe to cite.
    """
    baseline = _summary(json.loads(BASELINE.read_text()))
    current = _summary(_rescore())
    assert current == baseline, (
        "the product extension changed a v1 metric, so it was not additive:\n"
        f"  baseline {baseline}\n  current  {current}"
    )


def test_the_suite_version_moved_with_the_extension():
    version = int((ROOT / "backend" / "tests" / "benchmarks" / "VERSION").read_text().strip())
    assert version >= 2, "adding the product block must bump the suite version"
