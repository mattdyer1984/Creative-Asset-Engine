"""
Text-ownership analysis step.

ONE narrow job: for each detected text region, decide whether the text is a
separable creator-added presentation layer, or belongs to the semantic content
of the asset. It answers *who owns the text* — never whether to remove it
(that is a separate downstream removal-safety decision, not in this slice).

Asymmetric policy:
    high-confidence creator_overlay -> eligible_for_separation
    anything else / uncertain       -> preserve

The Plan Builder must CONSUME this result and must not re-infer ownership from
typography or surface. Architectural boundary:
    visual + semantic evidence -> ownership analysis -> Plan decision -> handling
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

OWNERSHIP_CLASSES = {"creator_overlay", "product_native", "scene_native", "design_integral"}
HIGH_CONFIDENCE = 0.80


@dataclass
class TextRegionEvidence:
    region_id: str
    text: str
    surface: Optional[str] = None          # OCR: overlay | physical | None
    role: Optional[str] = None             # OCR role
    bbox: Optional[list] = None            # [x_min,y_min,x_max,y_max]
    overlaps_product: bool = False         # from product regions
    overlaps_scene_object: bool = False    # from scene regions
    slide_narrative_role: Optional[str] = None   # hook | reveal | ...
    crop_path: Optional[str] = None        # image crop for the VLM
    slide_path: Optional[str] = None       # full slide for context


@dataclass
class OwnershipDecision:
    region_id: str
    text: str
    ownership_class: Optional[str]         # one of OWNERSHIP_CLASSES, or None == uncertain
    confidence: float                      # 0..1
    removal_alters_meaning: Optional[bool] # would removing this change identity/story/evidence/meaning?
    reasoning: str
    provenance: list[str] = field(default_factory=list)   # which evidence drove it
    evidence_used: list[str] = field(default_factory=list)

    @property
    def is_uncertain(self) -> bool:
        return self.ownership_class is None or self.confidence < HIGH_CONFIDENCE

    @property
    def proposed_handling(self) -> str:
        """Asymmetric policy — the safety gate. Ownership only; no removal action."""
        if self.ownership_class == "creator_overlay" and self.confidence >= HIGH_CONFIDENCE \
           and self.removal_alters_meaning is False:
            return "eligible_for_separation"
        return "preserve"


class OwnershipClassifier:
    def classify(self, ev: TextRegionEvidence) -> OwnershipDecision:  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------
# Production classifier: a VLM judgment over the full evidence bundle.
# Not executed in the cloud slice (no provider creds); runs in the app env.
# --------------------------------------------------------------------------
OWNERSHIP_PROMPT = """\
You are deciding TEXT OWNERSHIP for one text region in a TikTok Shop creative.

Question: does this text belong to the SEMANTIC CONTENT of the image, or was it
added by the creator as a SEPARABLE presentation layer on top?

Classify into exactly one of:
- creator_overlay : a hook/caption/price-sticker/CTA the creator added over an
  otherwise-complete visual. Separable.
- product_native  : branding, packaging, labels, product feature copy. Belongs to the product.
- scene_native    : signs, clothing print, book covers, shelf tags — text physically on an object/environment.
- design_integral : infographics, editorial illustrations, comics, dialogue, memes,
  chat/review screenshots, simulated interfaces — text that is part of the story/designed composition.

Then answer the decisive safety question:
  Would REMOVING this text alter the identity, story, evidence, product information
  or intended meaning of the underlying asset? (true/false)
If true, it is NOT separable overlay text, even if it visually resembles one.

Policy: only mark creator_overlay with HIGH confidence when you are sure it is a
separable layer whose removal changes nothing essential. If unsure, return low
confidence — the system will preserve it. Styling is weak evidence; ownership and
meaning decide.

Evidence provided: the text, its OCR role/surface/bbox, the image crop, the full
slide, neighbouring text, product/scene regions, and the slide's narrative role.

Return JSON: {ownership_class, confidence (0..1), removal_alters_meaning (bool),
reasoning}."""


class VLMOwnershipClassifier(OwnershipClassifier):
    def __init__(self, vlm_fn: Callable[[str, TextRegionEvidence], dict]):
        self._vlm = vlm_fn  # (prompt, evidence) -> {ownership_class, confidence, removal_alters_meaning, reasoning}

    def classify(self, ev: TextRegionEvidence) -> OwnershipDecision:
        r = self._vlm(OWNERSHIP_PROMPT, ev)
        cls = r.get("ownership_class")
        if cls not in OWNERSHIP_CLASSES:
            cls = None
        return OwnershipDecision(
            region_id=ev.region_id, text=ev.text, ownership_class=cls,
            confidence=float(r.get("confidence", 0.0)),
            removal_alters_meaning=r.get("removal_alters_meaning"),
            reasoning=r.get("reasoning", ""), provenance=["vlm_ownership"],
            evidence_used=["crop", "slide", "ocr", "neighbours", "product_scene_regions", "narrative_role"],
        )


# --------------------------------------------------------------------------
# Conservative, fully-deterministic fallback (runnable here, zero deps).
# Deliberately abstains whenever evidence is insufficient — high abstention,
# zero destructive false-positives.
# --------------------------------------------------------------------------
class ConservativeRuleClassifier(OwnershipClassifier):
    def classify(self, ev: TextRegionEvidence) -> OwnershipDecision:
        prov, why = [], ""
        cls, conf, alters = None, 0.4, True
        surf, role = (ev.surface or ""), (ev.role or "")
        if surf == "physical":
            prov.append("ocr.surface=physical")
            alters = True
            if ev.overlaps_product:
                cls, why = "product_native", "physical text overlapping the product"
            else:
                cls, why = "scene_native", "physical text on an object/scene (default preserve)"
            conf = 0.85  # confident it is NOT a separable overlay (safe direction)
        elif surf == "overlay":
            prov.append("ocr.surface=overlay")
            # overlay is NOT sufficient to authorise separation (see benchmark). Abstain
            # unless it is a plain caption role AND not a price AND not over a product/scene object.
            is_price = role == "price" or any(c in ev.text for c in ("£", "$", "%"))
            if role in {"headline", "subheadline", "cta"} and not is_price \
               and not ev.overlaps_product and not ev.overlaps_scene_object:
                # still cannot rule out design-integral from fields alone -> medium confidence -> preserve
                cls, conf, alters, why = "creator_overlay", 0.6, False, \
                    "caption-role overlay, not price, not over product/scene — but design-integral cannot be ruled out from fields"
            else:
                cls, conf, why = None, 0.4, "overlay with price/ambiguous ownership — abstain (preserve)"
        else:
            why = "no surface evidence — abstain (preserve)"
        return OwnershipDecision(
            region_id=ev.region_id, text=ev.text, ownership_class=cls, confidence=conf,
            removal_alters_meaning=alters, reasoning=why, provenance=prov or ["no_evidence"],
            evidence_used=[k for k in ("surface", "role") if getattr(ev, k)],
        )


# --------------------------------------------------------------------------
# Recorded classifier: replays a stored VLM judgment (used to run the benchmark
# here without a live provider). This is the recorded output of a VLM doing the
# real classifier's job on the fixture.
# --------------------------------------------------------------------------
class RecordedOwnershipClassifier(OwnershipClassifier):
    def __init__(self, recorded: dict[str, dict]):
        self._rec = recorded

    def classify(self, ev: TextRegionEvidence) -> OwnershipDecision:
        r = self._rec.get(ev.region_id)
        if r is None:
            return OwnershipDecision(ev.region_id, ev.text, None, 0.0, True,
                                     "no recorded decision — preserve", ["missing"], [])
        cls = r.get("class")
        cls = cls if cls in OWNERSHIP_CLASSES else None
        alters = False if cls == "creator_overlay" else True
        return OwnershipDecision(
            region_id=ev.region_id, text=ev.text, ownership_class=cls,
            confidence=float(r.get("confidence", 0.0)), removal_alters_meaning=alters,
            reasoning=r.get("reason", ""), provenance=["recorded_vlm"],
            evidence_used=["crop", "slide", "ocr", "context"],
        )
