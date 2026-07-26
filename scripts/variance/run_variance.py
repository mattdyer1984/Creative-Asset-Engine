"""
Case 2 variance study harness.

Measures GENERATION variance with analysis held fixed: the pipeline runs once
through Creative Specification, the request is compiled once, and that exact
request is sent to the provider N times.

Protocol and pre-registered acceptance criteria:
`docs/variance/CASE02_PROTOCOL.md`. This script implements the frozen
configuration and refuses to run if it cannot hold it:

  - escalation disabled (high_quality=None)
  - GPT Image fallback disabled (fallback=None)
  - the prompt hash is asserted identical on every call
  - the model is asserted identical on every call

Every call that reaches the provider is recorded, including failures. There
is no regeneration of a disliked candidate - that would be exactly the
selection bias this study exists to remove.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True,
                        help="an EXISTING data dir whose analysis is complete")
    parser.add_argument("--out", required=True)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--i-understand-this-spends-money", action="store_true",
                        required=True)
    args = parser.parse_args()

    import os
    os.environ["CAE_DATA_DIR"] = str(pathlib.Path(args.data_dir).resolve())

    from app.ai_providers.failover import generate_with_failover
    from app.ai_providers.registry import default_registry
    from app.db import SessionLocal
    from app.models.creative_specification import CreativeSpecification
    from app.models.slide import Slide
    from app.services.generation_engine import _route_image_provider
    from app.services.prompt_compiler import compile_generation_request
    from app.services.reference_selection import (
        get_reference_image_paths,
        select_reference_images,
    )
    from app.services.decision_engine import GenerationPlan
    from app.slideshow_stages.creative_specification_stage import (
        resolve_primary_appearance,
    )

    db = SessionLocal()
    out_dir = pathlib.Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    record: dict = {"candidates": [], "frozen": {}}

    try:
        slide = db.query(Slide).first()
        if slide is None:
            print("no slide - run the benchmark harness into this data dir first")
            return 2

        spec = db.query(CreativeSpecification).filter(
            CreativeSpecification.slide_id == slide.id,
            CreativeSpecification.is_current.is_(True),
        ).first()
        if spec is None:
            print("no current Creative Specification - analysis is incomplete")
            return 2

        appearance = resolve_primary_appearance(slide.current_product_appearances)
        if appearance is None:
            print("no product appearance on the slide")
            return 2

        # --- freeze the tier ONCE. No per-candidate routing. --------------
        plan = GenerationPlan(
            quality_mode="quality", candidate_count=1, provider="", model="",
        )
        provider, decision = _route_image_provider(db, slide, plan)

        reference_set = select_reference_images(
            db, appearance.product_id, spec.structured_json, provider.capabilities
        )
        if reference_set is None:
            print("no Generation Reference Set")
            return 2
        reference_paths = get_reference_image_paths(db, reference_set.id)

        # --- compile the request ONCE ------------------------------------
        request = compile_generation_request(
            creative_specification=spec.structured_json,
            reference_image_paths=reference_paths,
        )
        prompt_hash = _sha256(request.creative_intent.encode())

        record["frozen"] = {
            "commit": "482862fa00451d75c92cffc98d04bf124991c2a3",
            "provider": provider.provider,
            "model": provider.model,
            "tier": decision.tier if decision else "explicit",
            "tier_reasons": decision.reasons if decision else [],
            "prompt_sha256": prompt_hash,
            "prompt_chars": len(request.creative_intent),
            "aspect_ratio": request.aspect_ratio,
            "reference_count": len(reference_paths),
            "reference_sha256": [
                _sha256(pathlib.Path(p).read_bytes()) for p in reference_paths
            ],
            "escalation": "DISABLED",
            "fallback": "DISABLED",
            "seed": "NOT SUPPORTED by this model's SDK surface",
        }
        print(f"  provider   {provider.provider}/{provider.model}")
        print(f"  tier       {record['frozen']['tier']}")
        print(f"  prompt     {prompt_hash[:16]}  ({len(request.creative_intent)} chars)")
        print(f"  references {len(reference_paths)}")
        print(f"  generating {args.candidates} candidates\n")

        for index in range(1, args.candidates + 1):
            # Re-assert the frozen inputs on EVERY call. A study whose
            # inputs drifted halfway through would report noise as variance.
            assert _sha256(request.creative_intent.encode()) == prompt_hash
            assert provider.model == record["frozen"]["model"]

            entry: dict = {"candidate": index}
            start = time.perf_counter()
            try:
                result, failover = generate_with_failover(
                    request, provider,
                    fallback=None,        # GPT Image disabled for the study
                    high_quality=None,    # no escalation between candidates
                )
                elapsed_ms = (time.perf_counter() - start) * 1000

                path = out_dir / f"candidate_{index:02d}.png"
                path.write_bytes(result.image_bytes)

                entry.update({
                    "status": "generated",
                    "latency_ms": round(elapsed_ms, 1),
                    "provider": result.provider,
                    "model": result.model,
                    "attempts": failover.attempts,
                    "transient_errors": failover.transient_errors,
                    "escalated": failover.escalated_to_model,
                    "fell_back_to": failover.fell_back_to_provider,
                    "bytes": len(result.image_bytes),
                    "file": path.name,
                })
                print(f"  [{index}/{args.candidates}] {elapsed_ms:8.0f}ms  "
                      f"{result.model}  attempts={failover.attempts}  "
                      f"{len(result.image_bytes):,}B")
            except Exception as exc:  # noqa: BLE001 - a failure IS a result
                elapsed_ms = (time.perf_counter() - start) * 1000
                entry.update({
                    "status": "failed",
                    "latency_ms": round(elapsed_ms, 1),
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                })
                print(f"  [{index}/{args.candidates}] FAILED after "
                      f"{elapsed_ms:.0f}ms: {type(exc).__name__}")

            record["candidates"].append(entry)
    finally:
        db.close()

    pathlib.Path(args.out).write_text(json.dumps(record, indent=2))
    print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
