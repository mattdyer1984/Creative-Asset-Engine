#!/usr/bin/env python3
"""
Guarded Alembic wrapper (follow-up to Checkpoint B, item 3).

Exists because of a real mistake, not a hypothetical one: a migration
intended for a throwaway copy ran against the live development database,
because the override used the wrong env var (settings use the `CAE_`
prefix, so `DATABASE_PATH=...` was silently ignored and the default
path was used). Nothing was harmed, but "remember the right prefix" is
not a safeguard.

So this refuses to guess. It always prints the FULLY RESOLVED database
path first, states plainly whether that is the live development database
or a copy, and requires `--live` before touching the live one. Before an
approved live migration it takes a real backup (SQLite's own backup API,
which is WAL-safe - a plain file copy is not), and afterwards it runs an
integrity check.

Usage:
    python3 scripts/migrate.py upgrade head            # dry, refuses if live
    python3 scripts/migrate.py --live upgrade head     # explicit consent
    python3 scripts/migrate.py --db /tmp/copy.db upgrade head
    python3 scripts/migrate.py downgrade -1 --live
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
# The backend's own interpreter, not whatever python is invoking this
# script - app.config needs the venv's dependencies.
VENV_PYTHON = BACKEND_DIR / ".venv/bin/python"


def resolve_live_db_path() -> Path:
    """Ask the application itself, rather than reimplementing its logic."""
    result = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "from app.config import Settings; print(Settings().database_path)",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit("Could not resolve the configured database path.")
    return Path(result.stdout.strip())


def backup_sqlite(source: Path) -> Path:
    """
    WAL-safe backup via SQLite's own backup API. A plain `cp` of a
    WAL-mode database can capture a torn state - this app runs in WAL
    mode (see app/db.py), so the difference is real, not pedantry.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = source.with_name(f"{source.stem}.pre-migration-{stamp}.db")
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return destination


def integrity_check(path: Path) -> tuple[bool, str]:
    with sqlite3.connect(path) as con:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
    return result == "ok", result


def current_revision(path: Path) -> str:
    with sqlite3.connect(path) as con:
        try:
            row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return "(no alembic_version table)"
    return row[0] if row else "(empty)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="alembic command, e.g. upgrade / downgrade / current")
    parser.add_argument("args", nargs="*", help="arguments for that command, e.g. head / -1")
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly consent to migrating the LIVE development database",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="run against this database instead (a copy). Implies not-live.",
    )
    parser.add_argument("--no-backup", action="store_true", help="skip the pre-migration backup")
    options = parser.parse_args()

    live_path = resolve_live_db_path()
    env = dict(os.environ)

    if options.db:
        target = options.db.resolve()
        # The app derives the DB filename from CAE_DATA_DIR, so point it
        # at the copy's directory and require the expected filename.
        if target.name != live_path.name:
            raise SystemExit(
                f"--db must be named {live_path.name!r} (the app derives the filename "
                f"from its data dir); got {target.name!r}"
            )
        env["CAE_DATA_DIR"] = str(target.parent)
        is_live = False
    else:
        target = live_path
        is_live = True

    print("=" * 68)
    print("  Resolved database path:")
    print(f"    {target}")
    print(f"  Target: {'*** LIVE DEVELOPMENT DATABASE ***' if is_live else 'copy / test database'}")
    print(f"  Exists: {target.exists()}")
    if target.exists():
        print(f"  Current revision: {current_revision(target)}")
    print(f"  Command: alembic {options.command} {' '.join(options.args)}")
    print("=" * 68)
    sys.stdout.flush()  # keep the banner ahead of any stderr refusal

    if is_live and not options.live:
        print(
            "\nREFUSING to run against the live development database without --live.\n"
            "  * To migrate a copy:  --db /path/to/creative_asset_engine.db\n"
            "  * To proceed anyway:  --live  (a backup is taken automatically)\n",
            file=sys.stderr,
        )
        return 2

    backup_path = None
    mutating = options.command in {"upgrade", "downgrade", "stamp"}
    if is_live and mutating and not options.no_backup and target.exists():
        backup_path = backup_sqlite(target)
        ok, detail = integrity_check(backup_path)
        print(f"  Backup written: {backup_path}")
        print(f"  Backup integrity: {detail}")
        if not ok:
            raise SystemExit("Backup failed its integrity check - aborting before migrating.")

    result = subprocess.run(
        [str(BACKEND_DIR / ".venv/bin/alembic"), options.command, *options.args],
        cwd=BACKEND_DIR,
        env=env,
    )
    if result.returncode != 0:
        print("\nMigration FAILED.", file=sys.stderr)
        if backup_path:
            print(f"Restore with:  cp {backup_path} {target}", file=sys.stderr)
        return result.returncode

    if target.exists():
        ok, detail = integrity_check(target)
        print(f"\n  Post-migration integrity: {detail}")
        print(f"  Revision now: {current_revision(target)}")
        if not ok:
            if backup_path:
                print(f"Restore with:  cp {backup_path} {target}", file=sys.stderr)
            raise SystemExit("Post-migration integrity check FAILED.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
