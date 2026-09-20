"""Run event collectors.

    python -m backend.events.scripts.ingest_events --list
    python -m backend.events.scripts.ingest_events --source eventbrite
    python -m backend.events.scripts.ingest_events --source feed:my-feed --dry-run
    python -m backend.events.scripts.ingest_events --all [--ai] [--limit 50]

Only sources that are configured run (see .env and collectors/sources.json). Each run is
logged to `ingestion_runs` / `ingestion_errors` and appears in the admin dashboard.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.events.database import ensure_indexes, get_db  # noqa: E402
from backend.events.collectors.registry import list_collectors  # noqa: E402
from backend.events.processors.pipeline import run_collector  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list collectors and whether they are configured")
    ap.add_argument("--source", action="append", help="collector name (repeatable)")
    ap.add_argument("--all", action="store_true", help="run every configured collector")
    ap.add_argument("--dry-run", action="store_true", help="validate/dedupe but write nothing")
    ap.add_argument("--ai", action="store_true", help="use the configured LLM for classification (falls back to rules)")
    ap.add_argument("--limit", type=int, help="stop after N records per collector")
    args = ap.parse_args()

    collectors = list_collectors()
    if args.list or not (args.source or args.all):
        for c in collectors:
            print(f"{c.name:28} {'configured' if c.is_configured() else 'NOT configured':15} {c.description}")
        return 0

    wanted = [c for c in collectors if args.all or c.name in (args.source or [])]
    unknown = set(args.source or []) - {c.name for c in collectors}
    if unknown:
        print(f"unknown source(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    db = get_db()
    ensure_indexes(db)
    exit_code = 0
    for c in wanted:
        if not c.is_configured():
            print(f"- {c.name}: skipped (not configured)")
            continue
        summary = run_collector(db, c, dry_run=args.dry_run, use_ai=True if args.ai else None, limit=args.limit)
        print(f"- {c.name}: {summary['status']}  {summary['counts']}" + (f"  error={summary['error']}" if summary["error"] else ""))
        if summary["status"] == "failed":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
