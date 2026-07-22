"""
Unit tests for SlideRecreationPromptStage (new pipeline, Phase 2.4e) -
mirrors tests/test_recreation_prompt_stage.py's coverage.
"""

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.recreation_prompt import RecreationPrompt
from app.slideshow_stages.creative_fingerprint_stage import SlideCreativeFingerprintStage
from app.slideshow_stages.product_isolation_stage import SlideProductIsolationStage
from app.slideshow_stages.product_lock_profile_stage import SlideProductLockProfileStage
from app.slideshow_stages.recreation_prompt_stage import SlideRecreationPromptStage
from tests.fakes import FakeAIProviderRegistry, FakePromptGenerationProvider, FakeVisionAnalysisProvider
from tests.test_slide_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_prerequisites(db_session, slideshow, monkeypatch):
    """Runs Product Isolation, Product Lock Profile, and Creative Fingerprint first."""
    monkeypatch.setattr(
        "app.slideshow_stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.slideshow_stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    SlideProductIsolationStage().run(db_session, slideshow)
    SlideProductLockProfileStage().run(db_session, slideshow)
    SlideCreativeFingerprintStage().run(db_session, slideshow)


def test_fails_gracefully_without_a_lock_profile(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    result = SlideRecreationPromptStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Product Lock Profile" in result.error
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_fails_gracefully_without_a_fingerprint(db_session, slideshow_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.slideshow_stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    SlideProductLockProfileStage().run(db_session, slideshow_with_product)

    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideRecreationPromptStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "No Creative Fingerprint" in result.error


def test_succeeds_and_assembles_product_lock_reference(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    result = SlideRecreationPromptStage().run(db_session, slideshow_with_product)

    assert result.succeeded is True

    db_session.refresh(slideshow_with_product)
    prompt_id = slideshow_with_product.current_recreation_prompt_id
    assert prompt_id is not None

    prompt = db_session.get(RecreationPrompt, prompt_id)
    assert prompt.is_current is True
    assert prompt.slideshow_id == slideshow_with_product.id
    assert prompt.creative_id is None

    structured = prompt.structured_json
    assert structured["subject"]
    assert structured["aspect_ratio"] == "4:5"
    assert structured["product_lock_reference"]["product_lock_profile_id"] == prompt.product_lock_profile_id
    assert structured["product_lock_reference"]["immutable_characteristics"] == [
        "bottle shape",
        "label design",
        "cap color",
    ]

    analysis_run = db_session.get(AnalysisRun, prompt.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "recreation_prompt"
    assert analysis_run.slideshow_id == slideshow_with_product.id


def test_ai_is_never_asked_to_produce_ids(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    fake_prompt_provider = FakePromptGenerationProvider()
    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry",
        FakeAIProviderRegistry(prompt_generation_provider=fake_prompt_provider),
    )

    SlideRecreationPromptStage().run(db_session, slideshow_with_product)

    assert fake_prompt_provider.last_call is not None
    assert "product_category" in fake_prompt_provider.last_call["lock_profile"]
    assert "visual_style" in fake_prompt_provider.last_call["fingerprint"]


def test_fails_gracefully_on_provider_error(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry",
        FakeAIProviderRegistry(
            prompt_generation_provider=FakePromptGenerationProvider(raise_error=RuntimeError("provider down"))
        ),
    )

    result = SlideRecreationPromptStage().run(db_session, slideshow_with_product)

    assert result.succeeded is False
    assert "provider down" in result.error

    db_session.refresh(slideshow_with_product)
    assert slideshow_with_product.current_recreation_prompt_id is None


def test_rerun_produces_new_version(db_session, slideshow_with_product, monkeypatch):
    _build_prerequisites(db_session, slideshow_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.slideshow_stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = SlideRecreationPromptStage()
    stage.run(db_session, slideshow_with_product)
    db_session.refresh(slideshow_with_product)
    first_id = slideshow_with_product.current_recreation_prompt_id

    stage.run(db_session, slideshow_with_product)
    db_session.refresh(slideshow_with_product)
    second_id = slideshow_with_product.current_recreation_prompt_id

    assert second_id != first_id
    first = db_session.get(RecreationPrompt, first_id)
    assert first.is_current is False
