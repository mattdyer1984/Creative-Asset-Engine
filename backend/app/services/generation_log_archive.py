"""
Generation Log archive — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). Creates the permanent, self-contained
`Generation Logs/{timestamp}/` folder for one generate-creative call:
generated/original/references image files plus generation.json, so the
folder alone is enough to reproduce or inspect that generation years
later, per the spec's own requirement.

Deliberately **copies** already-materialized files (shutil.copy2 from
each row's existing file_path) rather than re-fetching/re-generating
anything - every image this needs (the winner/final output, the
original slide, the reference images used) was already written to disk
by app/storage.py earlier in the same call. Called synchronously at the
end of the generate_creative router, not backgrounded: the response
already waits for the full paid retry loop, so a handful of local file
copies add negligible latency, and it keeps the archive guaranteed to
exist by the time the frontend gets the response - no race with a
background task.

review.json is written later, by write_review, once a human review is
actually submitted - not here, since none exists yet at generation
time.
"""

import json
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.generation_log import GenerationLog
from app.models.generation_reference_set import GenerationReferenceSet
from app.models.generation_reference_set_image import GenerationReferenceSetImage
from app.models.generation_review import GenerationReview
from app.models.product_reference_image import ProductReferenceImage
from app.models.slide import Slide
from app.services.generate_with_retry import RetryLoopResult


def create_archive(db: Session, generation_log: GenerationLog, retry_result: RetryLoopResult, slide: Slide) -> Path:
    folder = settings.generation_logs_dir / generation_log.created_at.strftime("%Y-%m-%d_%H-%M-%S")
    generated_dir = folder / "generated"
    original_dir = folder / "original"
    references_dir = folder / "references"
    for directory in (generated_dir, original_dir, references_dir):
        directory.mkdir(parents=True, exist_ok=True)

    slide_label = f"slide_{slide.slide_index + 1:02d}"

    generated_paths: list[str] = []
    if retry_result.final_output is not None:
        source = Path(retry_result.final_output.file_path)
    elif retry_result.winner is not None:
        source = Path(retry_result.winner.generated_image.file_path)
    else:
        source = None
    if source is not None and source.exists():
        dest = generated_dir / f"{slide_label}{source.suffix}"
        shutil.copy2(source, dest)
        generated_paths.append(str(dest.relative_to(folder)))

    original_paths: list[str] = []
    original_source = Path(slide.stored_file_path)
    if original_source.exists():
        dest = original_dir / f"{slide_label}{original_source.suffix}"
        shutil.copy2(original_source, dest)
        original_paths.append(str(dest.relative_to(folder)))

    # References: only reachable for the single-product path today - a
    # Bundle Composition winner has no generation_reference_set_id (a
    # bundle attempt has N Sets, one per member, not one on the
    # GeneratedImage itself - see GenerationAttempt's own docstring). A
    # real, small, known gap, not guessed at: bundle calls get an empty
    # references/ folder for now.
    reference_paths: list[str] = []
    if retry_result.winner is not None and retry_result.winner.generated_image.generation_reference_set_id:
        reference_set = db.get(
            GenerationReferenceSet, retry_result.winner.generated_image.generation_reference_set_id
        )
        if reference_set is not None:
            set_images = (
                db.query(GenerationReferenceSetImage)
                .filter(GenerationReferenceSetImage.generation_reference_set_id == reference_set.id)
                .order_by(GenerationReferenceSetImage.rank)
                .all()
            )
            for index, set_image in enumerate(set_images, start=1):
                product_reference_image = db.get(
                    ProductReferenceImage, set_image.product_reference_image_id
                )
                if product_reference_image is None:
                    continue
                reference_source = Path(product_reference_image.file_path)
                if not reference_source.exists():
                    continue
                dest = references_dir / f"product_reference_{index:02d}{reference_source.suffix}"
                shutil.copy2(reference_source, dest)
                reference_paths.append(str(dest.relative_to(folder)))

    generation_json = {
        "generation_uuid": generation_log.id,
        "timestamp": generation_log.created_at.isoformat(),
        "project_id": generation_log.project_id,
        "product_id": generation_log.product_id,
        "bundle_product_ids": generation_log.bundle_product_ids_json,
        # No Creative entity exists post-Phase-2.8 (see MIGRATION_PLAN.md) -
        # Slideshow is the closest living equivalent.
        "creative_id": generation_log.slideshow_id,
        "slideshow_id": generation_log.slideshow_id,
        "slide_id": generation_log.slide_id,
        "blueprint_version": {
            "creative_specification_id": generation_log.creative_specification_id,
            "schema_version": generation_log.creative_specification_schema_version,
        },
        "prompt_version": {
            "prompt_used": generation_log.prompt_used,
            "schema_version": generation_log.creative_specification_schema_version,
        },
        "ai_provider": generation_log.ai_provider,
        "ai_model": generation_log.ai_model,
        "text_strategy": generation_log.text_strategy,
        "generation_settings": {
            "quality_mode": generation_log.quality_mode,
            "creativity_level": generation_log.creativity_level,
        },
        "reference_image_paths": reference_paths,
        "generated_image_paths": generated_paths,
        "original_image_paths": original_paths,
        "generation_duration_seconds": generation_log.generation_duration_seconds,
        "retry_count": generation_log.retry_count,
    }
    (folder / "generation.json").write_text(json.dumps(generation_json, indent=2))

    return folder


def write_review(generation_log: GenerationLog, review: GenerationReview) -> None:
    folder = Path(generation_log.archive_path)
    review_json = {
        "generation_uuid": generation_log.id,
        "overall_score": review.overall_score,
        "main_issue": review.main_issue,
        "comment": review.comment,
        "review_timestamp": review.created_at.isoformat(),
        "learning_mode_enabled": review.learning_mode_enabled,
    }
    (folder / "review.json").write_text(json.dumps(review_json, indent=2))
