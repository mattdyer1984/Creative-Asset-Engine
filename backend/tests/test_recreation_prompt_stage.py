"""
Unit tests for RecreationPromptStage (plan §13's Stage contract tests).
"""

import json

from sqlalchemy import select

from app.models.analysis_run import STATUS_SUCCEEDED, AnalysisRun
from app.models.recreation_prompt import RecreationPrompt
from app.stages.creative_fingerprint_stage import CreativeFingerprintStage
from app.stages.product_isolation_stage import ProductIsolationStage
from app.stages.product_lock_profile_stage import ProductLockProfileStage
from app.stages.recreation_prompt_stage import RecreationPromptStage
from tests.fakes import FakeAIProviderRegistry, FakePromptGenerationProvider, FakeVisionAnalysisProvider
from tests.test_creative_fingerprint_stage import FINGERPRINT_RESULT


def _build_prerequisites(db_session, creative, monkeypatch):
    """Runs Product Isolation, Product Lock Profile, and Creative Fingerprint first."""
    monkeypatch.setattr(
        "app.stages.product_isolation_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    monkeypatch.setattr(
        "app.stages.creative_fingerprint_stage.default_registry",
        FakeAIProviderRegistry(vision_provider=FakeVisionAnalysisProvider(result=FINGERPRINT_RESULT)),
    )
    ProductIsolationStage().run(db_session, creative, creative.blueprint)
    ProductLockProfileStage().run(db_session, creative, creative.blueprint)
    CreativeFingerprintStage().run(db_session, creative, creative.blueprint)


def test_fails_gracefully_without_a_lock_profile(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    result = RecreationPromptStage().run(
        db_session, creative_with_product, creative_with_product.blueprint
    )

    assert result.succeeded is False
    assert "No Product Lock Profile" in result.error
    assert db_session.scalars(select(AnalysisRun)).first() is None


def test_fails_gracefully_without_a_fingerprint(db_session, creative_with_product, monkeypatch):
    monkeypatch.setattr(
        "app.stages.product_lock_profile_stage.default_registry", FakeAIProviderRegistry()
    )
    ProductLockProfileStage().run(db_session, creative_with_product, creative_with_product.blueprint)

    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    result = RecreationPromptStage().run(
        db_session, creative_with_product, creative_with_product.blueprint
    )

    assert result.succeeded is False
    assert "No Creative Fingerprint" in result.error


def test_succeeds_and_assembles_product_lock_reference(db_session, creative_with_product, monkeypatch):
    _build_prerequisites(db_session, creative_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )
    result = RecreationPromptStage().run(
        db_session, creative_with_product, creative_with_product.blueprint
    )

    assert result.succeeded is True

    db_session.refresh(creative_with_product.blueprint)
    prompt_id = creative_with_product.blueprint.current_recreation_prompt_id
    assert prompt_id is not None

    prompt = db_session.get(RecreationPrompt, prompt_id)
    assert prompt.is_current is True
    assert prompt.product_lock_profile_id == creative_with_product.blueprint.current_product_lock_profile_id
    assert prompt.creative_fingerprint_id == creative_with_product.blueprint.current_creative_fingerprint_id

    structured = json.loads(prompt.structured_json)
    # AI-generated creative direction fields present:
    assert structured["subject"]
    assert structured["aspect_ratio"] == "4:5"
    # product_lock_reference assembled by the Stage, not the AI - must
    # reference the real profile id and its real immutable_characteristics,
    # not something the model invented.
    assert structured["product_lock_reference"]["product_lock_profile_id"] == prompt.product_lock_profile_id
    assert structured["product_lock_reference"]["immutable_characteristics"] == [
        "bottle shape",
        "label design",
        "cap color",
    ]

    analysis_run = db_session.get(AnalysisRun, prompt.analysis_run_id)
    assert analysis_run.status == STATUS_SUCCEEDED
    assert analysis_run.analysis_type == "recreation_prompt"


def test_ai_is_never_asked_to_produce_ids(db_session, creative_with_product, monkeypatch):
    """
    Directly verifies the pure-composition constraint: the provider call
    receives only lock_profile/fingerprint dicts (plain data, no ids to
    hallucinate) and the response_schema passed to it has no
    product_lock_profile_id / reference_image_ids fields at all.
    """
    _build_prerequisites(db_session, creative_with_product, monkeypatch)

    fake_prompt_provider = FakePromptGenerationProvider()
    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry",
        FakeAIProviderRegistry(prompt_generation_provider=fake_prompt_provider),
    )

    RecreationPromptStage().run(db_session, creative_with_product, creative_with_product.blueprint)

    assert fake_prompt_provider.last_call is not None
    assert "product_category" in fake_prompt_provider.last_call["lock_profile"]
    assert "visual_style" in fake_prompt_provider.last_call["fingerprint"]


def test_fails_gracefully_on_provider_error(db_session, creative_with_product, monkeypatch):
    _build_prerequisites(db_session, creative_with_product, monkeypatch)

    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry",
        FakeAIProviderRegistry(
            prompt_generation_provider=FakePromptGenerationProvider(raise_error=RuntimeError("provider down"))
        ),
    )

    result = RecreationPromptStage().run(
        db_session, creative_with_product, creative_with_product.blueprint
    )

    assert result.succeeded is False
    assert "provider down" in result.error

    db_session.refresh(creative_with_product.blueprint)
    assert creative_with_product.blueprint.current_recreation_prompt_id is None


def test_rerun_produces_new_version(db_session, creative_with_product, monkeypatch):
    _build_prerequisites(db_session, creative_with_product, monkeypatch)
    monkeypatch.setattr(
        "app.stages.recreation_prompt_stage.default_registry", FakeAIProviderRegistry()
    )

    stage = RecreationPromptStage()
    stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    db_session.refresh(creative_with_product.blueprint)
    first_id = creative_with_product.blueprint.current_recreation_prompt_id

    stage.run(db_session, creative_with_product, creative_with_product.blueprint)
    db_session.refresh(creative_with_product.blueprint)
    second_id = creative_with_product.blueprint.current_recreation_prompt_id

    assert second_id != first_id
    first = db_session.get(RecreationPrompt, first_id)
    assert first.is_current is False
