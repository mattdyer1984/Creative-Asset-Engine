"""
Unit tests for AIProviderRegistry's image_generation() and vision()
multi-provider selection. image_generation (Phase 10.1 of the AI
Creative Engine vNext, see MIGRATION_PLAN.md's ADR §10) was the first
capability accessor in this registry with more than one real adapter;
vision() gained the same provider_name override pattern later, as part
of a real-world-driven cost/quality change moving Product Lock Profile
and Creative Fingerprint to Gemini while every other vision_analysis
task stays on the configured default (see MIGRATION_PLAN.md).
"""

from app.ai_providers.config import ModelsConfig, ProvidersConfig
from app.ai_providers.gemini_adapter import GeminiOCRAdapter, GeminiVisionAnalysisAdapter
from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
from app.ai_providers.openai_adapter import (
    OpenAIImageGenerationAdapter,
    OpenAIVisionAnalysisAdapter,
)
from app.ai_providers.registry import AIProviderRegistry


def _make_registry() -> AIProviderRegistry:
    return AIProviderRegistry(providers_config=ProvidersConfig(), models_config=ModelsConfig())


def test_default_image_generation_provider_is_nano_banana_2():
    registry = _make_registry()

    provider = registry.image_generation()

    assert isinstance(provider, NanoBananaImageGenerationAdapter)
    assert provider.provider == "nano_banana"
    assert provider.model == "gemini-3.1-flash-image-preview"


def test_no_argument_returns_the_same_cached_instance_every_call():
    registry = _make_registry()

    assert registry.image_generation() is registry.image_generation()


def test_explicit_override_selects_a_different_provider():
    registry = _make_registry()

    provider = registry.image_generation("openai")

    assert isinstance(provider, OpenAIImageGenerationAdapter)
    assert provider.provider == "openai"
    assert provider.model == "gpt-image-1"


def test_explicit_override_matching_the_default_returns_the_cached_instance():
    registry = _make_registry()

    assert registry.image_generation("nano_banana") is registry.image_generation()


def test_default_ocr_provider_is_gemini_flash():
    registry = _make_registry()

    provider = registry.ocr()

    assert isinstance(provider, GeminiOCRAdapter)
    assert provider.provider == "gemini"
    assert provider.model == "gemini-flash-latest"


def test_default_vision_provider_stays_openai():
    """
    A narrower scope the user chose explicitly (see MIGRATION_PLAN.md) -
    unlike ocr, vision_analysis's DEFAULT provider stays OpenAI; only
    Product Lock Profile Stage and Creative Fingerprint Stage opt into
    Gemini via the explicit override below.
    """
    registry = _make_registry()

    provider = registry.vision()

    assert isinstance(provider, OpenAIVisionAnalysisAdapter)
    assert provider.provider == "openai"


def test_vision_no_argument_returns_the_same_cached_instance_every_call():
    registry = _make_registry()

    assert registry.vision() is registry.vision()


def test_vision_explicit_override_selects_gemini_pro():
    registry = _make_registry()

    provider = registry.vision("gemini")

    assert isinstance(provider, GeminiVisionAnalysisAdapter)
    assert provider.provider == "gemini"
    assert provider.model == "gemini-pro-latest"


def test_vision_explicit_override_matching_the_default_returns_the_cached_instance():
    registry = _make_registry()

    assert registry.vision("openai") is registry.vision()


def test_default_image_generation_fallback_is_openai():
    registry = _make_registry()

    fallback = registry.image_generation_fallback()

    assert isinstance(fallback, OpenAIImageGenerationAdapter)
    assert fallback.provider == "openai"


def test_no_fallback_configured_returns_none():
    registry = AIProviderRegistry(
        providers_config=ProvidersConfig(image_generation_fallback=None), models_config=ModelsConfig()
    )

    assert registry.image_generation_fallback() is None


def test_fallback_matching_the_primary_returns_none():
    """Nothing real to fall back to if the configured fallback names the same provider as the primary."""
    registry = AIProviderRegistry(
        providers_config=ProvidersConfig(image_generation="openai", image_generation_fallback="openai"),
        models_config=ModelsConfig(),
    )

    assert registry.image_generation_fallback() is None
