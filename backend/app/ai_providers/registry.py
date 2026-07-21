"""
AI Provider registry (plan §4.2).

Maps capability -> concrete adapter, driven by providers.yaml. A Stage
only ever asks the registry for "the current OCR provider" - it never
imports an SDK or instantiates an adapter itself. Adding a new provider
for an existing capability (e.g. Claude for OCR) is: implement
OCRProvider in a new class, add one line to OCR_ADAPTERS, flip
providers.yaml - no registry code changes.

`default_registry` (bottom of this file) is constructed lazily via a
module-level __getattr__ (PEP 562), not as a bare top-level statement -
see the comment down there for why, and app/main.py's `lifespan` for
where construction is explicitly, intentionally triggered.
"""

from app.ai_providers.base import (
    OCRProvider,
    ProductIsolationProvider,
    PromptGenerationProvider,
    TextGenerationProvider,
    VisionAnalysisProvider,
)
from app.ai_providers.config import ModelsConfig, ProvidersConfig, load_config
from app.ai_providers.openai_adapter import (
    OpenAIOCRAdapter,
    OpenAIProductIsolationAdapter,
    OpenAIPromptGenerationAdapter,
    OpenAITextGenerationAdapter,
    OpenAIVisionAnalysisAdapter,
)

OCR_ADAPTERS: dict[str, type[OCRProvider]] = {
    "openai": OpenAIOCRAdapter,
}

PRODUCT_ISOLATION_ADAPTERS: dict[str, type[ProductIsolationProvider]] = {
    "openai": OpenAIProductIsolationAdapter,
}

VISION_ANALYSIS_ADAPTERS: dict[str, type[VisionAnalysisProvider]] = {
    "openai": OpenAIVisionAnalysisAdapter,
}

TEXT_GENERATION_ADAPTERS: dict[str, type[TextGenerationProvider]] = {
    "openai": OpenAITextGenerationAdapter,
}

PROMPT_GENERATION_ADAPTERS: dict[str, type[PromptGenerationProvider]] = {
    "openai": OpenAIPromptGenerationAdapter,
}


class AIProviderRegistry:
    def __init__(
        self,
        providers_config: ProvidersConfig | None = None,
        models_config: ModelsConfig | None = None,
    ):
        if providers_config is None or models_config is None:
            loaded_providers, loaded_models = load_config()
            providers_config = providers_config or loaded_providers
            models_config = models_config or loaded_models

        self._ocr: OCRProvider = self._build(
            OCR_ADAPTERS, providers_config.ocr, models_config, "ocr"
        )
        self._isolation: ProductIsolationProvider = self._build(
            PRODUCT_ISOLATION_ADAPTERS,
            providers_config.product_isolation,
            models_config,
            "product_isolation",
        )
        self._vision: VisionAnalysisProvider = self._build(
            VISION_ANALYSIS_ADAPTERS,
            providers_config.vision_analysis,
            models_config,
            "vision_analysis",
        )
        self._text_generation: TextGenerationProvider = self._build(
            TEXT_GENERATION_ADAPTERS,
            providers_config.text_generation,
            models_config,
            "text_generation",
        )
        self._prompt_generation: PromptGenerationProvider = self._build(
            PROMPT_GENERATION_ADAPTERS,
            providers_config.prompt_generation,
            models_config,
            "prompt_generation",
        )

    @staticmethod
    def _build(adapters: dict, provider_name: str, models_config: ModelsConfig, capability: str):
        model = getattr(models_config, provider_name, {}).get(capability, "gpt-5.5")
        return adapters[provider_name](model=model, provider=provider_name)

    def ocr(self) -> OCRProvider:
        return self._ocr

    def isolation(self) -> ProductIsolationProvider:
        return self._isolation

    def vision(self) -> VisionAnalysisProvider:
        return self._vision

    def text_generation(self) -> TextGenerationProvider:
        return self._text_generation

    def prompt_generation(self) -> PromptGenerationProvider:
        return self._prompt_generation


# Module-level default instance - Stages import this rather than each
# constructing their own registry, so config is loaded once per process.
#
# Built lazily (on first access to the name `default_registry`, via the
# module __getattr__ below - PEP 562) rather than as a bare
# `default_registry = AIProviderRegistry()` statement, so merely
# *importing* this module (e.g. for the AIProviderRegistry class itself,
# or transitively via some import chain that never actually needs the
# singleton) no longer has the side effect of reading providers.yaml and
# constructing five adapters. app/main.py's `lifespan` explicitly touches
# `default_registry` on app startup as the intentional, documented
# trigger point for that construction.
#
# Every Stage still does `from app.ai_providers.registry import
# default_registry` exactly as before - that statement itself invokes
# this __getattr__ (Python's `from module import name` performs a
# getattr(module, name), which module-level __getattr__ intercepts), so
# no Stage or test file needed to change: each Stage's own
# `default_registry` name still ends up bound to this same cached
# instance, and `monkeypatch.setattr("app.stages.<x>.default_registry",
# ...)` continues to work exactly as it does today.
_default_registry: AIProviderRegistry | None = None


def __getattr__(name: str) -> AIProviderRegistry:
    if name == "default_registry":
        global _default_registry
        if _default_registry is None:
            _default_registry = AIProviderRegistry()
        return _default_registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
