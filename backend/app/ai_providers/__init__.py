"""AI Provider abstraction: capability interfaces, config, and registry (plan §4)."""

from app.ai_providers.base import (
    OCRExtraction,
    OCRProvider,
    ProductIsolationProvider,
    PromptGenerationProvider,
    VisionAnalysisProvider,
)
from app.ai_providers.registry import AIProviderRegistry, default_registry

__all__ = [
    "OCRExtraction",
    "OCRProvider",
    "ProductIsolationProvider",
    "PromptGenerationProvider",
    "VisionAnalysisProvider",
    "AIProviderRegistry",
    "default_registry",
]
