"""
Operator spend tooling (P3).

    python scripts/spend.py forecast --slides 3
    python scripts/spend.py forecast --slides 3 --hard-stop 2.00
    python scripts/spend.py today

Dry run is the default and the only mode: this script never makes a provider
call. It forecasts, it authorises, and it reports - the run itself is started
by the application, which enforces per-call limits of its own.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

DEFAULT_STAGES = [
    "ocr", "product_isolation", "product_lock_profile", "creative_fingerprint",
    "scene_intelligence", "composition_contract", "creative_profile",
    "text_ownership", "marketing_analysis", "narrative_structure",
    "creative_specification",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    f = sub.add_parser("forecast", help="what would a run cost?")
    f.add_argument("--slides", type=int, default=1)
    f.add_argument("--stages", nargs="*", default=DEFAULT_STAGES)
    f.add_argument("--daily-cap", type=float, default=None)
    f.add_argument("--hard-stop", type=float, default=None)
    f.add_argument("--allow-unpriced", action="store_true")

    sub.add_parser("today", help="what has been spent today?")

    args = parser.parse_args()

    from app.db import SessionLocal
    from app.services.spend_forecast import authorise_run
    from app.services.spend_limit import load_daily_cap_usd, spend_snapshot

    db = SessionLocal()
    try:
        if args.command == "today":
            snapshot = spend_snapshot(db)
            print(f"  spent today (known)   ${snapshot.spent_usd:.4f}")
            print(f"  unpriced calls today  {snapshot.calls_with_untrusted_cost}")
            cap = load_daily_cap_usd()
            print(f"  configured daily cap  {'disabled' if cap is None else f'${cap:.2f}'}")
            if snapshot.calls_with_untrusted_cost:
                print("  NOTE: today's figure is INCOMPLETE - some calls have no rate")
            return 0

        decision = authorise_run(
            db, args.stages, slides=args.slides,
            daily_cap_usd=args.daily_cap if args.daily_cap is not None else load_daily_cap_usd(),
            hard_stop_usd=args.hard_stop,
            allow_unpriced=args.allow_unpriced,
        )
        print(decision.render())
        print("\n  (dry run - no provider call was made)")
        return 0 if decision.allowed else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
