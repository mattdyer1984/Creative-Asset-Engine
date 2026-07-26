"""
Image-generation retry and failover policy.

The P1 case-02 run showed GPT Image behaving as the effective default: a
single Gemini `503 "high demand ... usually temporary"` sent the work
straight to the fallback, at $0.25 and 139.9s against Nano Banana's 24.1s on
the call that succeeded. The old code caught `Exception` with no retry.
"""

import pytest

from app.ai_providers.failover import (
    TRANSIENT_STATUS,
    generate_with_failover,
    is_transient,
    status_of,
)


class _Provider:
    def __init__(self, provider, model, errors=None, result="image"):
        self.provider, self.model = provider, model
        self._errors = list(errors or [])
        self._result = result
        self.calls = 0

    def generate_image(self, request):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return self._result


class _Status(Exception):
    def __init__(self, code, message="service says no"):
        super().__init__(message)
        self.code = code


@pytest.mark.parametrize("code", sorted(TRANSIENT_STATUS))
def test_transient_statuses_are_recognised(code):
    assert is_transient(_Status(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
def test_client_errors_are_not_transient(code):
    assert not is_transient(_Status(code))


@pytest.mark.parametrize("message", [
    "503 UNAVAILABLE. This model is currently experiencing high demand.",
    "The model is overloaded, please try again later",
    "Deadline exceeded",
])
def test_transient_messages_are_recognised_without_a_status(message):
    assert is_transient(Exception(message))


@pytest.mark.parametrize("message", [
    "API key not valid", "PERMISSION_DENIED", "invalid model name",
    "blocked by safety settings", "Invalid argument: malformed request",
])
def test_our_own_defects_are_never_transient(message):
    """
    These must reach a developer. Producing an image from another provider
    would hide an integration defect behind an apparent success.
    """
    assert not is_transient(Exception(message))


def test_a_permanent_message_beats_a_transient_looking_one():
    assert not is_transient(Exception("invalid model name, please try again"))


def test_the_happy_path_makes_one_call():
    primary = _Provider("nano_banana", "flash")
    result, record = generate_with_failover(object(), primary)
    assert result == "image" and primary.calls == 1
    assert record.attempts == 1 and not record.used_fallback
    assert record.final_provider == "nano_banana"


def test_a_transient_error_is_retried_before_any_fallback():
    """The defect this policy exists to fix."""
    primary = _Provider("nano_banana", "flash", errors=[_Status(503)])
    fallback = _Provider("openai", "gpt-image-1")
    result, record = generate_with_failover(
        object(), primary, fallback=fallback, sleep=lambda _s: None
    )
    assert primary.calls == 2, "the primary must be retried"
    assert fallback.calls == 0, "the fallback must not be reached"
    assert record.attempts == 2 and not record.used_fallback


def test_the_fallback_is_reached_only_after_the_primary_is_exhausted():
    primary = _Provider("nano_banana", "flash",
                        errors=[_Status(503), _Status(503), _Status(503)])
    fallback = _Provider("openai", "gpt-image-1")
    result, record = generate_with_failover(
        object(), primary, fallback=fallback, max_attempts=3, sleep=lambda _s: None
    )
    assert primary.calls == 3 and fallback.calls == 1
    assert record.used_fallback
    assert record.final_provider == "openai"
    assert "3 transient attempt" in record.fallback_reason


def test_a_non_transient_error_raises_and_never_falls_back():
    """
    An invalid model or a bad credential must stay visible. The old code
    turned both into a successful image from a different provider.
    """
    primary = _Provider("nano_banana", "flash", errors=[Exception("API key not valid")])
    fallback = _Provider("openai", "gpt-image-1")
    with pytest.raises(Exception, match="API key not valid"):
        generate_with_failover(object(), primary, fallback=fallback, sleep=lambda _s: None)
    assert fallback.calls == 0


def test_escalation_to_the_higher_quality_model_precedes_the_fallback():
    primary = _Provider("nano_banana", "flash", errors=[_Status(503), _Status(503)])
    high = _Provider("nano_banana", "pro")
    fallback = _Provider("openai", "gpt-image-1")
    _, record = generate_with_failover(
        object(), primary, fallback=fallback, high_quality=high,
        max_attempts=2, sleep=lambda _s: None,
    )
    assert high.calls == 1 and fallback.calls == 0
    assert record.escalated_to_model == "pro"
    assert record.final_provider == "nano_banana", "still the Google path"


def test_backoff_is_exponential_and_bounded():
    delays = []
    primary = _Provider("nano_banana", "flash",
                        errors=[_Status(503), _Status(503), _Status(503)])
    fallback = _Provider("openai", "gpt-image-1")
    generate_with_failover(object(), primary, fallback=fallback, max_attempts=3,
                           backoff_seconds=1.0, sleep=delays.append)
    assert delays == [1.0, 2.0], "one sleep between attempts, doubling, none after the last"


def test_every_fallback_is_recorded_for_the_result_metadata():
    """
    The UI and the manifest must be able to say which provider actually
    produced the image, and why.
    """
    primary = _Provider("nano_banana", "flash", errors=[_Status(429), _Status(503)])
    fallback = _Provider("openai", "gpt-image-1")
    _, record = generate_with_failover(object(), primary, fallback=fallback,
                                       max_attempts=2, sleep=lambda _s: None)
    data = record.as_dict()
    for field in ("primary_provider", "primary_model", "attempts",
                  "transient_errors", "fell_back_to_provider",
                  "fallback_reason", "final_provider", "final_model"):
        assert field in data
    assert len(data["transient_errors"]) == 2


def test_with_no_fallback_configured_the_original_error_surfaces():
    primary = _Provider("nano_banana", "flash", errors=[_Status(503)])
    with pytest.raises(_Status):
        generate_with_failover(object(), primary, max_attempts=1, sleep=lambda _s: None)


def test_status_is_read_from_common_sdk_attributes():
    assert status_of(_Status(503)) == 503
    class _Alt(Exception):
        status_code = 429
    assert status_of(_Alt()) == 429
    assert status_of(Exception("no status")) is None
