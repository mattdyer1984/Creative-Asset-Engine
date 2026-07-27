"""
The Plan Builder's ONLY ownership logic: translate an OwnershipDecision into a
handling decision. It does not look at typography, surface or geometry, and it
never overrides an uncertain classification. Ownership analysis decides *who
owns the text*; this maps that to *what the Plan does with it*.

`hand_off_candidate` means "eligible for the overlay brief" — NOT "remove".
Whether the source is masked/inpainted is a separate downstream removal-safety
decision, deliberately out of this slice.
"""
from __future__ import annotations

from typing import Optional
from .ownership import OwnershipDecision


def plan_text_handling(decision: Optional[OwnershipDecision]) -> dict:
    if decision is None:
        return {"handling": "preserve_in_asset", "reason": "no ownership decision — preserved, not inferred"}
    if decision.proposed_handling == "eligible_for_separation":
        return {"handling": "hand_off_candidate", "from_class": decision.ownership_class,
                "confidence": decision.confidence}
    return {"handling": "preserve_in_asset", "from_class": decision.ownership_class,
            "confidence": decision.confidence}
