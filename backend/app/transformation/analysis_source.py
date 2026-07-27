"""
Read-only access to the EXISTING analysis artefacts.

The boundary between the (rich, evolving) analysis layer and the Plan Builder.
Returns plain dicts — no ORM, no interpretation, no decisions. In the slice it
reads the dev SQLite DB directly so it runs with zero dependencies; in the app
it would be backed by the ORM behind the same method surface.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional


class AnalysisSource:
    def __init__(self, db_path: str):
        self._c = sqlite3.connect(db_path)
        self._c.row_factory = sqlite3.Row

    def resolve_slideshow_id(self, prefix: str) -> str:
        row = self._c.execute(
            "select id from slideshows where id like ?", (prefix + "%",)
        ).fetchone()
        if not row:
            raise ValueError(f"no slideshow matching {prefix!r}")
        return row["id"]

    def slides(self, slideshow_id: str) -> list[dict]:
        rows = self._c.execute(
            "select id, slide_index from slides where slideshow_id=? order by slide_index",
            (slideshow_id,),
        ).fetchall()
        return [{"id": r["id"], "slide_index": r["slide_index"]} for r in rows]

    def narrative(self, slideshow_id: str) -> Optional[dict]:
        row = self._c.execute(
            "select structured_json from narrative_structures "
            "where slideshow_id=? and is_current=1",
            (slideshow_id,),
        ).fetchone()
        return json.loads(row["structured_json"]) if row else None

    def marketing_text(self, slideshow_id: str) -> str:
        row = self._c.execute(
            "select narrative_text from marketing_analyses "
            "where slideshow_id=? order by created_at desc limit 1",
            (slideshow_id,),
        ).fetchone()
        return (row["narrative_text"] if row and row["narrative_text"] else "")

    def ocr_blocks(self, slide_id: str) -> list[dict]:
        row = self._c.execute(
            "select structured_blocks_json from ocr_results "
            "where slide_id=? and is_current=1",
            (slide_id,),
        ).fetchone()
        return json.loads(row["structured_blocks_json"] or "[]") if row else []

    def fingerprint(self, slide_id: str) -> dict:
        row = self._c.execute(
            "select structured_json from creative_fingerprints "
            "where slide_id=? and is_current=1",
            (slide_id,),
        ).fetchone()
        return json.loads(row["structured_json"]) if row else {}

    def scene_regions(self, slide_id: str) -> list[dict]:
        row = self._c.execute(
            "select regions_json from scene_analyses where slide_id=? and is_current=1",
            (slide_id,),
        ).fetchone()
        return json.loads(row["regions_json"]) if row and row["regions_json"] else []

    def product_appearances(self, slide_id: str) -> list[dict]:
        rows = self._c.execute(
            """select p.id as product_id, p.display_name, pa.prominence, pa.is_current,
                      (select count(*) from product_lock_profiles pl
                        where pl.product_id=pa.product_id and pl.is_current=1) as has_lock
                 from product_appearances pa
                 join products p on p.id=pa.product_id
                where pa.slide_id=?""",
            (slide_id,),
        ).fetchall()
        return [
            {
                "product_id": r["product_id"],
                "display_name": r["display_name"],
                "prominence": r["prominence"],
                "is_current": bool(r["is_current"]),
                "has_lock": bool(r["has_lock"]),
            }
            for r in rows
        ]

    def product_references(self, product_id: str) -> list[str]:
        """Trusted product reference images (ids) usable as identity anchors."""
        rows = self._c.execute(
            "select id from product_reference_images "
            "where product_id=? and is_current=1",
            (product_id,),
        ).fetchall()
        return [r["id"] for r in rows]
