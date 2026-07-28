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

from app.services.image_dimensions import (
    measure_source_file, is_valid_pair, is_malformed_pair,
)


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

    def source_dims(self, slide_id: str) -> Optional[dict]:
        """Source pixel dimensions {"width","height"} for the slide, or None (explicit
        unknown — never a default). This is the compatibility seam Canvas consumes; its
        CONTRACT is unchanged. Deterministic read precedence:

            1. persisted width+height        -> returned WITHOUT opening the file
            2. source-file measurement       -> legacy compatibility
            3. explicit unknown (None)

        Persisted evidence is AUTHORITATIVE over the disk: when a valid pair is stored
        it is returned as-is and the file is never opened (so a later disk measurement
        can never silently replace it). A partial pair (exactly one of width/height) is
        MALFORMED — never used to derive dimensions; it falls through to the file. Use
        `source_dimension_state()` to observe malformed/conflict diagnostics."""
        row = self._c.execute(
            "select source_width, source_height, stored_file_path from slides where id=?",
            (slide_id,),
        ).fetchone()
        if not row:
            return None
        w, h = self._col(row, "source_width"), self._col(row, "source_height")
        if is_valid_pair(w, h):                                   # 1. persisted, authoritative
            return {"width": int(w), "height": int(h)}
        state, dims = measure_source_file(self._col(row, "stored_file_path"))  # 2. file fallback
        if dims is not None:
            return {"width": dims[0], "height": dims[1]}
        return None                                              # 3. explicit unknown

    def source_dimension_state(self, slide_id: str) -> dict:
        """Observability for the dimension lifecycle (diagnostics, backfill audit) —
        NOT the hot read path. Reports what is persisted, what the file measures, which
        source resolves, and whether the two disagree (persisted always wins, but the
        discrepancy is made observable rather than silently dropped)."""
        row = self._c.execute(
            "select source_width, source_height, dimension_measurement_source, "
            "stored_file_path from slides where id=?", (slide_id,),
        ).fetchone()
        if not row:
            return {"resolved": None, "source": "unknown", "persisted": None,
                    "malformed": False, "file": None, "conflict": False,
                    "measurement_source": None}
        w, h = self._col(row, "source_width"), self._col(row, "source_height")
        persisted = (int(w), int(h)) if is_valid_pair(w, h) else None
        malformed = is_malformed_pair(w, h)
        _, file_dims = measure_source_file(self._col(row, "stored_file_path"))
        if persisted is not None:
            resolved, source = persisted, "persisted"
            conflict = file_dims is not None and file_dims != persisted
        elif file_dims is not None:
            resolved, source, conflict = file_dims, "file", False
        else:
            resolved, source, conflict = None, "unknown", False
        return {"resolved": resolved, "source": source, "persisted": persisted,
                "malformed": malformed, "file": file_dims, "conflict": conflict,
                "measurement_source": self._col(row, "dimension_measurement_source")}

    @staticmethod
    def _col(row, name):
        """sqlite Row column access tolerant of older DBs without the column."""
        try:
            return row[name]
        except (IndexError, KeyError):
            return None

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

    def text_ownership(self, slide_id: str) -> dict:
        """The authoritative text-ownership artifact per OCR block, keyed by block
        INDEX (aligned to ocr_blocks order via block_id 'block-{i}'). The Plan Builder
        must CONSUME this instead of re-deriving ownership from OCR surface/role.
        Returns {} when no artifact was produced (an explicit absence → the caller
        records a gap and falls back to the OCR heuristic; it never pretends)."""
        try:
            row = self._c.execute(
                "select blocks_json from text_ownership_artifacts "
                "where slide_id=? and is_current=1", (slide_id,),
            ).fetchone()
        except Exception:
            return {}
        if not row or not row["blocks_json"]:
            return {}
        out: dict[int, dict] = {}
        for b in json.loads(row["blocks_json"]):
            bid = str(b.get("block_id") or "")
            if not bid.startswith("block-"):
                continue
            try:
                i = int(bid.split("-", 1)[1])
            except (ValueError, IndexError):
                continue
            out[i] = {
                "owner": b.get("owner"),
                "text_class": b.get("text_class"),
                "handling_policy": b.get("handling_policy"),
                "copy_policy": b.get("effective_copy_policy"),
                "confidence": b.get("confidence"),
            }
        return out

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
