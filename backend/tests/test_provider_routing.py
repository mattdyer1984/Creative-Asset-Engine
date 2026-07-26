"""
Role-based provider routing.

The audit found that the intended architecture existed only as prose in a
config comment, so three stages added later inherited the OpenAI default
because nobody re-decided. Roles make the intent explicit and checkable.
"""

import pathlib

import pytest
import yaml

from app.ai_providers.routing import (
    INTENDED,
    ROLES,
    RoutingConfigError,
    load_routing,
)

PROVIDERS_YAML = pathlib.Path(__file__).resolve().parents[1] / "providers.yaml"


def _configured() -> dict:
    return yaml.safe_load(PROVIDERS_YAML.read_text()).get("routing")


def test_the_shipped_configuration_declares_every_role():
    policy = load_routing(_configured())
    assert set(policy.roles) == set(ROLES)


def test_the_shipped_configuration_matches_the_intended_architecture():
    """
    The regression this exists to prevent: a role quietly moving to a
    provider the architecture did not intend.
    """
    assert load_routing(_configured()).drift() == {}


@pytest.mark.parametrize("role,provider", sorted(INTENDED.items()))
def test_each_role_resolves_to_its_intended_provider(role, provider):
    assert load_routing(_configured()).provider_for(role) == provider


def test_a_missing_routing_block_fails_loudly():
    with pytest.raises(RoutingConfigError, match="no `routing:` block"):
        load_routing(None)


def test_an_unset_role_fails_rather_than_taking_a_default():
    """
    Silently substituting a default is how OpenAI came to handle more of the
    pipeline than intended.
    """
    partial = {k: v for k, v in INTENDED.items() if k != "visual_analysis_provider"}
    with pytest.raises(RoutingConfigError, match="not configured"):
        load_routing(partial)


def test_an_unknown_role_is_refused():
    with pytest.raises(RoutingConfigError, match="unknown routing role"):
        load_routing({**INTENDED, "wishful_thinking_provider": "gemini"})


def test_an_unknown_provider_is_refused():
    with pytest.raises(RoutingConfigError, match="unknown provider"):
        load_routing({**INTENDED, "visual_analysis_provider": "definitely-not-a-provider"})


def test_drift_is_reported_with_both_values():
    policy = load_routing({**INTENDED, "visual_analysis_provider": "openai"})
    assert policy.drift() == {"visual_analysis_provider": ("openai", "gemini")}


def test_image_generation_never_defaults_to_the_fallback_provider():
    """
    GPT Image is an emergency provider, not the normal generator.
    """
    policy = load_routing(_configured())
    assert policy.provider_for("primary_image_provider") == "nano_banana"
    assert policy.provider_for("fallback_image_provider") != \
        policy.provider_for("primary_image_provider")
