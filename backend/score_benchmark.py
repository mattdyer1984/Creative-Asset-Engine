#!/usr/bin/env python3
"""
Attach human commercial scores to benchmark-corpus candidates, and inspect the
corpus. The human commercial score is the eighth reproducibility artifact: it
turns raw candidates + validator verdicts into a durable commercial judgement
that every future model/architecture run can be compared against.

This needs NO database and NO API keys — it only reads/writes the corpus on disk.

List cases:
  python score_benchmark.py --corpus benchmark_corpus list

Show one case (its runs + candidates + current scores):
  python score_benchmark.py --corpus benchmark_corpus show --case 54a1a9d6_s1

Score one candidate (0-10 commercial usability + a verdict):
  python score_benchmark.py --corpus benchmark_corpus score \
      --case 54a1a9d6_s1 --run 20260728_140102__1a2b3c4d \
      --model gemini-3-pro-image-preview --candidate 0 \
      --commercial-score 8 --verdict usable --rejection-class cosmetic \
      --notes "hearts correct; pink a touch dark"

Rebuild the index (after manual edits):
  python score_benchmark.py --corpus benchmark_corpus reindex
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Score/inspect the benchmark corpus")
    ap.add_argument("--corpus", default="benchmark_corpus", help="corpus root directory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list all cases")
    sub.add_parser("reindex", help="rebuild index.json from disk")
    sub.add_parser("analyze", help="aggregate scores into failure-mode / ship evidence")
    sub.add_parser("vocab", help="print the closed diagnostic vocabularies")

    s_show = sub.add_parser("show", help="show one case")
    s_show.add_argument("--case", required=True)

    s_score = sub.add_parser("score", help="attach a human score + structured diagnostics")
    s_score.add_argument("--case", required=True)
    s_score.add_argument("--run", required=True)
    s_score.add_argument("--model", required=True)
    s_score.add_argument("--candidate", type=int, required=True)
    s_score.add_argument("--reproduction-fidelity", type=float, default=None,
                         help="0-10: faithful stand-in for the ORIGINAL slide (identity + beat)")
    s_score.add_argument("--standalone-appeal", type=float, default=None,
                         help="0-10: how good/usable the image is on its OWN")
    s_score.add_argument("--commercial-score", type=float, default=None,
                         help="optional overall roll-up (legacy)")
    s_score.add_argument("--verdict", default=None, choices=["usable", "repairable", "reject"])
    # business decision
    s_score.add_argument("--would-ship", dest="would_ship", action="store_true", default=None)
    s_score.add_argument("--no-would-ship", dest="would_ship", action="store_false")
    s_score.add_argument("--repair-then-ship", dest="repair_then_ship", action="store_true", default=None)
    s_score.add_argument("--no-repair-then-ship", dest="repair_then_ship", action="store_false")
    # structured diagnostics — OBSERVATION vs DIAGNOSIS.
    # --issue records what was SEEN; a suspected cause + confidence are OPTIONAL:
    #   --issue color_drift                        (pure observation, no diagnosis)
    #   --issue color_drift:critical               (+ severity)
    #   --issue color_drift:critical:model:high    (+ suspected cause + confidence)
    s_score.add_argument("--issue", dest="observed_issues", action="append", default=[],
                         help="observation[:severity[:suspected_cause[:confidence]]] (repeatable)")
    s_score.add_argument("--appeal-strength", dest="appeal_strengths", action="append", default=[],
                         help="code (repeatable)")
    # --repair records a PROPOSED remedy (hypothesis): strategy[:confidence]
    s_score.add_argument("--repair", dest="repair_hypotheses", action="append", default=[],
                         help="repair strategy[:confidence] — a hypothesis (repeatable)")
    s_score.add_argument("--repairable", dest="repairable", action="store_true", default=None)
    s_score.add_argument("--not-repairable", dest="repairable", action="store_false")
    s_score.add_argument("--notes", default="")
    s_score.add_argument("--by", default="human")

    # verify: record that later evidence confirmed/refuted a suspected cause
    s_verify = sub.add_parser("verify", help="confirm/refute a suspected cause with later evidence")
    s_verify.add_argument("--case", required=True)
    s_verify.add_argument("--run", required=True)
    s_verify.add_argument("--model", required=True)
    s_verify.add_argument("--candidate", type=int, required=True)
    s_verify.add_argument("--observation", required=True, help="the observed_issue to verify")
    s_verify.add_argument("--status", required=True, choices=["confirmed", "refuted", "unverified"])
    s_verify.add_argument("--note", default="")

    args = ap.parse_args()

    from app.benchmark import corpus as corpuslib

    root = Path(args.corpus)

    if args.cmd == "reindex":
        idx = corpuslib.rebuild_index(root)
        print(f"Reindexed {idx['case_count']} case(s) -> {root / 'index.json'}")
        return 0

    if args.cmd == "vocab":
        print(f"scoring_rubric_version: {corpuslib.SCORING_RUBRIC_VERSION}   "
              f"corpus_schema_version: {corpuslib.CORPUS_SCHEMA_VERSION}")
        print("observed_issues (fact): ", sorted(corpuslib.OBSERVED_ISSUES))
        print("appeal_strengths:       ", sorted(corpuslib.APPEAL_STRENGTHS))
        print("repair_strategies (hyp):", sorted(corpuslib.REPAIR_STRATEGIES))
        print("suspected_causes (interp):", sorted(corpuslib.SUSPECTED_CAUSES))
        print("confidence_levels:      ", sorted(corpuslib.CONFIDENCE_LEVELS))
        print("diagnosis_statuses:     ", sorted(corpuslib.DIAGNOSIS_STATUSES))
        print("severities:             ", sorted(corpuslib.SEVERITIES))
        return 0

    if args.cmd == "verify":
        case_root = root / "cases" / args.case
        path = corpuslib.verify_diagnosis(
            case_root, args.run, args.model, args.candidate, args.observation,
            status=args.status, note=args.note,
        )
        print(f"Diagnosis '{args.observation}' -> {args.status}: {path}")
        return 0

    if args.cmd == "analyze":
        agg = corpuslib.aggregate(root)
        print(json.dumps(agg, indent=2))
        return 0

    if args.cmd == "list":
        idx = corpuslib.rebuild_index(root)
        if not idx["cases"]:
            print(f"(no cases in {root})"); return 0
        for c in idx["cases"]:
            print(f"{c['case_id']}  slide {c['slide_index']}  "
                  f"refs={c['reference_count']}  runs={c['run_count']}")
            for r in c["runs"]:
                print(f"    run {r['run_id']}  models={r['models']}  "
                      f"scored {r['scored']}/{r['candidates']}")
        return 0

    if args.cmd == "show":
        case_root = root / "cases" / args.case
        man = case_root / "request" / "manifest.json"
        if not man.exists():
            print(f"no case {args.case} in {root}"); return 2
        manifest = json.loads(man.read_text())
        print(json.dumps(manifest, indent=2))
        runs_dir = case_root / "runs"
        if runs_dir.is_dir():
            for run_root in sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name != "_drift"):
                print(f"\n== run {run_root.name} ==")
                for score_path in sorted(run_root.rglob("score.json")):
                    cand_dir = score_path.parent
                    cand = json.loads((cand_dir / "candidate.json").read_text()) if (cand_dir / "candidate.json").exists() else {}
                    score = json.loads(score_path.read_text())
                    rel = cand_dir.relative_to(run_root)
                    dec = score.get("decision") or {}
                    diag = score.get("diagnostics") or {}
                    def _fmt(i):
                        obs = i.get("observation")
                        c = i.get("suspected_cause")
                        if not c:
                            return obs
                        conf = i.get("cause_confidence") or "?"
                        st = i.get("diagnosis_status", "unverified")
                        return f"{obs}(~{c}/{conf}/{st})"
                    issues = "; ".join(_fmt(i) for i in diag.get("observed_issues", []) if isinstance(i, dict)) or "-"
                    print(f"  {rel}  gen={cand.get('generated')} "
                          f"accepted={cand.get('accepted')} identity={cand.get('identity_passed')}  "
                          f"repro={score.get('reproduction_fidelity')} "
                          f"appeal={score.get('standalone_appeal')} verdict={score.get('verdict')} "
                          f"ship={dec.get('would_ship')} repair_ship={dec.get('repair_then_ship')}  "
                          f"observed=[{issues}]"
                          + (f"  ({score.get('notes')})" if score.get('notes') else ""))
        return 0

    if args.cmd == "score":
        case_root = root / "cases" / args.case
        path = corpuslib.score_candidate(
            case_root, args.run, args.model, args.candidate,
            reproduction_fidelity=args.reproduction_fidelity,
            standalone_appeal=args.standalone_appeal,
            commercial_score=args.commercial_score, verdict=args.verdict,
            would_ship=args.would_ship, repair_then_ship=args.repair_then_ship,
            observed_issues=args.observed_issues,
            appeal_strengths=args.appeal_strengths,
            repair_hypotheses=args.repair_hypotheses, repairable=args.repairable,
            notes=args.notes, scored_by=args.by,
        )
        corpuslib.rebuild_index(root)
        print(f"Scored -> {path}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
