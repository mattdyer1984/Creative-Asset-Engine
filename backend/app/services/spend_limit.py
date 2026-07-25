"""
Daily spend limit (Phase 1 remediation, WP-5).

**A soft cap, and the docstring says so because the behaviour genuinely
is soft.** The check happens once, before a unit of paid work starts.
Work already in flight always runs to completion. So total spend can
exceed the cap by at most the cost of one unit - a slideshow analysis or
one generation call. That is a deliberate trade, not an oversight:
aborting halfway through a candidate batch would leave the user having
paid for provider calls that produced no usable result, which is worse
than a bounded overshoot.

**What it guards.** New paid work only:
  * a full slideshow analysis (POST /analyze)
  * an explicit paid stage rerun
  * image generation
Read-only endpoints, blueprint reads, listings, and anything served from
existing data are never blocked - they cost nothing, so capping them
would be pure friction.

**Day boundary.** The user's LOCAL calendar day, not UTC. A cap that
resets at 01:00 local time because the server thinks in UTC would be
astonishing to the person reading the number.

**What counts toward spend.** Only ProviderCall rows with a trusted cost
(estimated/exact). Rows whose cost is partial or unknown cannot be
summed honestly - counting them as 0 would let real spend run past the
cap invisibly, so `spend_snapshot` reports them separately and the
caller can see the total is a floor, not a certainty.

**Unknown cost must never behave like zero (follow-up to Checkpoint B,
item 1).** The primary image provider is currently unpriced, which is
the most expensive part of the workflow - so an "active" cap that let
unpriced generation through would be protection in name only. The
policy, in full:

  * Cap DISABLED -> unpriced work proceeds. Nothing is being enforced,
    so refusing would be pure friction. The calls are still recorded and
    reported as unknown.
  * Cap ENABLED, work IS priceable -> normal behaviour: proceed unless
    already at the cap.
  * Cap ENABLED, work is NOT priceable, and a conservative ceiling IS
    configured for that provider/capability -> proceed, but RESERVE the
    ceiling against today's budget, so an unpriceable call still
    consumes budget rather than being free.
  * Cap ENABLED, work is NOT priceable, and no ceiling is configured ->
    FAIL CLOSED with a 429 that says the cost could not be estimated
    safely. This is the case that would otherwise silently bypass the
    cap entirely.

Ceilings are deliberately per provider+capability and must be set by a
human in providers.yaml. Nothing here infers a price.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_providers.config import PROVIDERS_YAML_PATH
from app.models.provider_call import ProviderCall
from app.services.cost_estimation import CostStatus, has_usable_rate

_TRUSTED = {str(CostStatus.EXACT), str(CostStatus.ESTIMATED)}


@dataclass(frozen=True)
class SpendSnapshot:
    cap_usd: float | None
    spent_usd: float
    calls_with_untrusted_cost: int
    resets_at: datetime

    @property
    def is_over_cap(self) -> bool:
        return self.cap_usd is not None and self.spent_usd >= self.cap_usd

    @property
    def remaining_usd(self) -> float | None:
        if self.cap_usd is None:
            return None
        return max(self.cap_usd - self.spent_usd, 0.0)


def load_daily_cap_usd(path=PROVIDERS_YAML_PATH) -> float | None:
    """
    Reads `spend_limits.daily_usd` from providers.yaml. None (or absent)
    means no cap - the default, so this cannot start blocking work just
    because the feature shipped.
    """
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text()) or {}
    value = (raw.get("spend_limits") or {}).get("daily_usd")
    return float(value) if value is not None else None


def load_unknown_cost_ceilings(path=PROVIDERS_YAML_PATH) -> dict[str, dict[str, float]]:
    """
    `spend_limits.unknown_cost_ceilings_usd[provider][capability]` - a
    human-set conservative upper bound used ONLY to let an unpriceable
    call proceed under an enabled cap, by reserving that amount against
    the budget. Absent = no ceiling = that work fails closed.
    """
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    ceilings = (raw.get("spend_limits") or {}).get("unknown_cost_ceilings_usd") or {}
    return {
        provider: {cap: float(v) for cap, v in caps.items() if v is not None}
        for provider, caps in ceilings.items()
        if isinstance(caps, dict)
    }


def _local_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Start of the current LOCAL calendar day, and the next one."""
    current = now or datetime.now()
    start = datetime.combine(current.date(), time.min)
    return start, start + timedelta(days=1)


def spend_snapshot(
    db: Session, *, now: datetime | None = None, cap_usd: float | None = None
) -> SpendSnapshot:
    cap = cap_usd if cap_usd is not None else load_daily_cap_usd()
    start, end = _local_day_bounds(now)

    spent = 0.0
    untrusted = 0
    for call in db.scalars(
        select(ProviderCall).where(
            ProviderCall.created_at >= start, ProviderCall.created_at < end
        )
    ):
        if call.cost_status in _TRUSTED and call.estimated_cost_usd is not None:
            spent += call.estimated_cost_usd
        else:
            untrusted += 1

    return SpendSnapshot(
        cap_usd=cap,
        spent_usd=round(spent, 6),
        calls_with_untrusted_cost=untrusted,
        resets_at=end,
    )


@dataclass(frozen=True)
class PlannedCall:
    """One provider call a pending operation is about to make."""

    provider: str
    model: str
    capability: str
    billing: str = "token"  # "token" | "image"


def check_spend_allowed(
    db: Session,
    *,
    planned: "Sequence[PlannedCall]" = (),
    estimated_unit_cost_usd: float | None = None,
    now: datetime | None = None,
    cap_usd: float | None = None,
    ceilings: dict | None = None,
) -> SpendSnapshot:
    """
    Call ONCE, before starting a unit of paid work.

    Raises `SpendLimitExceeded` when the cap is already reached, or
    `UnpricedWorkRefused` when the cap is enabled but the work about to
    run cannot be priced and has no configured ceiling (see the module
    docstring for the full policy).

    `planned` describes the provider calls the operation will make. It
    is what makes the unknown-cost policy possible: without it we could
    only check spend AFTER the fact, by which point unpriced work has
    already bypassed the cap.

    Deliberately checks "already at/over the cap" for priced work rather
    than forecasting whether this unit would exceed it - a per-unit
    forecast needs rates we honestly do not have for every model. The
    bounded overshoot that allows is documented; silently letting
    unpriceable work through is not acceptable, which is why that case
    fails closed instead.
    """
    snapshot = spend_snapshot(db, now=now, cap_usd=cap_usd)

    # Cap disabled: nothing is being enforced, so unpriced work proceeds.
    # It is still recorded and reported as unknown.
    if snapshot.cap_usd is None:
        return snapshot

    if snapshot.is_over_cap:
        raise SpendLimitExceeded(snapshot, estimated_unit_cost_usd)

    configured = load_unknown_cost_ceilings() if ceilings is None else ceilings
    unpriceable: list[PlannedCall] = []
    reserved = 0.0

    for call in planned:
        if has_usable_rate(call.provider, call.model, billing=call.billing):
            continue
        ceiling = (configured.get(call.provider) or {}).get(call.capability)
        if ceiling is None:
            unpriceable.append(call)
        else:
            reserved += ceiling

    if unpriceable:
        raise UnpricedWorkRefused(snapshot, unpriceable)

    # An unpriceable-but-ceilinged call still has to consume budget,
    # otherwise it is free in all but name.
    if reserved and snapshot.spent_usd + reserved > snapshot.cap_usd:
        raise SpendLimitExceeded(snapshot, reserved)

    return snapshot


class SpendLimitExceeded(Exception):
    """Raised before any paid work starts - never mid-unit."""

    def __init__(self, snapshot: SpendSnapshot, estimated_unit_cost_usd: float | None = None):
        self.snapshot = snapshot
        self.estimated_unit_cost_usd = estimated_unit_cost_usd
        super().__init__(
            f"Daily spend cap of ${snapshot.cap_usd:.2f} reached "
            f"(${snapshot.spent_usd:.4f} spent today)."
        )

    def to_detail(self) -> dict:
        """The 429 body - everything WP-5 requires the caller to be told."""
        detail = {
            "error": "daily_spend_cap_reached",
            "message": str(self),
            "cap_usd": self.snapshot.cap_usd,
            "spent_today_usd": self.snapshot.spent_usd,
            "estimated_unit_cost_usd": self.estimated_unit_cost_usd,
            "resets_at": self.snapshot.resets_at.isoformat(),
            "resets_at_note": "local calendar day",
        }
        if self.snapshot.calls_with_untrusted_cost:
            detail["note"] = (
                f"{self.snapshot.calls_with_untrusted_cost} call(s) today have a partial or "
                "unknown cost and are NOT included in spent_today_usd - real spend is at "
                "least this figure, possibly higher."
            )
        return detail


class UnpricedWorkRefused(Exception):
    """
    Raised when the cap is ENABLED but the work about to run cannot be
    priced and has no configured conservative ceiling (follow-up to
    Checkpoint B, item 1).

    This is the case that would otherwise silently bypass the cap: the
    primary image provider is currently unpriced, so without this an
    "active" cap would not protect the most expensive part of the
    workflow at all. Failing closed is the honest behaviour - the
    alternative is presenting protection that does not exist.
    """

    def __init__(self, snapshot: SpendSnapshot, unpriceable: "Sequence[PlannedCall]"):
        self.snapshot = snapshot
        self.unpriceable = list(unpriceable)
        described = ", ".join(
            f"{c.provider}/{c.model} ({c.capability})" for c in self.unpriceable
        )
        super().__init__(
            "Refusing to start paid work whose cost cannot be estimated while a daily "
            f"spend cap is enabled: {described}."
        )

    def to_detail(self) -> dict:
        return {
            "error": "unpriced_work_refused",
            "message": str(self),
            "reason": (
                "A daily spend cap is enabled, but this operation would call a "
                "provider/model with no configured rate, so its cost could not be "
                "counted against the cap. Allowing it would let spend bypass the cap "
                "entirely."
            ),
            "cap_usd": self.snapshot.cap_usd,
            "spent_today_usd": self.snapshot.spent_usd,
            "resets_at": self.snapshot.resets_at.isoformat(),
            "resets_at_note": "local calendar day",
            "unpriceable_calls": [
                {
                    "provider": c.provider,
                    "model": c.model,
                    "capability": c.capability,
                }
                for c in self.unpriceable
            ],
            "how_to_resolve": (
                "Either add a real rate for these models to pricing.yaml (official "
                "provider documentation or a verified billing line item only), or set a "
                "conservative upper bound under spend_limits.unknown_cost_ceilings_usd "
                "in providers.yaml so the call reserves that amount against the cap. "
                "Disabling the cap also allows it, but then nothing is enforced."
            ),
        }
