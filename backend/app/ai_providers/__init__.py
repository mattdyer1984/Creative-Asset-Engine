"""AI Provider abstraction: capability interfaces, config, and registry (plan §4)."""

from app.ai_providers.base import (
    OCRExtraction,
    OCRProvider,
    ProductIsolationProvider,
    PromptGenerationProvider,
    VisionAnalysisProvider,
)
from app.ai_providers.registry import AIProviderRegistry

# Deliberately NOT re-exporting `default_registry` here: doing so would
# eagerly trigger its construction (via registry.py's module __getattr__)
# the moment this package is imported at all - the exact import-time side
# effect this phase removes. Nothing in the codebase actually imports it
# from this package root (every Stage does `from
# app.ai_providers.registry import default_registry` directly); this was
# an unused re-export.
__all__ = [
    "OCRExtraction",
    "OCRProvider",
    "ProductIsolationProvider",
    "PromptGenerationProvider",
    "VisionAnalysisProvider",
    "AIProviderRegistry",
]
