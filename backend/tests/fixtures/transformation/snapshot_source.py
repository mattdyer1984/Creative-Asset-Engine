"""
Portable, repository-contained fixture source for deterministic transformation tests.

Captures everything build_plan()/the transformation layer reads from AnalysisSource
into a JSON snapshot, and replays it through the identical 9-method interface — so
tests run with NO database and NO absolute paths. Snapshots live beside this file.
"""
from __future__ import annotations
import json, os

_DIR = os.path.dirname(os.path.abspath(__file__))


def dump_snapshot(src, slideshow_id: str) -> dict:
    """Extract the exact read-surface build_plan() consumes for one slideshow."""
    sid = src.resolve_slideshow_id(slideshow_id)
    slides = src.slides(sid)
    per_slide, product_refs = {}, {}
    for s in slides:
        apps = src.product_appearances(s["id"])
        per_slide[s["id"]] = {
            "fingerprint": src.fingerprint(s["id"]),
            "scene_regions": src.scene_regions(s["id"]),
            "ocr_blocks": src.ocr_blocks(s["id"]),
            "product_appearances": apps,
            "source_dims": src.source_dims(s["id"]) if hasattr(src, "source_dims") else None,
            "text_ownership": {str(k): v for k, v in (
                src.text_ownership(s["id"]) if hasattr(src, "text_ownership") else {}).items()},
        }
        for a in apps:
            pid = a["product_id"]
            if pid not in product_refs:
                product_refs[pid] = src.product_references(pid)
    return {
        "slideshow_id": sid,
        "slides": slides,
        "narrative": src.narrative(sid),
        "marketing_text": src.marketing_text(sid),
        "per_slide": per_slide,
        "product_references": product_refs,
    }


class SnapshotAnalysisSource:
    """Same method surface as AnalysisSource, backed by a JSON snapshot dict."""
    def __init__(self, snapshot: dict):
        self._s = snapshot

    @classmethod
    def load(cls, name: str) -> "SnapshotAnalysisSource":
        with open(os.path.join(_DIR, f"{name}.snapshot.json")) as f:
            return cls(json.load(f))

    def resolve_slideshow_id(self, prefix: str) -> str:
        sid = self._s["slideshow_id"]
        if not sid.startswith(prefix):
            raise ValueError(f"no slideshow matching {prefix!r}")
        return sid

    def slides(self, slideshow_id): return self._s["slides"]
    def narrative(self, slideshow_id): return self._s["narrative"]
    def marketing_text(self, slideshow_id): return self._s["marketing_text"]
    def fingerprint(self, slide_id): return self._s["per_slide"][slide_id]["fingerprint"]
    def scene_regions(self, slide_id): return self._s["per_slide"][slide_id]["scene_regions"]
    def ocr_blocks(self, slide_id): return self._s["per_slide"][slide_id]["ocr_blocks"]
    def product_appearances(self, slide_id): return self._s["per_slide"][slide_id]["product_appearances"]
    def product_references(self, product_id): return self._s["product_references"].get(product_id, [])
    def source_dims(self, slide_id): return self._s["per_slide"].get(slide_id, {}).get("source_dims")
    def text_ownership(self, slide_id):
        raw = self._s["per_slide"].get(slide_id, {}).get("text_ownership") or {}
        return {int(k): v for k, v in raw.items()}
