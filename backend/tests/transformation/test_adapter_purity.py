"""
Enforcement family #1 — Adapter purity.
Primary defence: structural translation (provider_language). Secondary net: this
deny-list scanner. Proven over the portable fixture corpus, no paid calls.
"""
import re
from tests.fixtures.transformation.snapshot_source import SnapshotAnalysisSource
from app.transformation.plan_builder import build_plan
from app.transformation.attention import derive_attention
from app.transformation.generation_spec import assemble_generation_spec
from app.transformation.adapters.nano_banana_prompt_adapter import NanoBananaPromptAdapter
from run_three_families import brief_from_plan

FIXTURES = ["ninja", "posture", "colgate", "crocs"]

INTERNAL_TOKENS = {
    "hook_caption", "subhead", "price_card", "cta", "creator_overlay",
    "product_native", "design_integral", "provider_scene", "composite_layer",
    "overlay_handoff", "render_in_asset", "semantic_presence", "reference_fidelity",
    "exact_text", "promoted_product", "product_withheld", "product_is_dominant_focus",
    "price_is_evidence",
}
_ELEMENT_ID = re.compile(r"\bs\d+_(?:t\d+|product|packaging)\b")
_JARGON = re.compile(r"\bstrictness\b")


def scan(req: str) -> list[str]:
    hits = set()
    low = req.lower()
    for t in INTERNAL_TOKENS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(t)}(?![a-z0-9_])", low):
            hits.add(f"enum:{t}")
    if _ELEMENT_ID.search(req):
        hits.add("element-id")
    if _JARGON.search(low):
        hits.add("jargon")
    return sorted(hits)


def build_requests(name: str) -> list[str]:
    src = SnapshotAnalysisSource.load(name)
    plan = build_plan(src, src._s["slideshow_id"][:8])
    att = derive_attention(plan, brief_from_plan(plan))
    spec = assemble_generation_spec(plan, att, {})     # ownership wired authoritatively in step 3
    ad = NanoBananaPromptAdapter()
    return [ad.write(s).provider_request for s in spec.slides]


def test_no_internal_tokens_in_any_request():
    for name in FIXTURES:
        for i, req in enumerate(build_requests(name)):
            hits = scan(req)
            assert not hits, f"{name} slide {i} leaked {hits}"
