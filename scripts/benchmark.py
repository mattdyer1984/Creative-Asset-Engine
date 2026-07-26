#!/usr/bin/env python3
"""
Benchmark scoring harness (ADR 0001 WP-0.2).

Scores the pipeline against the eight gold-standard cases, **per stage**.
One overall number was explicitly rejected: it tells you quality moved
without telling you which stage moved it, which is how a week of work
raised validator acceptance from 5/7 to 7/7 while the output got worse.

**Stages that do not exist yet report `not_implemented`, never zero.** A
zero would average into a total and read as "working badly"; the honest
statement is that there is nothing there to measure. `not_implemented` is
excluded from every aggregate.

Deterministic stages are scored by comparing against `ground_truth.yaml`.
Vision-scored stages need real provider calls and are opt-in via
`--with-generation`, because they cost money and vary run to run.

Usage:
    python3 scripts/benchmark.py                  # deterministic stages only
    python3 scripts/benchmark.py --json out.json  # machine-readable
    python3 scripts/benchmark.py --case case04_posture
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
BENCHMARKS = BACKEND / "tests" / "benchmarks"
sys.path.insert(0, str(BACKEND))

NOT_IMPLEMENTED = "not_implemented"

# The stages ADR 0001 §16 requires scored independently.
STAGES = [
    "project_analysis",
    "transformation_planning",
    "prompt_compilation",
    "text_handling",
    "generation",
    "project_consistency",
    "human_quality",
]


@dataclass
class StageScore:
    stage: str
    status: str  # "scored" | "not_implemented" | "skipped"
    score: float | None = None
    detail: str = ""
    failures: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    stages: list[StageScore]


def _load(case: Path) -> dict:
    import yaml

    return yaml.safe_load((case / "ground_truth.yaml").read_text())


def score_text_handling(truth: dict) -> StageScore:
    """
    The only stage with a real implementation today: does the classifier
    agree with the annotation about what each block IS?

    Scored on the baked-in/overlay distinction rather than the exact class,
    because that is the distinction the product rule turns on (ADR §4) - and
    the one whose failure stripped designed typography.
    """
    from app.services.text_classification import classify_block

    blocks = truth["text_blocks"]
    correct = 0
    failures: list[str] = []
    for block in blocks:
        expected_baked_in = block["class"] != "platform_caption"
        # OCR's `surface` is what tells the classifier a block sits on a real
        # object the camera photographed - which per the OCR prompt includes a
        # screen or a sign, not only packaging. Both product_native and
        # environmental text are therefore "physical"; only text added
        # digitally on top of the photo is "overlay".
        surface = (
            "physical"
            if block["class"] in ("product_native", "environmental")
            else "overlay"
        )
        result = classify_block({"text": block["text"], "surface": surface})
        if result.is_baked_in == expected_baked_in:
            correct += 1
        else:
            failures.append(
                f"{block['text'][:40]!r}: expected "
                f"{'baked-in' if expected_baked_in else 'overlay'}, "
                f"got {result.text_class} ({result.confidence})"
            )
    return StageScore(
        "text_handling",
        "scored",
        round(correct / len(blocks), 3),
        f"{correct}/{len(blocks)} blocks classified on the baked-in/overlay axis",
        failures,
    )


def score_case(case: Path, with_generation: bool) -> CaseResult:
    truth = _load(case)
    scores = [score_text_handling(truth)]

    for stage, reason in (
        ("project_analysis", "CreativeProjectProfile lands in WP-1.1/WP-3.1"),
        ("transformation_planning", "TransformationPlan lands in WP-3.6"),
        ("prompt_compilation", "structured sectioned compiler lands in WP-2.4"),
        ("project_consistency", "set-coherence validation lands in WP-4.1"),
        ("human_quality", "requires a captured human rating"),
    ):
        scores.append(StageScore(stage, NOT_IMPLEMENTED, None, reason))

    scores.append(
        StageScore("generation", "skipped", None, "needs --with-generation (real provider calls)")
        if not with_generation
        else StageScore("generation", NOT_IMPLEMENTED, None, "rubric scoring lands in WP-4.2")
    )
    scores.sort(key=lambda s: STAGES.index(s.stage))
    return CaseResult(truth["case_id"], scores)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="score a single case")
    parser.add_argument("--json", type=Path, help="write machine-readable results here")
    parser.add_argument(
        "--with-generation", action="store_true", help="include stages that make paid calls"
    )
    options = parser.parse_args()

    cases = sorted(p for p in BENCHMARKS.iterdir() if p.is_dir())
    if options.case:
        cases = [p for p in cases if p.name == options.case]
        if not cases:
            raise SystemExit(f"no benchmark case named {options.case!r}")

    results = [score_case(case, options.with_generation) for case in cases]

    width = max(len(s) for s in STAGES) + 2
    print(f"\nBenchmark: {len(results)} case(s)\n")
    for result in results:
        print(f"  {result.case_id}")
        for stage in result.stages:
            if stage.status == "scored":
                mark = f"{stage.score:.3f}"
            elif stage.status == "skipped":
                mark = "  -  "
            else:
                mark = " n/i "
            print(f"    {stage.stage:<{width}} {mark}  {stage.detail}")
            for failure in stage.failures:
                print(f"      ! {failure}")
        print()

    scored = [s for r in results for s in r.stages if s.status == "scored"]
    by_stage: dict[str, list[float]] = {}
    for stage in scored:
        by_stage.setdefault(stage.stage, []).append(stage.score or 0.0)

    print("  Per-stage means (implemented stages only)")
    for stage in STAGES:
        values = by_stage.get(stage)
        if values:
            print(f"    {stage:<{width}} {sum(values) / len(values):.3f}  (n={len(values)})")
        else:
            print(f"    {stage:<{width}}  n/i")
    print()

    if options.json:
        options.json.write_text(
            json.dumps([asdict(r) for r in results], indent=2, sort_keys=True) + "\n"
        )
        print(f"  wrote {options.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
