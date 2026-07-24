"""
AI Provider config: which provider/model backs each capability, and how
credentials are looked up (plan §4.2, §4.6).
"""

import os
from pathlib import Path

import keyring
import yaml
from pydantic import BaseModel

PROVIDERS_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "providers.yaml"

KEYRING_SERVICE_NAME = "creative-asset-engine"


class ProvidersConfig(BaseModel):
    # One field per capability - all 5 of the plan's AI capabilities now
    # present (ocr, product_isolation, vision_analysis added in M4;
    # text_generation in M5; prompt_generation in M6), plus a 6th,
    # image_generation, added in Phase 8.2 of the Generation -> Validation
    # proof of loop (see MIGRATION_PLAN.md) - the one capability that
    # produces an image rather than analyzing one.
    ocr: str = "openai"
    product_isolation: str = "openai"
    vision_analysis: str = "openai"
    text_generation: str = "openai"
    prompt_generation: str = "openai"
    # Phase 10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's
    # ADR §10) - Nano Banana Lite is the default, an implementation
    # choice made explicit here and in providers.yaml, not an
    # architectural one; OpenAI's adapter stays fully registered and
    # selectable (registry.image_generation("openai")) without any code
    # change to switch back.
    image_generation: str = "nano_banana"


class ModelsConfig(BaseModel):
    # provider name -> {capability: model_name}
    openai: dict[str, str] = {
        "ocr": "gpt-5.5",
        "product_isolation": "gpt-5.5",
        "vision_analysis": "gpt-5.5",
        "text_generation": "gpt-5.5",
        "prompt_generation": "gpt-5.5",
        # "gpt-5.5" is not a real OpenAI model (confirmed via a real 400
        # from OpenAI's Images API during Phase 8.3's live verification -
        # providers.yaml was fixed at the time, but this Pydantic-level
        # default was missed, a latent inconsistency only harmless
        # because providers.yaml always overrides it in real app
        # startup via load_config() - found and fixed here while adding
        # the nano_banana entry alongside it (Phase 10.1).
        "image_generation": "gpt-image-1",
    }
    # Phase 10.1 of the AI Creative Engine vNext (see MIGRATION_PLAN.md's
    # ADR §10) - the first second-provider entry in this config. Only
    # image_generation is populated since NanoBananaImageGenerationAdapter
    # is the only capability with a real Nano Banana implementation;
    # ProvidersConfig.image_generation stays "openai" by default (not
    # switched here) - selecting nano_banana is a deliberate choice made
    # via providers.yaml or an explicit registry.image_generation("nano_banana")
    # call, never silent.
    nano_banana: dict[str, str] = {
        # "Nano Banana 2" (general-purpose tier), not the Lite tier -
        # switched after the Lite tier was diagnosed as the real cause
        # of near-universal branding_text validation failures (see
        # providers.yaml's own comment and MIGRATION_PLAN.md).
        "image_generation": "gemini-3.1-flash-image-preview",
    }


def load_config(path: Path = PROVIDERS_YAML_PATH) -> tuple[ProvidersConfig, ModelsConfig]:
    if not path.exists():
        # Sensible defaults if providers.yaml is missing, rather than
        # failing to start - this is a local single-user app, not a
        # deployed service where missing config should be a hard error.
        return ProvidersConfig(), ModelsConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return (
        ProvidersConfig(**raw.get("providers", {})),
        ModelsConfig(**raw.get("models", {})),
    )


def get_api_key(provider: str) -> str:
    """
    Looks up the API key for `provider` from the macOS Keychain first,
    falling back to a <PROVIDER>_API_KEY environment variable - the
    keychain is the primary mechanism (plan §4.6), the env var exists so
    local development/testing doesn't require setting up the keychain
    just to run a quick script.

    keyring.get_password() can raise (not just return None) if no
    backend is configured at all - caught here so the env var fallback
    still runs in that case, rather than surfacing a confusing keyring
    internals error for what is, from the caller's perspective, simply
    "no key configured yet."
    """
    try:
        key = keyring.get_password(KEYRING_SERVICE_NAME, f"{provider}_api_key")
    except Exception:
        key = None

    if key:
        return key

    env_key = os.environ.get(f"{provider.upper()}_API_KEY")
    if env_key:
        return env_key

    raise RuntimeError(
        f"No API key found for provider '{provider}'. Set one via:\n"
        f"  keyring.set_password('{KEYRING_SERVICE_NAME}', '{provider}_api_key', '<your key>')\n"
        f"or by setting the {provider.upper()}_API_KEY environment variable."
    )
