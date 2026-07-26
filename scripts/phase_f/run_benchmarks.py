"""
Phase F1 - run every benchmark case through the real provider.

Measurement, not optimisation. This makes NO judgement about whether an
answer is right; it records what the pipeline did, what it cost and how long
it took. Comparison against the benchmark truth is F2's job, deliberately
separate so that a scoring bug cannot quietly change what was measured.

Runs against an ISOLATED data directory (`--data-dir`), so the real dev
database is untouched and a run can be repeated from a clean state. The
providers, however, are entirely real.

Everything is written to `run.json` as it happens, per case, so a run that
dies at case 6 still yields five cases of evidence rather than nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import uuid

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"
BENCHMARKS = BACKEND / "tests" / "benchmarks"


def _bootstrap(data_dir: pathlib.Path) -> None:
    """Point the app at an isolated data dir and bring its schema up."""
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CAE_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(BACKEND))
    result = subprocess.run(
        [str(BACKEND / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=BACKEND, capture_output=True, text=True,
        env={**os.environ, "CAE_DATA_DIR": str(data_dir)},
    )
    if result.returncode != 0:
        raise SystemExit(f"alembic upgrade failed:\n{result.stderr[-2000:]}")


def _cases(only: list[str] | None) -> list[pathlib.Path]:
    found = sorted(p for p in BENCHMARKS.iterdir() if p.is_dir())
    return [c for c in found if not only or c.name in only]


def _stage_records(db, slideshow_id: str, slide_ids: list[str]) -> list[dict]:
    """
    Every AnalysisRun for this slideshow, with the ProviderCall rows it
    produced. Cost is reported per call, never summed into a single figure
    here - `estimated_cost_usd` is NULL for an unpriced model, and adding
    NULLs as zero is how an incomplete total gets presented as a complete one.
    """
    from app.models.analysis_run import AnalysisRun
    from app.models.provider_call import ProviderCall

    runs = (
        db.query(AnalysisRun)
        .filter(
            (AnalysisRun.slideshow_id == slideshow_id)
            | (AnalysisRun.slide_id.in_(slide_ids))
        )
        .order_by(AnalysisRun.created_at)
        .all()
    )

    records = []
    for run in runs:
        calls = db.query(ProviderCall).filter(ProviderCall.analysis_run_id == run.id).all()
        records.append({
            "analysis_run_id": run.id,
            "stage": run.analysis_type,
            "status": run.status,
            "error": run.error,
            "provider": run.provider,
            "model": run.model_name,
            "duration_ms": run.duration_ms,
            "provider_call_ms": run.provider_call_ms,
            "deterministic_ms": (
                round(run.duration_ms - run.provider_call_ms, 2)
                if run.duration_ms is not None and run.provider_call_ms is not None
                else None
            ),
            "provider_calls": [{
                "provider": c.provider,
                "model": c.model,
                "capability": c.capability,
                "prompt_id": c.prompt_id,
                "prompt_version": c.prompt_version,
                "prompt_tokens": c.prompt_tokens,
                "completion_tokens": c.completion_tokens,
                "image_count": c.image_count,
                "provider_latency_ms": c.provider_latency_ms,
                "estimated_cost_usd": c.estimated_cost_usd,
                "cost_status": c.cost_status,
                "record_source": c.record_source,
            } for c in calls],
        })
    return records


def _artifacts(db, slideshow_id: str, slide) -> dict:
    """The inferred artifacts, serialised for F2 to score against truth."""
    from app.services.composition_contract import contract_of, get_current_contract
    from app.services.creative_project_profile import (
        effective_copy_policy,
        effective_overlay_policy,
        effective_primary_text_mode,
        effective_production_value_strategy,
        effective_typography_system,
        get_current_profile,
    )
    from app.services.ownership_artifact import decisions_of, get_current

    out: dict = {}

    contract_row = get_current_contract(db, slide.id)
    contract = contract_of(contract_row)
    out["composition_contract"] = contract.model_dump(mode="json") if contract else None

    profile = get_current_profile(db, slideshow_id)
    if profile is not None:
        system = effective_typography_system(profile)
        out["creative_project_profile"] = {
            "primary_text_mode": str(effective_primary_text_mode(profile) or ""),
            "text_mode_confidence": profile.analysed_text_mode_confidence,
            "copy_policy": str(effective_copy_policy(profile)),
            "overlay_policy": str(effective_overlay_policy(profile)),
            "production_value_strategy": str(effective_production_value_strategy(profile)),
            "classification_evidence": profile.classification_evidence_json,
        }
        out["typography_system"] = system.model_dump(mode="json") if system else None
    else:
        out["creative_project_profile"] = None
        out["typography_system"] = None

    ownership_row = get_current(db, slide.id)
    if ownership_row is not None:
        out["text_ownership"] = {
            "ownership_model_version": ownership_row.ownership_model_version,
            "composition_contract_id": ownership_row.composition_contract_id,
            "composition_contract_version": ownership_row.composition_contract_version,
            "decisions": [d.model_dump(mode="json") for d in decisions_of(ownership_row)],
        }
    else:
        out["text_ownership"] = None

    # Upstream artifacts F2 needs to explain a disagreement: an ownership
    # error caused by an OCR miss is an OCR failure, not an ownership one.
    from app.models.creative_fingerprint import CreativeFingerprint
    from app.models.ocr_result import OCRResult

    if slide.current_ocr_result_id:
        ocr = db.get(OCRResult, slide.current_ocr_result_id)
        out["ocr"] = {
            "raw_text": ocr.raw_text if ocr else None,
            "blocks": list(ocr.structured_blocks_json or []) if ocr else [],
        }
    else:
        out["ocr"] = None

    if slide.current_creative_fingerprint_id:
        row = db.get(CreativeFingerprint, slide.current_creative_fingerprint_id)
        out["creative_fingerprint"] = row.structured_json if row else None
    else:
        out["creative_fingerprint"] = None

    return out


#: The stages that analyse the CREATIVE. The three product stages are
#: excluded by default because they hard-fail without an assigned Product,
#: and the benchmark fixtures declare none - a real gap in what the suite
#: can exercise, reported rather than papered over by inventing a product
#: the annotation never described.
CREATIVE_ANALYSIS_STAGES = (
    "ocr",
    "creative_fingerprint",
    "scene_intelligence",
    "composition_contract",
    "creative_profile",
    "text_ownership",
    "marketing_analysis",
    "narrative_structure",
)


def _select_stages(names: tuple[str, ...] | None):
    from app.slideshow_stages.pipeline import SLIDESHOW_STAGE_PIPELINE

    if names is None:
        return list(SLIDESHOW_STAGE_PIPELINE)
    chosen = [s for s in SLIDESHOW_STAGE_PIPELINE if s.name in names]
    missing = set(names) - {s.name for s in chosen}
    if missing:
        raise SystemExit(f"unknown stage(s): {sorted(missing)}")
    return chosen


def _attach_product(db, slideshow, slide, case: pathlib.Path):
    """
    Create the Product the fixture describes and attach it to the slide.

    The product stages hard-fail without a ProductAppearance. The fixture's
    `product.name` is what a user would type when creating it, so nothing is
    invented here that the annotation does not already state.
    """
    import yaml

    from app.models.product import Product
    from app.models.product_appearance import ProductAppearance

    truth = yaml.safe_load((case / "ground_truth.yaml").read_text())
    product_spec = truth.get("product")
    if not product_spec:
        return None

    product = Product(display_name=product_spec["name"])
    db.add(product)
    db.flush()
    appearance = ProductAppearance(slide_id=slide.id, product_id=product.id)
    db.add(appearance)
    db.commit()
    return product.id


def run_case(case: pathlib.Path, data_dir: pathlib.Path, stages=None,
             *, with_product: bool = False, generate: bool = False) -> dict:
    from app import storage
    from app.db import SessionLocal
    from app.models.slide import Slide
    from app.models.slideshow import Slideshow
    from app.slideshow_stages.orchestrator import SlideshowOrchestrator

    record: dict = {"case": case.name, "started_at": time.time()}
    db = SessionLocal()
    try:
        slideshow = Slideshow()
        db.add(slideshow)
        db.flush()

        original = case / "original.jpg"
        stored = storage.save_creative_original(
            slideshow.id, "original.jpg", original.read_bytes()
        )
        slide = Slide(
            slideshow_id=slideshow.id, slide_index=0, stored_file_path=str(stored),
            original_filename="original.jpg", source_type="upload",
            source_locator=str(original),
        )
        db.add(slide)
        db.commit()

        record["slideshow_id"] = slideshow.id
        record["slide_id"] = slide.id
        if with_product:
            record["product_id"] = _attach_product(db, slideshow, slide, case)
            db.refresh(slideshow)

        started = time.perf_counter()
        orchestrator = (
            SlideshowOrchestrator(stages=stages) if stages else SlideshowOrchestrator()
        )
        record["stages_requested"] = [s.name for s in orchestrator.stages]
        failed_stage, result = orchestrator.run_full_pipeline(db, slideshow)
        record["end_to_end_ms"] = round((time.perf_counter() - started) * 1000, 2)
        record["pipeline_succeeded"] = result.succeeded
        record["failed_stage"] = failed_stage
        record["pipeline_error"] = result.error

        if generate and result.succeeded and record.get("product_id"):
            record["canonical_references"] = _load_canonical_references(
                db, record["product_id"], case
            )
            record["reference_library"] = _build_reference_library(db, record["product_id"])
            db.refresh(slideshow)
            slide = db.get(Slide, slide.id)
        if generate and result.succeeded:
            record["generation"] = _generate(db, slideshow, slide)

        db.expire_all()
        slide = db.get(Slide, slide.id)
        record["stages"] = _stage_records(db, slideshow.id, [slide.id])
        record["artifacts"] = _artifacts(db, slideshow.id, slide)
    except Exception as exc:  # noqa: BLE001 - one case must not lose the rest
        record["harness_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        db.close()

    record["finished_at"] = time.time()
    return record


def _load_canonical_references(db, product_id: str, case: pathlib.Path) -> dict:
    """
    Load the case's Canonical Product References through the PRODUCTION
    upload path - the same one POST /api/products/{id}/reference-images uses.

    Only assets marked `edition_match` are supplied. An `edition_mismatch` is
    a different cover, and a different cover is a different visual identity;
    conditioning generation on one would silently substitute the wrong
    product while appearing to succeed. Excluding them is a decision about
    what the BENCHMARK supplies, not a change to how production behaves -
    production takes whatever references it is given.
    """
    import yaml

    from app.models.product_reference_image import ProductReferenceImage
    from app.storage import save_product_reference_image

    manifest_path = case / "references" / "MANIFEST.yaml"
    if not manifest_path.exists():
        return {"supplied": 0, "excluded": [], "note": "no references directory"}

    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    supplied, excluded = [], []
    for asset in manifest.get("assets") or []:
        if asset.get("edition_match") != "edition_match":
            excluded.append({"file": asset["file"],
                             "reason": asset.get("edition_match"),
                             "notes": asset.get("notes")})
            continue
        content = (case / "references" / asset["file"]).read_bytes()
        image = ProductReferenceImage(
            product_id=product_id, analysis_run_id=None,
            isolation_method="user_upload", file_path="",
        )
        db.add(image)
        db.flush()
        image.file_path = str(save_product_reference_image(product_id, image.id, content))
        supplied.append({"file": asset["file"], "reference_image_id": image.id})
    db.commit()
    return {"supplied": len(supplied), "assets": supplied, "excluded": excluded}


def _build_reference_library(db, product_id: str) -> dict:
    """
    Promote the isolated product crops into the Canonical Reference Library.

    Uses `run_reference_scoring` - the SAME function the products API calls
    via `run_reference_scoring_in_background`. Product Isolation already
    created the ProductReferenceImage rows; scoring is what sets
    `library_status`, and `select_reference_images` only ever considers rows
    marked `included`.

    Deliberately not a benchmark shortcut. Inserting rows with
    `library_status="included"` directly would exercise a path production
    never takes and would hide exactly the integration gap that stopped the
    first P1 run.
    """
    from app.models.product_reference_image import ProductReferenceImage
    from app.services.reference_scoring_stage import run_reference_scoring

    started = time.perf_counter()
    result = run_reference_scoring(db, product_id)
    db.commit()

    rows = db.query(ProductReferenceImage).filter(
        ProductReferenceImage.product_id == product_id
    ).all()
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.library_status or "unscored"] = (
            by_status.get(row.library_status or "unscored", 0) + 1
        )
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "succeeded": result.succeeded,
        "error": result.error,
        "candidates": len(rows),
        "by_library_status": by_status,
    }


def _generate(db, slideshow, slide) -> dict:
    """
    Run the real generation loop and record what it produced.

    Every failure mode is captured rather than raised: P1 exists to observe
    the generation path, and a harness that aborts on the first failure would
    hide everything after it.
    """
    from app.services.generate_with_retry import generate_with_retry

    started = time.perf_counter()
    out: dict = {}
    try:
        outcome = generate_with_retry(
            db, slideshow, quality_mode="fast", slide=slide,
        )
        out["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        out["succeeded"] = getattr(outcome, "succeeded", None)
        out["error"] = getattr(outcome, "error", None)
        attempts = getattr(outcome, "attempts", None)
        if attempts is not None:
            out["attempts"] = len(attempts)
    except Exception as exc:  # noqa: BLE001 - observe, do not abort
        out["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        out["succeeded"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"

    from app.models.final_output import FinalOutput
    from app.models.generated_image import GeneratedImage

    images = db.query(GeneratedImage).filter(GeneratedImage.slide_id == slide.id).all()
    out["generated_images"] = [
        {"id": i.id, "file_path": i.file_path, "status": getattr(i, "status", None)}
        for i in images
    ]
    finals = db.query(FinalOutput).filter(
        FinalOutput.generated_image_id.in_([i.id for i in images])
    ).all() if images else []
    out["final_outputs"] = [
        {"id": f.id, "file_path": f.file_path,
         "has_render_manifest": f.render_manifest_json is not None}
        for f in finals
    ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True,
                        help="isolated CAE_DATA_DIR for this run")
    parser.add_argument("--out", required=True, help="path for run.json")
    parser.add_argument("--only", nargs="*", help="case names, default all eight")
    parser.add_argument("--creative-analysis-only", action="store_true",
                        help="skip the three product stages, which hard-fail "
                             "without an assigned Product (see the module docstring)")
    parser.add_argument("--with-product", action="store_true",
                        help="attach the Product the fixture describes, so the "
                             "product stages can run")
    parser.add_argument("--include-generation", action="store_true",
                        help="run the real generation loop - EXPENSIVE and the "
                             "image model is unpriced")
    parser.add_argument("--fresh", action="store_true",
                        help="delete the data dir first")
    parser.add_argument("--i-understand-this-spends-money", action="store_true",
                        required=True,
                        help="every call in this run is real and billable")
    args = parser.parse_args()

    data_dir = pathlib.Path(args.data_dir)
    if args.fresh and data_dir.exists():
        shutil.rmtree(data_dir)
    _bootstrap(data_dir)

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run = {
        "run_id": str(uuid.uuid4()),
        "data_dir": str(data_dir),
        "cases": [],
    }

    stages = _select_stages(CREATIVE_ANALYSIS_STAGES if args.creative_analysis_only else None)
    run["stages"] = [s.name for s in stages]

    for case in _cases(args.only):
        print(f"--- {case.name}", flush=True)
        record = run_case(case, data_dir, stages,
                          with_product=args.with_product,
                          generate=args.include_generation)
        status = (
            "harness error" if "harness_error" in record
            else "ok" if record.get("pipeline_succeeded")
            else f"failed at {record.get('failed_stage')}"
        )
        print(f"    {status} in {record.get('end_to_end_ms', 0):.0f} ms", flush=True)
        run["cases"].append(record)
        # Written after every case: a run that dies at case 6 still leaves
        # five cases of evidence rather than nothing.
        out_path.write_text(json.dumps(run, indent=2, default=str))

    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
