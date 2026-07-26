"""
Score the Canonical Reference Library for an already-analysed data dir.

The benchmark harness gates reference loading and scoring behind
`--include-generation` (run_benchmarks.py:275), so an analysis-only run
leaves the references unscored and `select_reference_images` returns None.

This calls the harness's OWN functions - no benchmark-specific shortcut, no
reimplementation - so the variance study starts from exactly the reference
library a normal run would produce, without paying for two throwaway images
to unlock it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--case", required=True, help="benchmark case directory")
    parser.add_argument("--i-understand-this-spends-money", action="store_true",
                        required=True)
    args = parser.parse_args()

    import os
    os.environ["CAE_DATA_DIR"] = str(pathlib.Path(args.data_dir).resolve())

    import importlib.util
    spec_path = ROOT / "scripts" / "phase_f" / "run_benchmarks.py"
    spec = importlib.util.spec_from_file_location("_run_benchmarks", spec_path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    _load_canonical_references = harness._load_canonical_references
    _build_reference_library = harness._build_reference_library

    from app.db import SessionLocal
    from app.models.product import Product

    db = SessionLocal()
    try:
        product = db.query(Product).first()
        if product is None:
            print("no product in this data dir")
            return 2

        case = pathlib.Path(args.case)
        canonical = _load_canonical_references(db, product.id, case)
        library = _build_reference_library(db, product.id)
        db.commit()

        print(json.dumps({"canonical": canonical, "library": library}, indent=2)[:2000])
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
