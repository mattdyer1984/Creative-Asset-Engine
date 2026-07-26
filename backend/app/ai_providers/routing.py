"""
Role-based provider routing.

The capability map in `providers.yaml` says which adapter serves each
technical capability. It does not say *why*, so the intended architecture had
to be inferred from which call sites happened to pass an override - and the
audit found that three stages added after the partial Gemini migration
silently inherited the OpenAI default because nobody re-decided.

Roles make the intent explicit and checkable:

    visual_analysis         multimodal understanding - cheaper, adequate
    structured_reasoning    strict schemas, adjudication, compilation
    primary_image           the normal generator
    high_quality_image      escalation within the primary provider
    fallback_image          emergency only
    visual_validation       post-generation visual checks
    policy_validation       final adjudication, with local rules

**Unknown or missing configuration fails loudly.** Silently substituting a
default is exactly how OpenAI came to handle more of the pipeline than
intended.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLES = (
    "visual_analysis_provider",
    "structured_reasoning_provider",
    "primary_image_provider",
    "high_quality_image_provider",
    "fallback_image_provider",
    "visual_validation_provider",
    "policy_validation_provider",
)

#: The architecture's intent, used to report drift. Not a fallback - a role
#: missing from configuration raises rather than quietly taking this value.
INTENDED = {
    "visual_analysis_provider": "gemini",
    "structured_reasoning_provider": "openai",
    "primary_image_provider": "nano_banana",
    "high_quality_image_provider": "nano_banana",
    "fallback_image_provider": "openai",
    "visual_validation_provider": "gemini",
    "policy_validation_provider": "openai",
}

KNOWN_PROVIDERS = frozenset({"openai", "gemini", "nano_banana"})


class RoutingConfigError(ValueError):
    """Routing configuration that cannot be trusted to mean what it says."""


@dataclass(frozen=True)
class RoutingPolicy:
    roles: dict[str, str]

    def provider_for(self, role: str) -> str:
        if role not in ROLES:
            raise RoutingConfigError(f"unknown routing role {role!r}; known: {sorted(ROLES)}")
        provider = self.roles.get(role)
        if provider is None:
            raise RoutingConfigError(
                f"routing role {role!r} is not configured. Set it in providers.yaml "
                "under `routing:` - an unset role must not silently take a default"
            )
        return provider

    def drift(self) -> dict[str, tuple[str, str]]:
        """role -> (configured, intended) for every role that differs."""
        return {
            role: (self.roles[role], INTENDED[role])
            for role in ROLES
            if role in self.roles and self.roles[role] != INTENDED[role]
        }


def load_routing(raw: dict | None) -> RoutingPolicy:
    """
    Build the policy from the `routing:` block, validating every entry.

    An unrecognised role or provider raises: a typo that resolved to a
    default would reintroduce exactly the silent-substitution problem this
    module exists to prevent.
    """
    if not raw:
        raise RoutingConfigError(
            "providers.yaml has no `routing:` block. Provider roles must be "
            "declared explicitly - see app/ai_providers/routing.py"
        )

    unknown_roles = sorted(set(raw) - set(ROLES))
    if unknown_roles:
        raise RoutingConfigError(f"unknown routing role(s): {unknown_roles}")

    missing = sorted(set(ROLES) - set(raw))
    if missing:
        raise RoutingConfigError(f"routing role(s) not configured: {missing}")

    bad = {role: value for role, value in raw.items() if value not in KNOWN_PROVIDERS}
    if bad:
        raise RoutingConfigError(
            f"routing names unknown provider(s): {bad}. Known: {sorted(KNOWN_PROVIDERS)}"
        )

    return RoutingPolicy(roles=dict(raw))
