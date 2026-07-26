"""
Image-generation retry and failover policy.

**The defect this replaces.** `generation_engine._generate` was:

    try:
        result = image_provider.generate_image(request)
    except Exception:
        result = fallback_provider.generate_image(request)

Three problems, all of which the P1 case-02 run demonstrated:

1. **No retry.** A single transient error sent the work to GPT Image. The
   observed failure was a Gemini `503 "high demand … usually temporary"` —
   the textbook case for retrying — and the fallback cost $0.25 and 139.9 s
   against Nano Banana's 24.1 s on the call that did succeed.
2. **`except Exception` caught everything.** An invalid model name, a bad
   credential, a malformed request or a safety refusal is an integration
   defect that must stay visible. Silently producing an image from another
   provider hides it.
3. **No record of what happened.** The result carried the fallback
   provider's name, but not that a fallback had occurred, why, or how many
   retries preceded it.

So: retry the primary with exponential backoff for transient failures only,
escalate to the configured higher-quality model where one exists, and reach
the emergency provider only after the primary path has genuinely failed.
Non-transient failures are re-raised immediately and unchanged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: HTTP statuses worth retrying: the request was well-formed and the service
#: could not serve it right now.
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})

#: Substrings that identify a transient condition when no status is exposed.
#: Deliberately narrow - a broad match here would resurrect the
#: `except Exception` behaviour under a different name.
_TRANSIENT_MARKERS = (
    "unavailable", "high demand", "overloaded", "try again",
    "deadline exceeded", "timeout", "timed out", "rate limit",
    "resource has been exhausted", "internal error",
)

#: Substrings that identify a defect in OUR request. Never retried, never
#: failed over - these must reach a developer.
_PERMANENT_MARKERS = (
    "api key", "unauthenticated", "unauthorized", "permission denied",
    "not found", "invalid argument", "unsupported", "safety",
    "blocked", "malformed", "invalid model",
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 2.0


def status_of(error: Exception) -> int | None:
    for attribute in ("code", "status_code", "http_status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None


def is_transient(error: Exception) -> bool:
    """
    Should the primary provider be tried again?

    Status first, because it is unambiguous. Message matching is a fallback
    for SDKs that do not expose one, and a message naming a permanent
    condition wins over a transient-looking one.
    """
    status = status_of(error)
    if status is not None:
        return status in TRANSIENT_STATUS

    message = str(error).lower()
    if any(marker in message for marker in _PERMANENT_MARKERS):
        return False
    return any(marker in message for marker in _TRANSIENT_MARKERS)


@dataclass
class FailoverRecord:
    """What actually happened, for the result metadata and the manifest."""

    primary_provider: str
    primary_model: str
    attempts: int = 0
    transient_errors: list[str] = field(default_factory=list)
    escalated_to_model: str | None = None
    fell_back_to_provider: str | None = None
    fell_back_to_model: str | None = None
    fallback_reason: str | None = None
    final_provider: str | None = None
    final_model: str | None = None

    @property
    def used_fallback(self) -> bool:
        return self.fell_back_to_provider is not None

    def as_dict(self) -> dict:
        return {
            "primary_provider": self.primary_provider,
            "primary_model": self.primary_model,
            "attempts": self.attempts,
            "transient_errors": self.transient_errors,
            "escalated_to_model": self.escalated_to_model,
            "fell_back_to_provider": self.fell_back_to_provider,
            "fell_back_to_model": self.fell_back_to_model,
            "fallback_reason": self.fallback_reason,
            "final_provider": self.final_provider,
            "final_model": self.final_model,
        }


def generate_with_failover(
    request,
    primary,
    *,
    fallback=None,
    high_quality=None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    sleep=time.sleep,
):
    """
    Generate an image, exhausting the primary path before the fallback.

    Escalation order:
      1. primary, retried up to `max_attempts` with exponential backoff
      2. the higher-quality primary model, once, if one is configured
      3. the emergency fallback provider, once

    Returns `(result, FailoverRecord)`. A non-transient error is raised
    immediately from whichever step produced it - an integration defect must
    not be converted into a successful image from somewhere else.
    """
    record = FailoverRecord(primary_provider=primary.provider, primary_model=primary.model)

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        record.attempts = attempt
        try:
            result = primary.generate_image(request)
            record.final_provider, record.final_model = primary.provider, primary.model
            return result, record
        except Exception as exc:
            if not is_transient(exc):
                logger.error(
                    "%s/%s failed non-transiently - not retrying and not falling back",
                    primary.provider, primary.model, exc_info=True,
                )
                raise
            last_error = exc
            record.transient_errors.append(f"{type(exc).__name__}: {str(exc)[:200]}")
            logger.warning(
                "%s/%s transient failure on attempt %d/%d: %s",
                primary.provider, primary.model, attempt, max_attempts, str(exc)[:160],
            )
            if attempt < max_attempts:
                sleep(backoff_seconds * (2 ** (attempt - 1)))

    if high_quality is not None:
        try:
            logger.info(
                "escalating to the higher-quality %s model %s",
                high_quality.provider, high_quality.model,
            )
            result = high_quality.generate_image(request)
            record.escalated_to_model = high_quality.model
            record.final_provider, record.final_model = high_quality.provider, high_quality.model
            return result, record
        except Exception as exc:
            if not is_transient(exc):
                raise
            record.transient_errors.append(f"escalation: {type(exc).__name__}: {str(exc)[:160]}")

    if fallback is None:
        raise last_error if last_error else RuntimeError("image generation failed")

    record.fallback_reason = (
        f"{primary.provider}/{primary.model} failed {record.attempts} transient "
        f"attempt(s); last error: {record.transient_errors[-1][:160]}"
    )
    logger.warning(
        "falling back to %s/%s after exhausting %s: %s",
        fallback.provider, fallback.model, primary.provider, record.fallback_reason,
    )
    result = fallback.generate_image(request)
    record.fell_back_to_provider = fallback.provider
    record.fell_back_to_model = fallback.model
    record.final_provider, record.final_model = fallback.provider, fallback.model
    return result, record
