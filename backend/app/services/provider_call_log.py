"""
Recording billable provider calls (Phase 1 remediation, WP-2).

One function, `record_provider_call`, used by every paid AI call in the
codebase so spend has a single, complete calculation path. Before this,
four modules made real paid calls that created no record whatsoever -
photorealism scoring, reference scoring, creative intelligence and text
intelligence were entirely invisible to cost and timing reporting.

Deliberately best-effort: a failure to record telemetry must never lose
a real result the user already paid for. Any exception is logged and
swallowed. The alternative - letting a bookkeeping bug destroy a
successful generation - would be strictly worse than an incomplete cost
report.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.provider_call import RECORD_SOURCE_PER_CALL, ProviderCall
from app.services.cost_estimation import (
    CostEstimate,
    CostStatus,
    estimate_image_cost,
    estimate_token_cost,
    reported_model_for,
    resolve_billing_model,
)

logger = logging.getLogger(__name__)


def record_provider_call(
    db: Session,
    *,
    provider: str,
    model: str,
    capability: str,
    usage: dict | None = None,
    image_count: int | None = None,
    provider_latency_ms: float | None = None,
    analysis_run_id: str | None = None,
    generated_image_id: str | None = None,
    slide_id: str | None = None,
    slideshow_id: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
    prompt_content_hash: str | None = None,
) -> ProviderCall | None:
    """
    Records one billable call. Returns the row, or None if recording
    failed (never raises - see module docstring).

    `usage` is the same dict the adapters already populate via their
    `usage_sink` parameter. `image_count` marks an image-billed call;
    the two are mutually exclusive in practice, and which one is given
    decides how cost is computed.
    """
    try:
        prompt_tokens = (usage or {}).get("prompt_tokens")
        completion_tokens = (usage or {}).get("completion_tokens")

        # Follow-up to Checkpoint B (item 2): price against what the
        # provider says it actually served, not the alias we asked for.
        # `reported_model` comes from the response itself (the adapters
        # put it in usage_sink); the pricing.yaml value is only a
        # fallback for providers that do not report one.
        resolved_model = (usage or {}).get("reported_model") or reported_model_for(provider, model)
        billing_model, mismatch_reason = resolve_billing_model(
            provider, model, resolved_model
        )

        if image_count is not None:
            estimate = estimate_image_cost(provider, billing_model, image_count=image_count)
        else:
            estimate = estimate_token_cost(
                provider, billing_model, prompt_tokens, completion_tokens
            )

        # An alias that moved must read as unknown, never as a stale
        # rate - silently reusing the old price is exactly how a repoint
        # would go unnoticed.
        if mismatch_reason:
            estimate = CostEstimate(None, CostStatus.UNKNOWN, mismatch_reason)

        call = ProviderCall(
            provider=provider,
            model=model,
            reported_model=resolved_model,
            capability=capability,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_content_hash=prompt_content_hash,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            image_count=image_count,
            provider_latency_ms=provider_latency_ms,
            estimated_cost_usd=estimate.amount_usd,
            cost_status=str(estimate.status),
            cost_status_reason=estimate.reason,
            record_source=RECORD_SOURCE_PER_CALL,
            analysis_run_id=analysis_run_id,
            generated_image_id=generated_image_id,
            slide_id=slide_id,
            slideshow_id=slideshow_id,
        )
        db.add(call)
        db.flush()
        return call
    except Exception:
        # Telemetry must never cost the user a paid result.
        logger.exception(
            "Failed to record ProviderCall for %s/%s (%s) - the call itself was unaffected",
            provider,
            model,
            capability,
        )
        return None


def unknown_cost_reason(call: ProviderCall) -> str | None:
    """Convenience for reporting - why a row's cost cannot be trusted."""
    if call.cost_status in (CostStatus.EXACT, CostStatus.ESTIMATED):
        return None
    return call.cost_status_reason
