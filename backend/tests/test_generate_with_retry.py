"""
Unit tests for the basic automatic retry loop (Phase 10.2 of AI
Creative Engine vNext, see MIGRATION_PLAN.md's "ADR: AI Creative
Engine vNext" §14; Photorealism dimension added Phase 10.3). No real
provider calls - Fake providers throughout.
"""

from pathlib import Path

from sqlalchemy import select

from app.models.final_output import FinalOutput
from app.models.generated_image import GeneratedImage
from app.models.generation_attempt import GenerationAttempt
from app.services.generate_with_retry import RetryLoopResult, generate_with_retry
from app.slideshow_stages.base import StageResult
from tests.fakes import FakeAIProviderRegistry, FakeImageGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_image_generation_stage import _build_full_prerequisites

_IDENTITY_PASSES = {"field_checks": [{"field_name": "silhouette", "preserved": True, "reason": "Matches."}]}
_CREATIVE_PASSES = {
    "field_checks": [{"field_name": "color", "preserved": True, "reason": "Matches."}],
    "overall_explanation": "Everything preserved.",
}
_CREATIVE_FAILS = {
    "field_checks": [{"field_name": "color", "preserved": False, "reason": "Wrong shade."}],
    "overall_explanation": "Color mismatch.",
}
_PHOTOREALISM_PASSES = {
    "realistic_lighting": True,
    "believable_shadows": True,
    "material_accuracy": True,
    "reflections_correct": True,
    "texture_quality": "excellent",
    "perspective_correct": True,
    "object_integrity": True,
    "human_anatomy": "not_applicable",
    "ai_artefacts_detected": False,
    "image_sharpness": "excellent",
    "reasons": ["clean, photorealistic render"],
}


def _patch_generation(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(image_generation_provider=FakeImageGenerationProvider()),
    )


def _patch_validation(monkeypatch, *, creative_result):
    fake_vision = FakeVisionAnalysisProvider(
        results_by_schema_name={
            "identity_validation": _IDENTITY_PASSES,
            "image_validation": creative_result,
            "photorealism": _PHOTOREALISM_PASSES,
        }
    )
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=fake_vision),
    )


def test_accepts_on_the_first_attempt_when_a_candidate_passes(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast")

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 1
    assert result.winner is not None
    assert result.winner.quality_assessment.accepted is True

    slide = slideshow_with_product.primary_slide
    current = db_session.scalars(
        select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
    ).first()
    assert current is not None
    assert current.id == result.winner.generated_image.id


def test_retries_once_then_accepts_when_the_second_attempt_passes(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)

    call_count = {"n": 0}

    class _AlternatingVisionProvider:
        model = "fake-vision-model"
        provider = "openai"

        def analyze_creative(self, image_bytes, prompt_spec, response_schema):
            schema_name = prompt_spec.get("schema_name")
            if schema_name == "identity_validation":
                return _IDENTITY_PASSES
            if schema_name == "photorealism":
                return _PHOTOREALISM_PASSES
            call_count["n"] += 1
            # First attempt's one "fast"-mode candidate fails creative
            # validation; the retry's candidate passes.
            return _CREATIVE_FAILS if call_count["n"] == 1 else _CREATIVE_PASSES

    alternating_provider = _AlternatingVisionProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.image_validation_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=alternating_provider),
    )
    monkeypatch.setattr(
        "app.services.quality_engine.default_registry",
        FakeAIProviderRegistry(vision_provider=alternating_provider),
    )

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=1)

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 2
    assert result.attempts[1].attempt.retry_of_generation_attempt_id == result.attempts[0].attempt.id
    assert result.winner is not None
    assert result.winner.generated_image.generation_attempt_id == result.attempts[1].attempt.id


def test_exhausting_retries_returns_no_winner_without_error(
    db_session, slideshow_with_product, monkeypatch
):
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_FAILS)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=1)

    assert isinstance(result, RetryLoopResult)
    assert len(result.attempts) == 2  # the original attempt + 1 retry, then stop
    assert result.winner is None

    slide = slideshow_with_product.primary_slide
    assert (
        db_session.scalars(
            select(GeneratedImage).where(GeneratedImage.slide_id == slide.id, GeneratedImage.is_current.is_(True))
        ).first()
        is None
    )


def test_fails_cleanly_without_a_creative_specification(db_session, slideshow_with_slide, monkeypatch):
    _patch_generation(monkeypatch)

    result = generate_with_retry(db_session, slideshow_with_slide, "fast")

    assert isinstance(result, StageResult)
    assert result.succeeded is False
    assert "No Creative Specification" in result.error


def test_fails_cleanly_and_stops_immediately_without_a_library(
    db_session, slideshow_with_product, monkeypatch
):
    """A missing Library fails identically on every retry - stop after the first attempt, don't burn the budget."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch, with_library=False)
    _patch_generation(monkeypatch)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", max_retries=2)

    assert isinstance(result, StageResult)
    assert "No Generation Reference Set available" in result.error
    assert db_session.scalars(select(GenerationAttempt)).first() is None


# --- Phase 10.8 of AI Creative Engine vNext (see MIGRATION_PLAN.md's ADR
# §9/§15) - FinalOutput creation once a winner is accepted -----------


def test_no_final_output_when_text_strategy_is_not_given(db_session, slideshow_with_product, monkeypatch):
    """text_strategy=None (the default) preserves pre-Phase-10.8 behavior exactly - no FinalOutput at all."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast")

    assert result.winner is not None
    assert result.final_output is None
    assert db_session.scalars(select(FinalOutput)).first() is None


def test_final_output_created_with_no_text_assets_for_no_text_strategy(
    db_session, slideshow_with_product, monkeypatch
):
    """text_strategy='no_text' still produces a real FinalOutput row - a pass-through, not "nothing happened"."""
    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)
    _patch_generation(monkeypatch)
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", text_strategy="no_text")

    assert result.winner is not None
    assert result.final_output is not None
    assert result.final_output.text_assets_json == []
    assert result.final_output.generated_image_id == result.winner.generated_image.id

    with open(result.final_output.file_path, "rb") as f:
        assert f.read() == Path(result.winner.generated_image.file_path).read_bytes()


def test_final_output_reuses_real_ocr_positions_for_reuse_original_strategy(
    db_session, slideshow_with_product, monkeypatch
):
    """A real end-to-end check: OCR bounding boxes -> real TextAsset dicts -> a real, larger composited file."""
    from PIL import Image as PILImage

    from app.ai_providers.base import GeneratedImageResult
    from app.models.ocr_result import OCRResult
    from app.slideshow_stages.ocr_stage import SlideOCRStage

    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.ocr_stage.default_registry",
        FakeAIProviderRegistry(
            ocr_provider=_fake_ocr_provider_with_bbox()
        ),
    )
    SlideOCRStage().run(db_session, slideshow_with_product)
    db_session.commit()
    slide = slideshow_with_product.primary_slide
    assert slide.current_ocr_result_id is not None
    ocr_result = db_session.get(OCRResult, slide.current_ocr_result_id)
    assert ocr_result.structured_blocks_json[0]["bounding_box"] is not None

    real_png = _real_png_bytes()
    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(
            image_generation_provider=FakeImageGenerationProvider(
                result=GeneratedImageResult(
                    image_bytes=real_png,
                    provider="openai",
                    model="fake-image-model",
                    prompt_used="prompt",
                    seed=None,
                    generation_time_seconds=0.1,
                )
            )
        ),
    )
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", text_strategy="reuse_original")

    assert result.winner is not None
    assert result.final_output is not None
    assert len(result.final_output.text_assets_json) == 1
    assert result.final_output.text_assets_json[0]["wording"] == "SHOP NOW"

    rendered = PILImage.open(result.final_output.file_path)
    assert rendered.size == (400, 400)


def test_reuse_original_excludes_the_products_own_packaging_text(
    db_session, slideshow_with_product, monkeypatch
):
    """
    Real-world-diagnosed fix (see MIGRATION_PLAN.md): an OCR block whose
    text matches the product's own branding_text (packaging text
    already preserved in the base generated image) must be excluded
    from the FinalOutput's text_assets, even if OCR tagged it as a
    marketing-overlay role like "headline" - FakeVisionAnalysisProvider's
    default canned Product Lock Profile (see tests/fakes.py) has
    branding_text=["Sunrise"] (from its labels_and_text), so an OCR
    block reading "Sunrise" must be dropped while a genuine marketing
    headline survives.
    """
    from PIL import Image as PILImage

    from app.ai_providers.base import GeneratedImageResult, OCRExtraction
    from app.models.ocr_result import OCRResult
    from app.slideshow_stages.ocr_stage import SlideOCRStage

    _build_full_prerequisites(db_session, slideshow_with_product, monkeypatch)

    class _FakeOCRProviderWithPackagingText:
        model = "fake-ocr-model"
        provider = "openai"

        def extract_text(self, image_bytes: bytes) -> OCRExtraction:
            return OCRExtraction(
                raw_text="Sunrise Start Fresh",
                structured_blocks=[
                    {
                        "text": "Sunrise",
                        "role": "headline",
                        # OCR's own surface classification got this one
                        # wrong too - the real case (see MIGRATION_PLAN.md).
                        "surface": "overlay",
                        "bounding_box": {"x_min": 0.05, "y_min": 0.05, "x_max": 0.4, "y_max": 0.15},
                    },
                    {
                        "text": "Start Fresh",
                        "role": "headline",
                        "surface": "overlay",
                        "bounding_box": {"x_min": 0.1, "y_min": 0.8, "x_max": 0.4, "y_max": 0.92},
                    },
                ],
            )

    monkeypatch.setattr(
        "app.slideshow_stages.ocr_stage.default_registry",
        FakeAIProviderRegistry(ocr_provider=_FakeOCRProviderWithPackagingText()),
    )
    SlideOCRStage().run(db_session, slideshow_with_product)
    db_session.commit()
    slide = slideshow_with_product.primary_slide
    ocr_result = db_session.get(OCRResult, slide.current_ocr_result_id)
    assert ocr_result.structured_blocks_json[0]["text"] == "Sunrise"

    monkeypatch.setattr(
        "app.services.generation_engine.default_registry",
        FakeAIProviderRegistry(
            image_generation_provider=FakeImageGenerationProvider(
                result=GeneratedImageResult(
                    image_bytes=_real_png_bytes(),
                    provider="openai",
                    model="fake-image-model",
                    prompt_used="prompt",
                    seed=None,
                    generation_time_seconds=0.1,
                )
            )
        ),
    )
    _patch_validation(monkeypatch, creative_result=_CREATIVE_PASSES)

    result = generate_with_retry(db_session, slideshow_with_product, "fast", text_strategy="reuse_original")

    assert result.winner is not None
    assert result.final_output is not None
    wordings = [asset["wording"] for asset in result.final_output.text_assets_json]
    assert wordings == ["Start Fresh"]  # "Sunrise" excluded - it's the product's own packaging text
    PILImage.open(result.final_output.file_path)  # still a valid, real composited image


def _fake_ocr_provider_with_bbox():
    from app.ai_providers.base import OCRExtraction

    class _FakeOCRProvider:
        model = "fake-ocr-model"
        provider = "openai"

        def extract_text(self, image_bytes: bytes) -> OCRExtraction:
            return OCRExtraction(
                raw_text="SHOP NOW",
                structured_blocks=[
                    {
                        "text": "SHOP NOW",
                        "role": "cta",
                        "surface": "overlay",
                        "bounding_box": {"x_min": 0.1, "y_min": 0.8, "x_max": 0.4, "y_max": 0.92},
                    }
                ],
            )

    return _FakeOCRProvider()


def _real_png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image as PILImage

    buffer = BytesIO()
    PILImage.new("RGB", (400, 400), color=(180, 190, 200)).save(buffer, format="PNG")
    return buffer.getvalue()
