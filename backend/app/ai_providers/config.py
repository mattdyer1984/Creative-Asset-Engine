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
    image_generation: str = "openai"


class ModelsConfig(BaseModel):
    # provider name -> {capability: model_name}
    openai: dict[str, str] = {
        "ocr": "gpt-5.5",
        "product_isolation": "gpt-5.5",
        "vision_analysis": "gpt-5.5",
        "text_generation": "gpt-5.5",
        "prompt_generation": "gpt-5.5",
        "image_generation": "gpt-5.5",
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
