"""
Permanent benchmark corpus — a replayable evaluation suite, not a one-off run.

Motivation (Matt's mandate): "every benchmark should become reproducible. For
every generated candidate, persist enough information that the exact request can
be replayed months later." A benchmark run therefore is not an experiment that
evaporates — it deposits an immutable *frozen request* on disk, and each time a
model or the architecture improves we replay THAT SAME frozen request and record
a new *run* against it. Improvement is measured against identical input, forever.

Two-level layout (case = a frozen request; run = one evaluation of it over time):

    <root>/
      index.json                         registry rebuilt from disk
      cases/
        <case_id>/                       case_id = "<slideshow8>_s<idx>"  (STABLE)
          request/                        the frozen request — written ONCE, immutable
            manifest.json                 provenance: freeze time, git, models, schema versions
            final_prompt.txt              the exact provider prompt (sent verbatim)
            generation_request.json       aspect + reference filenames (the replayable request)
            transformation_plan.json      TransformationPlan.to_dict()  (why the request looks so)
            generation_spec.json          the slide's SlideGenerationSpec (dataclass -> dict)
            analysis_snapshot.json         dump of AnalysisSource read-surface -> DB-free plan replay
            reference_set.json            reference ids + provenance (observed crop vs listing)
            references/<n>__<ref_id><ext>  copied reference image files (self-contained)
            source_slide<ext>             the original slide image (human comparison anchor)
          runs/
            <run_id>/                     run_id = "<UTCstamp>__<git8>"
              run.json                    models, candidate count, git, timestamps, drift note
              <model_slug>/
                cand_<i>/
                  image.png               the raw generated candidate (saved BEFORE validation)
                  candidate.json          provider/model/seed/timing/cost + distinct-state flags
                  validation.json         validator result OR the exact exception (never lost)
                  score.json              human commercial score slot (filled later via score_case)

Replay is DB-free and transformation-free: `load_frozen_request` +
`frozen_to_generation_request` rebuild the exact GenerationRequest from
final_prompt.txt + the copied reference files + the aspect in the manifest.
The plan/spec/snapshot are persisted for provenance and for regenerating the
Plan if the transformation layer itself changes — not needed to replay the
request, which IS the frozen prompt + references + aspect + model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CORPUS_SCHEMA_VERSION = "1.2"

# The human-scoring METHODOLOGY has its own version, independent of the on-disk
# schema. When we later refine what an 8/10 reproduction means, or change the
# ship criteria, bump this — historical scores keep the version they were made
# under so they stay interpretable. Stamped into every score.json.
SCORING_RUBRIC_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Closed vocabularies for the structured human diagnostics.
#
# CRITICAL distinction (Matt's mandate): separate OBSERVATION from DIAGNOSIS.
#   - An OBSERVED ISSUE is what was actually seen ("colour drift", "missing
#     branding"). It is close to objective.
#   - A SUSPECTED CAUSE ("model", "prompt", "reference") is an interpretation.
#     It is OPTIONAL, carries a CONFIDENCE, and its correctness can be verified
#     later (diagnosis_status). We never encode a diagnosis as fact.
#   - A REPAIR HYPOTHESIS ("colour_correction") is a PROPOSED remedy, not a
#     proven one; it carries a confidence and an optional later outcome.
# This lets the corpus answer, across its whole history: how often was X
# observed, how often did we suspect cause Y, and how often did later evidence
# confirm Y — a scientific record, not a pile of assumptions.
#
# Vocabularies are governance-extensible: unknown terms are WARNED about, never
# rejected (a scorer is never blocked; the term is just proposed for governance).
# ---------------------------------------------------------------------------

# WHAT was observed to be wrong as a reproduction of the original slide (objective).
OBSERVED_ISSUES = {
    "color_drift",          # wrong shade / saturation of the product
    "incorrect_angle",      # product framed/rotated differently
    "missing_branding",     # brand mark absent or illegible
    "wrong_variant",        # different colourway/model than the source product
    "wrong_count",          # wrong number of product units
    "deformed_geometry",    # warped/implausible product shape
    "wrong_material",       # material/finish reads wrong
    "lost_text_beat",       # the slide's narrative message/beat not conveyed
    "restaged_scene",       # scene changed so much it no longer reads as this slide
    "added_details",        # invented product details not in the source
    "lost_product",         # product absent when it should be present
    "product_too_distant",  # product rendered too small/far in the frame to sell it
    "source_mismatch",      # the source slide itself is wrong (data defect, not a gen fault)
}
REPRODUCTION_FAILURES = OBSERVED_ISSUES  # back-compat alias

# What makes a candidate strong as a STANDALONE commercial image (observed).
APPEAL_STRENGTHS = {
    "realistic_background",
    "natural_lighting",
    "strong_composition",
    "authenticity",         # reads as a real photo, not a rendered/stock shot
    "material_realism",
    "believable_hands",
    "sharp_focus",
    "aspirational_styling",
}

# PROPOSED remedy for a recoverable candidate — a hypothesis, not a fact.
REPAIR_STRATEGIES = {
    "color_correction",
    "local_inpainting",
    "product_replacement",   # composite the real product in
    "background_regeneration",
    "text_overlay",          # add the composite-layer caption
    "crop_reframe",
    "none_needed",
    "not_repairable",        # only a regeneration will do
}

# The INTERPRETIVE layer — kept separate from observation.
SUSPECTED_CAUSES = {"model", "prompt", "reference", "validator", "source_data", "unknown"}
ATTRIBUTIONS = SUSPECTED_CAUSES  # back-compat alias
CONFIDENCE_LEVELS = {"low", "medium", "high", "certain"}
# Has a suspected cause / repair hypothesis been checked against later evidence?
DIAGNOSIS_STATUSES = {"unverified", "confirmed", "refuted"}
SEVERITIES = {"critical", "major", "minor", "cosmetic"}

# Versioned human-scoring rubric — what the numbers and decisions MEAN. Written
# into the corpus (scoring_rubric.json) and referenced by SCORING_RUBRIC_VERSION.
SCORING_RUBRIC = {
    "version": SCORING_RUBRIC_VERSION,
    "reproduction_fidelity": (
        "0-10. Faithful stand-in for the ORIGINAL slide: product identity + narrative "
        "beat recognisable. A full scene restage is NOT penalised (originality is a "
        "goal) so long as identity and beat survive. 10 = indistinguishable stand-in; "
        "8 = clearly the same slide, minor deviations; 5 = recognisable but notable "
        "drift; 1 = looks like a different slide."
    ),
    "standalone_appeal": (
        "0-10. How good/usable the image is on its OWN, independent of the original. "
        "10 = immediately shippable hero image; 7-8 = strong; 5 = usable but plain; "
        "<=3 = weak or artefacted."
    ),
    "would_ship": "Ship THIS as the slide, as-is, with no further work? True/False.",
    "repair_then_ship": "Ship after a BOUNDED repair (minutes, not a regeneration)? True/False.",
    "principle": (
        "Observation is recorded as fact; suspected cause and repair are recorded as "
        "hypotheses with confidence, never as fact."
    ),
}

# Registry: provider name -> its provider-prompt adapter class. The authoritative
# frozen request is the provider-NEUTRAL GenerationSpecification; each provider's
# prompt is a rendering of that spec through its adapter. Add a provider here and
# the same frozen corpus replays against it with no change to any case on disk.
# (Imported lazily in _prompt_adapter_for so importing this module stays cheap.)
_PROVIDER_PROMPT_ADAPTERS = {
    "nano_banana": ("app.transformation.adapters.nano_banana_prompt_adapter",
                    "NanoBananaPromptAdapter"),
}

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def git_commit(repo: Optional[Path] = None) -> Optional[str]:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo) if repo else None,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


def git_dirty(repo: Optional[Path] = None) -> Optional[bool]:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(repo) if repo else None,
            stderr=subprocess.DEVNULL,
        ).decode()
        return bool(out.strip())
    except Exception:
        return None


def _resolve_asset_path(raw: str) -> Optional[Path]:
    """Resolve a stored file path to a real file, tolerant of absolute vs
    storage-relative paths (older rows persisted either)."""
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    try:
        from app.config import settings

        alt = settings.storage_dir / raw
        if alt.is_file():
            return alt
        # last resort: match by basename under storage_dir/products
        base = Path(raw).name
        for cand in (settings.storage_dir / "products").rglob(base):
            if cand.is_file():
                return cand
    except Exception:
        pass
    return None


def _empty_score() -> dict:
    """The human-score slot. Two INDEPENDENT axes — the corpus keeps them apart
    on purpose (a single number conflates them):

      reproduction_fidelity  0-10  faithful stand-in for the ORIGINAL slide:
                                    product identity + narrative beat recognisable.
                                    (NOT scene-copying — a full restage is fine, even
                                    desired for originality, as long as identity/beat survive.)
      standalone_appeal       0-10  how good / usable the image is on its OWN,
                                    independent of the original.

    `commercial_score` is retained as an optional overall roll-up / legacy field.
    """
    return {
        "scored": False,
        "schema_version": CORPUS_SCHEMA_VERSION,
        "scoring_rubric_version": SCORING_RUBRIC_VERSION,
        "reproduction_fidelity": None,   # 0-10
        "standalone_appeal": None,       # 0-10
        "commercial_score": None,        # optional overall roll-up (legacy)
        "verdict": None,                 # usable | repairable | reject
        # Business decision — what we actually optimise for. Two 7/10s are not
        # equal if one ships now and the other needs ten minutes of repair.
        "decision": {
            "would_ship": None,          # ship THIS as the slide, as-is?  True/False
            "repair_then_ship": None,    # ship after a bounded repair?    True/False
        },
        # Structured diagnostics — OBSERVATION separated from DIAGNOSIS.
        "diagnostics": {
            # objective: what was seen. suspected_cause/cause_confidence are the
            # OPTIONAL interpretive layer; diagnosis_status records whether later
            # evidence checked it (unverified until then).
            "observed_issues": [],   # [{observation, severity, suspected_cause,
                                     #   cause_confidence, diagnosis_status, verification_note}]
            "appeal_strengths": [],  # [code]  (observations)
            "repair_hypotheses": [], # [{strategy, confidence, outcome}]  (proposed, not fact)
            "repairable": None,      # True/False/None
        },
        "notes": "",
        "scored_at": None,
        "scored_by": None,
    }


def _dataclass_to_dict(obj: Any) -> Any:
    """asdict for frozen dataclasses; tuples become lists (JSON-friendly)."""
    try:
        return asdict(obj)
    except TypeError:
        return obj


# ---------------------------------------------------------------------------
# analysis snapshot (DB-free plan replay).
#
# This mirrors tests/fixtures/transformation/snapshot_source.py::dump_snapshot.
# It is copied here deliberately so app.benchmark has NO dependency on the test
# tree — the corpus is product evaluation infrastructure, not a test fixture.
# The canonical *replay* counterpart is SnapshotAnalysisSource in that fixture.
# ---------------------------------------------------------------------------


def capture_analysis_snapshot(source, slideshow_id: str) -> dict:
    """Capture the exact read-surface build_plan() consumes for one slideshow."""
    sid = source.resolve_slideshow_id(slideshow_id)
    slides = source.slides(sid)
    per_slide: dict[str, dict] = {}
    product_refs: dict[str, Any] = {}
    for s in slides:
        apps = source.product_appearances(s["id"])
        per_slide[s["id"]] = {
            "fingerprint": source.fingerprint(s["id"]),
            "scene_regions": source.scene_regions(s["id"]),
            "ocr_blocks": source.ocr_blocks(s["id"]),
            "product_appearances": apps,
            "source_dims": source.source_dims(s["id"]) if hasattr(source, "source_dims") else None,
            "text_ownership": {
                str(k): v
                for k, v in (
                    source.text_ownership(s["id"]) if hasattr(source, "text_ownership") else {}
                ).items()
            },
        }
        for a in apps:
            pid = a["product_id"]
            if pid not in product_refs:
                product_refs[pid] = source.product_references(pid)
    return {
        "slideshow_id": sid,
        "slides": slides,
        "narrative": source.narrative(sid),
        "marketing_text": source.marketing_text(sid),
        "per_slide": per_slide,
        "product_references": product_refs,
    }


# ---------------------------------------------------------------------------
# the frozen request — PROVIDER-AGNOSTIC.
#
# The AUTHORITATIVE frozen request is the provider-neutral GenerationSpecification
# (generation_spec.json) + reference set + output aspect: it describes WHAT to
# generate, coupled to no provider. A provider's literal prompt is a *rendering*
# of that neutral spec through the provider's prompt adapter, captured per
# provider under request/provider_prompts/<provider>.txt. Replaying the same case
# against a new provider (GPT Image, Flux, …) renders its prompt from the neutral
# spec — the case on disk never changes.
# ---------------------------------------------------------------------------

DEFAULT_PROVIDER = "nano_banana"


def _prompt_adapter_for(provider: str):
    entry = _PROVIDER_PROMPT_ADAPTERS.get(provider)
    if entry is None:
        raise ValueError(
            f"no prompt adapter registered for provider '{provider}'. "
            f"Known: {sorted(_PROVIDER_PROMPT_ADAPTERS)}. Register one in "
            "_PROVIDER_PROMPT_ADAPTERS to replay the corpus against it."
        )
    import importlib

    module_name, class_name = entry
    return getattr(importlib.import_module(module_name), class_name)


def render_provider_request(spec, provider: str) -> str:
    """Render the provider-neutral spec into `provider`'s literal prompt."""
    adapter_cls = _prompt_adapter_for(provider)
    return adapter_cls().write(spec).provider_request


def ensure_provider_prompt(case_root: Path, provider: str) -> str:
    """Return `provider`'s literal prompt for a frozen case, rendering it from the
    neutral spec and persisting it under provider_prompts/<provider>.txt the first
    time. This is how replaying a case against a NEW provider records that provider
    without altering anything else in the case."""
    frozen = load_frozen_request(case_root)
    if provider in frozen.provider_prompts:
        return frozen.provider_prompts[provider]
    if frozen.spec is None:
        raise ValueError(f"case at {case_root} has no neutral spec to render for '{provider}'")
    prompt = render_provider_request(frozen.spec, provider)
    pp_dir = Path(case_root) / "request" / "provider_prompts"
    pp_dir.mkdir(parents=True, exist_ok=True)
    (pp_dir / f"{provider}.txt").write_text(prompt)
    return prompt


def spec_from_dict(d: dict):
    """Rebuild a SlideGenerationSpec from generation_spec.json — the inverse of the
    asdict() used at freeze time. Lets a stored case be re-rendered for any provider
    with no database and no transformation layer run."""
    from app.transformation.generation_spec import (
        SlideGenerationSpec, SpecProduct, SpecText, SpecScene, SpecAttention, SpecCanvas,
    )

    products = tuple(
        SpecProduct(p["ref"], p["label"], tuple(p.get("reference_ids", [])),
                    p.get("identity_required", True))
        for p in d.get("products", [])
    )
    texts = tuple(
        SpecText(t["ref"], t["text"], t["disposition"], t["fidelity_required"],
                 t.get("reference_target"), t.get("source", ""))
        for t in d.get("texts", [])
    )
    sc = d["scene"]
    scene = SpecScene(sc["subject_present"], sc["subject_action"], sc["subject_extent"],
                      sc["product_subject_relation"], tuple(sc.get("subject_emotion", [])),
                      sc["environment"], sc["lighting"], sc["concept"])
    a = d["attention"]
    attention = SpecAttention(
        focal_order=tuple(tuple(x) for x in a.get("focal_order", [])),
        relationships=tuple(a.get("relationships", [])),
        openings=tuple(tuple(x) for x in a.get("openings", [])),
        dynamics=a.get("dynamics", "calm"),
        contract_invariants=tuple(a.get("contract_invariants", [])),
        reuse_source_framing=a.get("reuse_source_framing", False),
    )
    cv = d.get("canvas")
    canvas = (SpecCanvas(cv["output_aspect"], cv.get("source_aspect"), cv.get("source_width"),
                         cv.get("source_height"), cv.get("fit_behaviour", "target_only"))
              if cv else None)
    return SlideGenerationSpec(
        slide_index=d["slide_index"], product_allowed=d["product_allowed"],
        products=products, texts=texts, scene=scene, attention=attention,
        gaps=tuple(d.get("gaps", [])), canvas=canvas,
    )


@dataclass
class FrozenRequest:
    aspect_ratio: str
    reference_files: list[Path] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    spec: Any = None                                     # provider-neutral (authoritative)
    provider_prompts: dict = field(default_factory=dict)  # provider -> captured prompt
    default_provider: str = DEFAULT_PROVIDER

    def provider_request(self, provider: Optional[str] = None) -> str:
        """The literal prompt for `provider`: the captured rendering if present,
        otherwise derived from the neutral spec via that provider's adapter."""
        provider = provider or self.default_provider
        if provider in self.provider_prompts:
            return self.provider_prompts[provider]
        if self.spec is not None:
            return render_provider_request(self.spec, provider)
        raise ValueError(
            f"no captured prompt for provider '{provider}' and no neutral spec to render from"
        )

    @property
    def prompt(self) -> str:
        """Back-compat: the default provider's literal prompt."""
        return self.provider_request()

    def to_generation_request(self, provider: Optional[str] = None):
        """Build the provider-agnostic GenerationRequest for `provider`. The literal
        prompt is sent verbatim (precompiled_prompt); no DB, no re-derivation."""
        from app.ai_providers.base import GenerationRequest

        prompt = self.provider_request(provider)
        return GenerationRequest(
            creative_intent=prompt,
            reference_image_paths=[str(p) for p in self.reference_files],
            things_to_avoid=[],
            aspect_ratio=self.aspect_ratio,
            precompiled_prompt=prompt,
        )


def load_frozen_request(case_root: Path) -> FrozenRequest:
    """Load a case's frozen request from disk — the true 'replay months later'
    entry point. Requires only the case's request/ directory, no DB, no provider."""
    req = Path(case_root) / "request"
    manifest = _read_json(req / "manifest.json")

    # provider prompts: prefer the per-provider directory; fall back to the legacy
    # single final_prompt.txt (treated as the default provider's rendering).
    provider_prompts: dict[str, str] = {}
    pp_dir = req / "provider_prompts"
    if pp_dir.is_dir():
        for f in sorted(pp_dir.glob("*.txt")):
            provider_prompts[f.stem] = f.read_text()
    if not provider_prompts and (req / "final_prompt.txt").exists():
        provider_prompts[DEFAULT_PROVIDER] = (req / "final_prompt.txt").read_text()

    # the provider-neutral spec (authoritative; enables cross-provider replay)
    spec = None
    gs = req / "generation_spec.json"
    if gs.exists():
        try:
            spec = spec_from_dict(_read_json(gs))
        except Exception:
            spec = None  # provenance file unreadable as a spec — captured prompts still work

    ref_set = _read_json(req / "reference_set.json")
    refs = ref_set.get("references", [])
    # Only references whose image was actually copied into the corpus resolve to a
    # file. Unresolved references keep their id for provenance but contribute no
    # file — the replayed request omits them rather than pointing at a missing path.
    ref_files = [req / "references" / r["stored_as"] for r in refs if r.get("stored_as")]
    ref_ids = [r.get("reference_id") for r in refs if r.get("reference_id")]
    return FrozenRequest(
        aspect_ratio=manifest.get("aspect_ratio", "3:4"),
        reference_files=ref_files,
        reference_ids=ref_ids,
        spec=spec,
        provider_prompts=provider_prompts,
    )


# ---------------------------------------------------------------------------
# freezing a case
# ---------------------------------------------------------------------------


def case_id_for(slideshow_id: str, slide_index: int) -> str:
    return f"{slideshow_id[:8]}_s{slide_index}"


def _copy_asset(raw_path: str, dest_dir: Path, dest_name: str) -> Optional[str]:
    """Copy a stored asset into the corpus; return the stored filename or None."""
    src = _resolve_asset_path(raw_path)
    if src is None:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".bin"
    stored = f"{dest_name}{suffix}"
    shutil.copy2(src, dest_dir / stored)
    return stored


@dataclass
class FreezeResult:
    case_root: Path
    case_id: str
    created: bool           # True if request/ was freshly frozen this call
    drift: Optional[dict]   # non-None if a rebuild disagreed with the frozen request
    frozen: FrozenRequest


def freeze_case(
    db,
    slide,
    *,
    corpus_root: Path,
    models: list[str],
    candidates: int,
    db_path: Optional[str] = None,
    repo: Optional[Path] = None,
    reuse_existing: bool = True,
) -> FreezeResult:
    """
    Ensure a frozen request exists on disk for `slide`, and return it.

    If `reuse_existing` and request/ already exists, the ON-DISK frozen request
    is authoritative (so every future run is evaluated against identical input);
    a fresh build is still computed and compared, and any disagreement is
    recorded as drift (never silently applied).

    Requires the live DB only at freeze time — replay later needs none of it.
    """
    from app.transformation.analysis_source import AnalysisSource
    from app.transformation.attention import derive_attention
    from app.transformation.generation_spec import assemble_generation_spec
    from app.transformation.plan_builder import build_plan
    from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
    from app.services.transformation_runner import (
        _brief_from_plan,
        _ownership_from_plan,
        _prefer_observed_references,
    )
    from app.config import settings
    from app.models.product_reference_image import ProductReferenceImage

    cid = case_id_for(slide.slideshow_id, slide.slide_index)
    case_root = Path(corpus_root) / "cases" / cid
    req_dir = case_root / "request"

    # --- build the transformation pass ONCE (plan + spec + prompt + refs) ---
    dbp = str(db_path or settings.database_path)
    source = AnalysisSource(dbp)
    try:
        plan = build_plan(source, slide.slideshow_id)
        ownership = _ownership_from_plan(plan)
        brief = _brief_from_plan(plan)
        attention = derive_attention(plan, brief)
        spec = assemble_generation_spec(plan, attention, ownership)
        snapshot = capture_analysis_snapshot(source, slide.slideshow_id)
    finally:
        conn = getattr(source, "_c", None)
        if conn is not None:
            conn.close()

    slide_spec = next((s for s in spec.slides if s.slide_index == slide.slide_index), None)
    if slide_spec is None:
        raise ValueError(
            f"Transformation Plan produced no spec for slide index {slide.slide_index}"
        )

    out = NanoBananaPromptAdapter().write(slide_spec)
    plan_reference_ids = tuple(r for p in slide_spec.products for r in p.reference_ids)
    chosen_ids, reference_paths = _prefer_observed_references(db, plan_reference_ids)
    aspect = slide_spec.canvas.output_aspect if slide_spec.canvas else "3:4"

    built = FrozenRequest(
        aspect_ratio=aspect,
        reference_files=[Path(p) for p in reference_paths],
        reference_ids=list(chosen_ids),
        spec=slide_spec,
        provider_prompts={DEFAULT_PROVIDER: out.provider_request},
    )

    # --- reuse-or-freeze ---
    if reuse_existing and (req_dir / "manifest.json").exists():
        frozen = load_frozen_request(case_root)
        drift = _detect_drift(built, frozen)
        if drift:
            _write_json(case_root / "runs" / "_drift" / f"{_stamp()}.json", drift)
        return FreezeResult(case_root, cid, created=False, drift=drift, frozen=frozen)

    # --- fresh freeze: write the immutable request/ directory ---
    req_dir.mkdir(parents=True, exist_ok=True)
    # Provider prompt is a RENDERING of the neutral spec (authoritative). Store it
    # per-provider so other providers can be added later without touching the case.
    (req_dir / "provider_prompts").mkdir(exist_ok=True)
    (req_dir / "provider_prompts" / f"{DEFAULT_PROVIDER}.txt").write_text(out.provider_request)
    (req_dir / "final_prompt.txt").write_text(out.provider_request)  # legacy alias (back-compat)

    # reference set: copy every chosen reference image, record provenance
    ref_rows = {}
    if chosen_ids:
        from sqlalchemy import select

        rows = db.execute(
            select(
                ProductReferenceImage.id,
                ProductReferenceImage.source_slide_id,
                ProductReferenceImage.file_path,
            ).where(ProductReferenceImage.id.in_(list(chosen_ids)))
        ).all()
        ref_rows = {r.id: r for r in rows}

    ref_records = []
    for n, rid in enumerate(chosen_ids):
        row = ref_rows.get(rid)
        raw = row.file_path if row else None
        stored = _copy_asset(raw, req_dir / "references", f"{n}__{rid}") if raw else None
        ref_records.append(
            {
                "reference_id": rid,
                "stored_as": stored,
                "origin": "observed_crop" if (row and row.source_slide_id) else "listing_or_import",
                "source_slide_id": row.source_slide_id if row else None,
                "original_path": raw,
                "resolved": stored is not None,
            }
        )
    _write_json(
        req_dir / "reference_set.json",
        {
            "reference_ids": list(chosen_ids),
            "count": len(chosen_ids),
            "resolved_count": sum(1 for r in ref_records if r["resolved"]),
            "precedence_rule": "observed slide crops authoritative; listing fills gaps only",
            "references": ref_records,
        },
    )

    # source slide image (human comparison anchor)
    source_stored = _copy_asset(getattr(slide, "stored_file_path", "") or "", req_dir, "source_slide")

    # plan / spec / snapshot (provenance + plan regeneration)
    (req_dir / "transformation_plan.json").write_text(plan.to_json())
    _write_json(req_dir / "generation_spec.json", _dataclass_to_dict(slide_spec))
    _write_json(req_dir / "analysis_snapshot.json", snapshot)

    # the replayable request (provider-neutral): the authoritative content is the
    # spec + references + aspect; provider prompts are derived renderings.
    _write_json(
        req_dir / "generation_request.json",
        {
            "authoritative_request": "generation_spec.json (provider-neutral)",
            "aspect_ratio": aspect,
            "reference_files": [r["stored_as"] for r in ref_records if r["stored_as"]],
            "provider_prompts": {DEFAULT_PROVIDER: f"provider_prompts/{DEFAULT_PROVIDER}.txt"},
            "providers_rendered": [DEFAULT_PROVIDER],
            "note": "To replay against another provider, render generation_spec.json "
                    "through that provider's prompt adapter — the case never changes.",
        },
    )

    # provenance manifest
    _write_json(
        req_dir / "manifest.json",
        {
            "corpus_schema_version": CORPUS_SCHEMA_VERSION,
            "case_id": cid,
            "frozen_at": _now_iso(),
            "slideshow_id": slide.slideshow_id,
            "slide_id": slide.id,
            "slide_index": slide.slide_index,
            "aspect_ratio": aspect,
            "reference_count": len(chosen_ids),
            "reference_resolved_count": sum(1 for r in ref_records if r["resolved"]),
            "source_slide_stored_as": source_stored,
            "authoritative_request": "generation_spec.json (provider-neutral)",
            "providers_rendered": [DEFAULT_PROVIDER],
            "prompt_chars": {DEFAULT_PROVIDER: len(out.provider_request or "")},
            "plan_schema_version": getattr(plan, "schema_version", None),
            "plan_version": getattr(plan, "plan_version", None),
            "intended_models": list(models),
            "intended_candidates_per_model": candidates,
            "git_commit": git_commit(repo),
            "git_dirty": git_dirty(repo),
            "db_path": dbp,
        },
    )

    return FreezeResult(case_root, cid, created=True, drift=None, frozen=built)


def _detect_drift(built: FrozenRequest, frozen: FrozenRequest) -> Optional[dict]:
    diffs: dict[str, Any] = {}
    if (built.prompt or "") != (frozen.prompt or ""):
        diffs["prompt"] = {
            "frozen_chars": len(frozen.prompt or ""),
            "rebuilt_chars": len(built.prompt or ""),
        }
    if built.aspect_ratio != frozen.aspect_ratio:
        diffs["aspect_ratio"] = {"frozen": frozen.aspect_ratio, "rebuilt": built.aspect_ratio}
    if list(built.reference_ids) != list(frozen.reference_ids):
        diffs["reference_ids"] = {
            "frozen": list(frozen.reference_ids),
            "rebuilt": list(built.reference_ids),
        }
    if not diffs:
        return None
    return {"detected_at": _now_iso(), "note": "rebuilt request differs from frozen request", "diffs": diffs}


# ---------------------------------------------------------------------------
# writing a run against a frozen case
# ---------------------------------------------------------------------------


class RunWriter:
    """One benchmark run (a set of candidates over one or more models) written
    beneath a frozen case's runs/ directory. Never touches request/."""

    def __init__(self, case_root: Path, *, models: list[str], candidates: int,
                 repo: Optional[Path] = None, drift: Optional[dict] = None, notes: str = "",
                 strategy: str = "transformation_plan", strategy_prompt: Optional[str] = None):
        self.case_root = Path(case_root)
        self.git = git_commit(repo)
        # strategy is part of the run id so competing strategies never collide.
        strat_tag = "" if strategy == "transformation_plan" else f"_{strategy}"
        self.run_id = f"{_stamp()}{strat_tag}__{(self.git or 'nogit')[:8]}"
        self.run_dir = self.case_root / "runs" / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.models = list(models)
        self.candidates = candidates
        self._meta = {
            "run_id": self.run_id,
            "started_at": _now_iso(),
            "git_commit": self.git,
            "git_dirty": git_dirty(repo),
            "models": self.models,
            "candidates_per_model": candidates,
            # which GENERATION STRATEGY produced this run — the head-to-head axis.
            # "transformation_plan" = the creative-spec pipeline; "source_edit" =
            # condition on the original slide, change only background + camera angle.
            "strategy": strategy,
            "strategy_prompt": strategy_prompt,
            "drift": drift,
            "notes": notes,
            "results": {},
        }
        _write_json(self.run_dir / "run.json", self._meta)

    def _model_slug(self, model: str) -> str:
        return model.replace("/", "_")

    def cand_dir(self, model: str, i: int) -> Path:
        d = self.run_dir / self._model_slug(model) / f"cand_{i}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_candidate(self, model: str, i: int, *, image_bytes: Optional[bytes],
                       candidate: dict, validation: dict) -> Path:
        """Persist a candidate's raw image (if any), its metadata, its validation
        result-or-exception, and an empty score slot. Image is written first, so a
        later validator failure can never discard it."""
        d = self.cand_dir(model, i)
        if image_bytes is not None:
            (d / "image.png").write_bytes(image_bytes)
        _write_json(d / "candidate.json", candidate)
        _write_json(d / "validation.json", validation)
        score_path = d / "score.json"
        if not score_path.exists():
            _write_json(score_path, _empty_score())
        return d

    def finalize(self, results: dict) -> Path:
        self._meta["results"] = results
        self._meta["finished_at"] = _now_iso()
        _write_json(self.run_dir / "run.json", self._meta)
        return self.run_dir


# ---------------------------------------------------------------------------
# scoring + index
# ---------------------------------------------------------------------------


def _warn_unknown(codes, vocab: set, kind: str) -> None:
    for c in codes or []:
        if c is not None and c not in vocab:
            print(f"  [corpus] note: '{c}' is not in the {kind} vocabulary "
                  f"(kept anyway — propose it for governance).")


def _normalize_observations(items) -> list[dict]:
    """Accept a string 'observation[:severity[:suspected_cause[:confidence]]]' or a
    dict; return uniform observation records. The suspected cause is OPTIONAL — an
    observation with no cause is a pure, undiagnosed observation (which is fine and
    often correct). diagnosis_status starts 'unverified'."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            rec = {
                "observation": it.get("observation") or it.get("code"),
                "severity": it.get("severity", "major"),
                "suspected_cause": it.get("suspected_cause"),
                "cause_confidence": it.get("cause_confidence"),
                "diagnosis_status": it.get("diagnosis_status", "unverified"),
                "verification_note": it.get("verification_note", ""),
            }
        else:
            p = str(it).split(":")
            rec = {
                "observation": p[0],
                "severity": p[1] if len(p) > 1 and p[1] else "major",
                "suspected_cause": p[2] if len(p) > 2 and p[2] else None,
                "cause_confidence": p[3] if len(p) > 3 and p[3] else None,
                "diagnosis_status": "unverified",
                "verification_note": "",
            }
        out.append(rec)
    return out


def _normalize_repairs(items) -> list[dict]:
    """Accept 'strategy[:confidence]' or a dict; return {strategy, confidence,
    outcome}. A repair is a PROPOSED remedy (hypothesis); outcome is filled only
    once the repair has actually been tried."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({"strategy": it.get("strategy") or it.get("code"),
                        "confidence": it.get("confidence"),
                        "outcome": it.get("outcome")})
        else:
            p = str(it).split(":")
            out.append({"strategy": p[0],
                        "confidence": p[1] if len(p) > 1 and p[1] else None,
                        "outcome": None})
    return out


def score_candidate(
    case_root: Path,
    run_id: str,
    model: str,
    candidate: int,
    *,
    reproduction_fidelity: Optional[float] = None,
    standalone_appeal: Optional[float] = None,
    commercial_score: Optional[float] = None,
    verdict: Optional[str] = None,
    would_ship: Optional[bool] = None,
    repair_then_ship: Optional[bool] = None,
    observed_issues=None,       # 'observation[:severity[:suspected_cause[:confidence]]]' or dicts
    appeal_strengths=None,      # list of codes
    repair_hypotheses=None,     # 'strategy[:confidence]' or dicts
    repairable: Optional[bool] = None,
    notes: str = "",
    scored_by: str = "human",
) -> Path:
    """Attach (or update) a human score for one candidate.

    Observation is recorded as fact; suspected cause and repair are recorded as
    hypotheses with confidence, never as fact (see the constants block). Only the
    fields you pass are set; unknown vocabulary terms are kept with a note."""
    d = Path(case_root) / "runs" / run_id / model.replace("/", "_") / f"cand_{candidate}"
    score_path = d / "score.json"
    if not score_path.exists():
        raise FileNotFoundError(f"no candidate at {d}")

    issues = _normalize_observations(observed_issues)
    repairs = _normalize_repairs(repair_hypotheses)
    _warn_unknown([i["observation"] for i in issues], OBSERVED_ISSUES, "observed-issue")
    _warn_unknown([i["suspected_cause"] for i in issues], SUSPECTED_CAUSES, "suspected-cause")
    _warn_unknown([i["cause_confidence"] for i in issues if i["cause_confidence"]],
                  CONFIDENCE_LEVELS, "confidence")
    _warn_unknown([i["severity"] for i in issues], SEVERITIES, "severity")
    _warn_unknown([r["strategy"] for r in repairs], REPAIR_STRATEGIES, "repair-strategy")
    _warn_unknown(appeal_strengths, APPEAL_STRENGTHS, "appeal-strength")

    ensure_scoring_rubric(Path(case_root).parent.parent)  # <corpus>/cases/<id> -> <corpus>

    payload = _empty_score()
    payload.update(
        scored=True,
        reproduction_fidelity=reproduction_fidelity,
        standalone_appeal=standalone_appeal,
        commercial_score=commercial_score,
        verdict=verdict,
        notes=notes,
        scored_at=_now_iso(),
        scored_by=scored_by,
    )
    payload["decision"] = {"would_ship": would_ship, "repair_then_ship": repair_then_ship}
    payload["diagnostics"] = {
        "observed_issues": issues,
        "appeal_strengths": list(appeal_strengths or []),
        "repair_hypotheses": repairs,
        "repairable": repairable,
    }
    _write_json(score_path, payload)
    return score_path


def verify_diagnosis(
    case_root: Path,
    run_id: str,
    model: str,
    candidate: int,
    observation: str,
    *,
    status: str,               # confirmed | refuted | unverified
    note: str = "",
) -> Path:
    """Record that later evidence has CONFIRMED or REFUTED the suspected cause of
    an observed issue. This is what makes the corpus a scientific record: we can
    ask how often a 'model' diagnosis was later proven correct. Updates the matching
    observed_issue in place; leaves the observation itself untouched."""
    d = Path(case_root) / "runs" / run_id / model.replace("/", "_") / f"cand_{candidate}"
    score_path = d / "score.json"
    if not score_path.exists():
        raise FileNotFoundError(f"no candidate at {d}")
    if status not in DIAGNOSIS_STATUSES:
        print(f"  [corpus] note: '{status}' is not in the diagnosis-status vocabulary.")
    score = _read_json(score_path)
    hit = False
    for i in (score.get("diagnostics") or {}).get("observed_issues", []):
        if i.get("observation") == observation:
            i["diagnosis_status"] = status
            i["verification_note"] = note
            hit = True
    if not hit:
        raise ValueError(f"no observed issue '{observation}' on {d}")
    _write_json(score_path, score)
    return score_path


def ensure_scoring_rubric(corpus_root: Path) -> Path:
    """Write the versioned scoring rubric into the corpus if the current version
    isn't already recorded. Historical scores reference their rubric version, so
    this file lets a reader recover what an old score MEANT."""
    root = Path(corpus_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "scoring_rubric.json"
    existing = _read_json(path) if path.exists() else {"versions": {}}
    if SCORING_RUBRIC_VERSION not in existing.get("versions", {}):
        existing.setdefault("versions", {})[SCORING_RUBRIC_VERSION] = SCORING_RUBRIC
        existing["current"] = SCORING_RUBRIC_VERSION
        _write_json(path, existing)
    return path


def _iter_scored(corpus_root: Path):
    """Yield (case_id, run_id, model, candidate_dir, candidate.json, score.json) for
    every scored candidate in the corpus."""
    cases_dir = Path(corpus_root) / "cases"
    if not cases_dir.is_dir():
        return
    for case_root in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        runs_dir = case_root / "runs"
        if not runs_dir.is_dir():
            continue
        for run_root in sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name != "_drift"):
            for score_path in sorted(run_root.rglob("score.json")):
                try:
                    score = _read_json(score_path)
                except Exception:
                    continue
                if not score.get("scored"):
                    continue
                cand_dir = score_path.parent
                cand = {}
                if (cand_dir / "candidate.json").exists():
                    try:
                        cand = _read_json(cand_dir / "candidate.json")
                    except Exception:
                        cand = {}
                model = cand.get("model") or cand_dir.parent.name
                yield case_root.name, run_root.name, model, cand_dir, cand, score


def aggregate(corpus_root: Path) -> dict:
    """Turn scores into evidence — keeping OBSERVATION and DIAGNOSIS separate.

    Reports how often each issue was OBSERVED (fact), and separately how often a
    cause was SUSPECTED and with what confidence and verification status
    (interpretation). So it answers: how often was colour drift observed? how
    often did we suspect the model? how often was that later confirmed?"""
    from collections import Counter, defaultdict

    n = 0
    verdicts = Counter()
    would_ship = Counter()
    repair_then_ship = Counter()
    repairable = Counter()
    observed = Counter()                          # observation -> times SEEN (fact)
    suspected_cause = Counter()                   # cause -> times SUSPECTED (interpretation)
    diagnosed_count = 0                            # observations that carry a suspected cause
    undiagnosed_count = 0                          # observations left as pure observation
    cause_confidence = Counter()                  # confidence of suspected causes
    diagnosis_status = Counter()                  # unverified / confirmed / refuted
    obs_by_cause = defaultdict(Counter)           # observation -> {cause: n}
    appeal_strengths = Counter()
    repair_hyp = Counter()                         # proposed strategy -> n
    repair_outcome = Counter()                     # outcome of tried repairs
    repro_by_model = defaultdict(list)
    appeal_by_model = defaultdict(list)
    rubric_versions = Counter()

    for case_id, run_id, model, cand_dir, cand, score in _iter_scored(corpus_root):
        n += 1
        rubric_versions[score.get("scoring_rubric_version")] += 1
        verdicts[score.get("verdict")] += 1
        dec = score.get("decision") or {}
        would_ship[dec.get("would_ship")] += 1
        repair_then_ship[dec.get("repair_then_ship")] += 1
        diag = score.get("diagnostics") or {}
        repairable[diag.get("repairable")] += 1
        for iss in diag.get("observed_issues", []):
            obs = iss.get("observation") if isinstance(iss, dict) else iss
            observed[obs] += 1
            cause = iss.get("suspected_cause") if isinstance(iss, dict) else None
            if cause:
                diagnosed_count += 1
                suspected_cause[cause] += 1
                obs_by_cause[obs][cause] += 1
                if iss.get("cause_confidence"):
                    cause_confidence[iss["cause_confidence"]] += 1
                diagnosis_status[iss.get("diagnosis_status", "unverified")] += 1
            else:
                undiagnosed_count += 1
        for s in diag.get("appeal_strengths", []):
            appeal_strengths[s] += 1
        for r in diag.get("repair_hypotheses", []):
            strat = r.get("strategy") if isinstance(r, dict) else r
            repair_hyp[strat] += 1
            if isinstance(r, dict) and r.get("outcome"):
                repair_outcome[r["outcome"]] += 1
        if score.get("reproduction_fidelity") is not None:
            repro_by_model[model].append(score["reproduction_fidelity"])
        if score.get("standalone_appeal") is not None:
            appeal_by_model[model].append(score["standalone_appeal"])

    def _mean(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "generated_at": _now_iso(),
        "scored_candidates": n,
        "scoring_rubric_versions": dict(rubric_versions),
        "verdicts": dict(verdicts),
        "would_ship": {str(k): v for k, v in would_ship.items()},
        "repair_then_ship": {str(k): v for k, v in repair_then_ship.items()},
        "repairable": {str(k): v for k, v in repairable.items()},
        # OBSERVATION (fact)
        "observed_issues": observed.most_common(),
        # DIAGNOSIS (interpretation) — kept separate on purpose
        "diagnosis": {
            "observations_with_suspected_cause": diagnosed_count,
            "observations_left_undiagnosed": undiagnosed_count,
            "suspected_cause_counts": dict(suspected_cause),
            "suspected_cause_confidence": dict(cause_confidence),
            "diagnosis_status": dict(diagnosis_status),
            "observation_to_suspected_cause": {k: dict(v) for k, v in obs_by_cause.items()},
        },
        "appeal_strengths": appeal_strengths.most_common(),
        "repair_hypotheses": repair_hyp.most_common(),
        "repair_outcomes": dict(repair_outcome),
        "mean_reproduction_fidelity_by_model": {m: _mean(v) for m, v in repro_by_model.items()},
        "mean_standalone_appeal_by_model": {m: _mean(v) for m, v in appeal_by_model.items()},
    }


def rebuild_index(corpus_root: Path) -> dict:
    """Scan every case + run on disk and write index.json (the corpus registry)."""
    root = Path(corpus_root)
    cases_dir = root / "cases"
    cases = []
    if cases_dir.is_dir():
        for case_root in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
            man_path = case_root / "request" / "manifest.json"
            manifest = _read_json(man_path) if man_path.exists() else {}
            runs = []
            runs_dir = case_root / "runs"
            if runs_dir.is_dir():
                for run_root in sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name != "_drift"):
                    rj = run_root / "run.json"
                    meta = _read_json(rj) if rj.exists() else {}
                    scored = 0
                    total = 0
                    for score_path in run_root.rglob("score.json"):
                        total += 1
                        try:
                            if _read_json(score_path).get("scored"):
                                scored += 1
                        except Exception:
                            pass
                    runs.append(
                        {
                            "run_id": run_root.name,
                            "git_commit": meta.get("git_commit"),
                            "models": meta.get("models"),
                            "started_at": meta.get("started_at"),
                            "candidates": total,
                            "scored": scored,
                        }
                    )
            cases.append(
                {
                    "case_id": case_root.name,
                    "slideshow_id": manifest.get("slideshow_id"),
                    "slide_index": manifest.get("slide_index"),
                    "frozen_at": manifest.get("frozen_at"),
                    "reference_count": manifest.get("reference_count"),
                    "run_count": len(runs),
                    "runs": runs,
                }
            )
    index = {
        "corpus_schema_version": CORPUS_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "case_count": len(cases),
        "cases": cases,
    }
    _write_json(root / "index.json", index)
    return index
