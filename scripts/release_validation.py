"""
Release validation against the REAL provider (P4).

Phase F is why this exists. Two structured-output defects failed four of
eight benchmark cases at 100% against the real provider while the entire
mocked suite - over a thousand tests - passed. A fake provider does not
validate the schema it is handed, so no amount of mocked testing can catch
that class of defect.

This is deliberately NOT the full benchmark suite. It is the smallest run
that exercises every provider CONTRACT: one case per response schema, so a
schema or provider regression fails here in about a minute for a few cents,
before it reaches a deployment.

    python scripts/release_validation.py --i-understand-this-spends-money

Exit codes: 0 pass, 1 fail, 2 refused before spending.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

#: One case, chosen because it exercises every schema this codebase sends:
#: OCR, Creative Fingerprint, Scene Intelligence, Composition Contract AND
#: the typography system (it is a designed-typography project, so the
#: profile stage makes its vision call). A caption case would silently skip
#: the typography schema - the exact schema that failed in Phase F.
VALIDATION_CASE = "case04_posture"

STAGES = [
    "ocr", "creative_fingerprint", "scene_intelligence",
    "composition_contract", "creative_profile", "text_ownership",
]

#: What must hold. Not accuracy - that is the benchmark's job. These are
#: contract checks: did every schema round-trip, and did each stage produce
#: something structurally usable?
def checks(artifacts: dict) -> list[tuple[str, bool, str]]:
    ocr = artifacts.get("ocr") or {}
    contract = artifacts.get("composition_contract") or {}
    profile = artifacts.get("creative_project_profile") or {}
    typography = artifacts.get("typography_system") or {}
    ownership = artifacts.get("text_ownership") or {}

    return [
        ("ocr returned text blocks",
         bool(ocr.get("blocks")), f"{len(ocr.get('blocks') or [])} block(s)"),
        ("composition contract has zones",
         bool(contract.get("zones")), f"{len(contract.get('zones') or [])} zone(s)"),
        ("contract relations all resolve",
         all(
             r["subject"] in {z["zone_id"] for z in contract.get("zones") or []}
             and r["object"] in {z["zone_id"] for z in contract.get("zones") or []}
             for r in contract.get("relations") or []
         ), f"{len(contract.get('relations') or [])} relation(s)"),
        ("profile chose a text mode",
         bool(profile.get("primary_text_mode")), str(profile.get("primary_text_mode"))),
        # The regression Phase F found. A designed project MUST produce a
        # typography system; a 400 from the schema shows up here first.
        ("typography system was produced",
         bool(typography), "present" if typography else "MISSING"),
        ("typography has text roles",
         bool(typography.get("text_roles")),
         f"{len(typography.get('text_roles') or {})} role(s)"),
        ("ownership decided every block",
         len(ownership.get("decisions") or []) == len(ocr.get("blocks") or []),
         f"{len(ownership.get('decisions') or [])} decision(s)"),
        ("artifacts carry a validation status",
         bool(ownership.get("decisions")) and contract is not None, "recorded"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--i-understand-this-spends-money", action="store_true", required=True)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--hard-stop", type=float, default=1.00,
                        help="refuse to start if the forecast would cross this")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    import tempfile
    data_dir = pathlib.Path(args.data_dir or tempfile.mkdtemp(prefix="release-validation-"))

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from phase_f.run_benchmarks import _bootstrap, _select_stages, run_case

    _bootstrap(data_dir)

    # Authorise before spending.
    from app.db import SessionLocal
    from app.services.spend_forecast import authorise_run

    db = SessionLocal()
    try:
        decision = authorise_run(db, STAGES, hard_stop_usd=args.hard_stop, allow_unpriced=True)
    finally:
        db.close()
    print(decision.render(), "\n")
    if not decision.allowed:
        print("REFUSED before spending anything.")
        return 2

    case = pathlib.Path(__file__).resolve().parents[1] / "backend" / "tests" / "benchmarks" / VALIDATION_CASE
    print(f"running {VALIDATION_CASE} against the real provider...\n")
    started = time.perf_counter()
    record = run_case(case, data_dir, _select_stages(tuple(STAGES)))
    elapsed = time.perf_counter() - started

    failures = 0
    print(f"{'check':40} {'result':8} detail")
    for name, ok, detail in checks(record.get("artifacts") or {}):
        print(f"  {name:38} {'PASS' if ok else 'FAIL':8} {detail}")
        failures += 0 if ok else 1

    if not record.get("pipeline_succeeded"):
        print(f"\n  PIPELINE FAILED at {record.get('failed_stage')}: "
              f"{(record.get('pipeline_error') or '')[:300]}")
        failures += 1

    known = sum(
        c["estimated_cost_usd"] or 0.0
        for s in record.get("stages", []) for c in s["provider_calls"]
    )
    unpriced = sum(
        1 for s in record.get("stages", []) for c in s["provider_calls"]
        if c["estimated_cost_usd"] is None
    )
    print(f"\n  wall clock       {elapsed:.1f}s")
    print(f"  known cost       ${known:.4f}"
          + (f"  ({unpriced} call(s) unpriced - INCOMPLETE)" if unpriced else ""))
    print(f"  result           {'PASS' if not failures else f'FAIL ({failures})'}")

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(record, indent=2, default=str))

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
