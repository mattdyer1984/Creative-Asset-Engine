"""
Unit tests for AIProviderRegistry's image_generation() multi-provider
selection (Phase 10.1 of the AI Creative Engine vNext, see
MIGRATION_PLAN.md's ADR §10) - the first capability accessor in this
registry with more than one real adapter.
"""

from app.ai_providers.config import ModelsConfig, ProvidersConfig
from app.ai_providers.nano_banana_adapter import NanoBananaImageGenerationAdapter
from app.ai_providers.openai_adapter import OpenAIImageGenerationAdapter
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
