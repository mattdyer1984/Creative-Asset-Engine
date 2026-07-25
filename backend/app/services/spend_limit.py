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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_providers.config import PROVIDERS_YAML_PATH
from app.models.provider_call import ProviderCall
from app.services.cost_estimation import CostStatus

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


def check_spend_allowed(
    db: Session,
    *,
    estimated_unit_cost_usd: float | None = None,
    now: datetime | None = None,
    cap_usd: float | None = None,
) -> SpendSnapshot:
    """
    Call ONCE, before starting a unit of paid work. Raises
    `SpendLimitExceeded` when the cap is already reached.

    Deliberately checks "already at/over the cap", not "would this unit
    push us over" - the latter needs a reliable per-unit cost estimate,
    and several models are honestly priced `unknown` today (see
    pricing.yaml). Blocking on a guessed forecast would be worse than a
    bounded overshoot. `estimated_unit_cost_usd` is carried into the
    error for the caller's benefit when it happens to be known.
    """
    snapshot = spend_snapshot(db, now=now, cap_usd=cap_usd)
    if snapshot.is_over_cap:
        raise SpendLimitExceeded(snapshot, estimated_unit_cost_usd)
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
