"""
Spend forecasting and run-level controls (P3).

The existing `spend_limit` answers *may this call proceed?* one call at a
time. An operator needs a different question answered **before** anything is
spent: *what will this run cost, and do I want to authorise it?*

Three controls, and the distinction between them matters:

    daily cap    a soft ceiling. Work already running finishes; the next
                 unit is refused. Overshoot is bounded by one unit.
    hard stop    an absolute ceiling. Nothing starts that could cross it,
                 even if that means refusing a run outright.
    dry run      forecast and report; make no provider call at all.

**Estimates are forecasts and are labelled as such.** A forecast built from
historical medians is not a quote, and reporting it as one is how an
"estimate" becomes a number nobody checks. Every forecast carries how many
calls it could not price, and a forecast with unpriced calls is reported as
incomplete rather than as a smaller number.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_run import AnalysisRun
from app.models.provider_call import ProviderCall


@dataclass(frozen=True)
class StageForecast:
    """What one stage is expected to cost, and how well we know."""

    stage: str
    calls: int
    known_usd: float | None
    unpriced_calls: int
    samples: int
    basis: str

    @property
    def is_priceable(self) -> bool:
        return self.known_usd is not None and self.unpriced_calls == 0


@dataclass
class RunForecast:
    """
    A forecast for a whole run, never collapsed into one number when part
    of it is unknown.
    """

    stages: list[StageForecast] = field(default_factory=list)
    slides: int = 1

    @property
    def known_subtotal_usd(self) -> float:
        return round(sum(s.known_usd or 0.0 for s in self.stages), 6)

    @property
    def unpriced_calls(self) -> int:
        return sum(s.unpriced_calls for s in self.stages)

    @property
    def is_complete(self) -> bool:
        return self.unpriced_calls == 0

    @property
    def headline(self) -> str:
        """
        The one line an operator reads. Deliberately refuses to state a
        total when part of the run cannot be priced.
        """
        if self.is_complete:
            return f"estimated ${self.known_subtotal_usd:.4f}"
        return (
            f"estimated ${self.known_subtotal_usd:.4f} known, plus "
            f"{self.unpriced_calls} call(s) with no configured rate - "
            "overall estimate INCOMPLETE"
        )

    def render(self) -> str:
        lines = [f"Forecast for {self.slides} slide(s): {self.headline}", ""]
        for stage in sorted(self.stages, key=lambda s: -(s.known_usd or 0.0)):
            cost = (
                f"${stage.known_usd:.4f}" if stage.known_usd is not None else "unpriced"
            )
            note = f"  [{stage.unpriced_calls} unpriced]" if stage.unpriced_calls else ""
            lines.append(
                f"  {stage.stage:24} {stage.calls:2} call(s)  {cost:>10}"
                f"  ({stage.basis}, n={stage.samples}){note}"
            )
        return "\n".join(lines)


#: Stages that make no provider call. Forecasting them as unknown would put
#: phantom uncertainty into every estimate.
DETERMINISTIC_STAGES = frozenset({"text_ownership"})


def forecast_run(
    db: Session, stages: list[str], *, slides: int = 1, minimum_samples: int = 3
) -> RunForecast:
    """
    Forecast a run from what previous runs of the same stages actually cost.

    The median rather than the mean: a single retry storm or one unusually
    long response would drag a mean upward and quietly inflate every future
    forecast. With fewer than `minimum_samples` observations the stage is
    reported as unpriced rather than guessed from one data point.
    """
    forecast = RunForecast(slides=slides)

    for stage in stages:
        if stage in DETERMINISTIC_STAGES:
            forecast.stages.append(StageForecast(
                stage=stage, calls=0, known_usd=0.0, unpriced_calls=0,
                samples=0, basis="deterministic - no provider call",
            ))
            continue

        # Joined through AnalysisRun: `capability` on a ProviderCall is the
        # provider-side axis (vision_analysis, ocr...), while the stage name
        # lives on the run. Forecasting by capability would merge every
        # vision stage into one number.
        observed = db.scalars(
            select(ProviderCall)
            .join(AnalysisRun, ProviderCall.analysis_run_id == AnalysisRun.id)
            .where(AnalysisRun.analysis_type == stage)
        ).all()

        priced = [r.estimated_cost_usd for r in observed if r.estimated_cost_usd is not None]
        unpriced = sum(1 for r in observed if r.estimated_cost_usd is None)

        if len(priced) < minimum_samples:
            forecast.stages.append(StageForecast(
                stage=stage, calls=slides, known_usd=None,
                unpriced_calls=slides, samples=len(priced),
                basis="too few observations to forecast",
            ))
            continue

        per_call = statistics.median(priced)
        unpriced_share = unpriced / len(observed) if observed else 0.0
        forecast.stages.append(StageForecast(
            stage=stage, calls=slides,
            known_usd=round(per_call * slides, 6),
            unpriced_calls=round(unpriced_share * slides),
            samples=len(priced),
            basis="median of observed calls",
        ))

    return forecast


class RunRefused(RuntimeError):
    """A run was refused before anything was spent."""


@dataclass(frozen=True)
class SpendDecision:
    allowed: bool
    reason: str
    forecast: RunForecast
    spent_today_usd: float
    daily_cap_usd: float | None
    hard_stop_usd: float | None

    def render(self) -> str:
        lines = [self.forecast.render(), ""]
        lines.append(f"  spent today      ${self.spent_today_usd:.4f}")
        if self.daily_cap_usd is not None:
            lines.append(f"  daily cap        ${self.daily_cap_usd:.4f} (soft)")
        if self.hard_stop_usd is not None:
            lines.append(f"  hard stop        ${self.hard_stop_usd:.4f}")
        lines.append(f"  decision         {'ALLOWED' if self.allowed else 'REFUSED'} - {self.reason}")
        return "\n".join(lines)


def authorise_run(
    db: Session,
    stages: list[str],
    *,
    slides: int = 1,
    daily_cap_usd: float | None = None,
    hard_stop_usd: float | None = None,
    allow_unpriced: bool = False,
) -> SpendDecision:
    """
    Decide whether a run may start, BEFORE any provider call.

    `hard_stop_usd` is absolute: a run whose forecast would cross it is
    refused outright. `daily_cap_usd` is the existing soft ceiling and is
    only advisory here - per-call enforcement still lives in `spend_limit`,
    because a run's forecast is not accurate enough to be the sole guard.

    An unpriceable run is refused unless `allow_unpriced` is set. Unknown
    cost must never behave like zero: the most expensive part of this
    workflow is exactly the part that is currently unpriced.
    """
    from app.services.spend_limit import spend_snapshot

    forecast = forecast_run(db, stages, slides=slides)
    snapshot = spend_snapshot(db)
    spent = snapshot.spent_usd

    if not forecast.is_complete and not allow_unpriced:
        return SpendDecision(
            allowed=False,
            reason=(
                f"{forecast.unpriced_calls} call(s) cannot be priced, so the run's "
                "cost is unknown. Configure a rate, or pass allow_unpriced to "
                "proceed deliberately"
            ),
            forecast=forecast, spent_today_usd=spent,
            daily_cap_usd=daily_cap_usd, hard_stop_usd=hard_stop_usd,
        )

    projected = spent + forecast.known_subtotal_usd

    if hard_stop_usd is not None and projected > hard_stop_usd:
        return SpendDecision(
            allowed=False,
            reason=(
                f"forecast ${forecast.known_subtotal_usd:.4f} on top of "
                f"${spent:.4f} already spent would reach ${projected:.4f}, "
                f"past the hard stop of ${hard_stop_usd:.4f}"
            ),
            forecast=forecast, spent_today_usd=spent,
            daily_cap_usd=daily_cap_usd, hard_stop_usd=hard_stop_usd,
        )

    reason = "within limits"
    if daily_cap_usd is not None and projected > daily_cap_usd:
        # Soft: the run proceeds and per-call enforcement stops it partway.
        reason = (
            f"projected ${projected:.4f} exceeds the soft daily cap of "
            f"${daily_cap_usd:.4f} - the run will be stopped mid-way by "
            "per-call enforcement"
        )

    return SpendDecision(
        allowed=True, reason=reason, forecast=forecast, spent_today_usd=spent,
        daily_cap_usd=daily_cap_usd, hard_stop_usd=hard_stop_usd,
    )


def reconcile(db: Session, forecast: RunForecast, actual_call_ids: list[str]) -> str:
    """
    Estimated versus actual, after the fact.

    An estimate nobody checks against reality drifts silently. This is what
    makes the forecast improvable rather than decorative.
    """
    rows = db.scalars(
        select(ProviderCall).where(ProviderCall.id.in_(actual_call_ids))
    ).all() if actual_call_ids else []

    actual_known = sum(r.estimated_cost_usd or 0.0 for r in rows)
    actual_unpriced = sum(1 for r in rows if r.estimated_cost_usd is None)
    estimated = forecast.known_subtotal_usd

    variance = actual_known - estimated
    share = (variance / estimated * 100) if estimated else 0.0

    lines = [
        f"  estimated known  ${estimated:.4f}",
        f"  actual known     ${actual_known:.4f}",
        f"  variance         ${variance:+.4f} ({share:+.1f}%)",
        f"  calls made       {len(rows)}",
    ]
    if actual_unpriced or not forecast.is_complete:
        lines.append(
            f"  unpriced         {actual_unpriced} actual, "
            f"{forecast.unpriced_calls} forecast - comparison is INCOMPLETE"
        )
    return "\n".join(lines)
