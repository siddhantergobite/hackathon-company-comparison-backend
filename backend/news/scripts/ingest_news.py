"""Collect news from the command line.

    python -m backend.news.scripts.ingest_news --list
    python -m backend.news.scripts.ingest_news                      # every due source (what the worker does)
    python -m backend.news.scripts.ingest_news --all                # every enabled source, due or not
    python -m backend.news.scripts.ingest_news --source bbc-news --source nasa
    python -m backend.news.scripts.ingest_news --all --no-ai        # skip AI enrichment
    python -m backend.news.scripts.ingest_news --enrich 25          # only AI-enrich the top 25 pending articles

Works with or without the API server running. Each run is logged and visible in News Admin.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.news.config import get_settings  # noqa: E402
from backend.news.database import ensure_indexes, get_db  # noqa: E402
from backend.news.pipeline import enrich_pending, is_due, run_due_sources  # noqa: E402
from backend.news.sources import ensure_default_categories, ensure_default_sources  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show sources and their state")
    ap.add_argument("--all", action="store_true", help="fetch every enabled source now")
    ap.add_argument("--source", action="append", help="source id (repeatable)")
    ap.add_argument("--no-ai", action="store_true", help="skip AI enrichment this run")
    ap.add_argument("--enrich", type=int, metavar="N", help="only run AI enrichment on up to N pending articles")
    args = ap.parse_args()

    settings = get_settings()
    db = get_db()
    ensure_indexes(db)
    ensure_default_categories(db)
    ensure_default_sources(db, settings)

    if args.list:
        now = datetime.now(timezone.utc)
        for s in db["news_sources"].find({}).sort([("name", 1)]):
            state = "disabled" if not s.get("enabled") else ("due" if is_due(s, now) else "ok")
            print(f"{s['_id']:34} {s.get('type'):7} {state:9} articles={s.get('articles_total', 0):5} err={(s.get('last_error') or '')[:50]}")
        return 0
    if args.enrich is not None:
        print(enrich_pending(db, limit=args.enrich, settings=settings))
        return 0

    if args.all:
        only = [s["_id"] for s in db["news_sources"].find({"enabled": True}, {"_id": 1})]
    else:
        only = args.source
    summary = run_due_sources(db, settings, only=only, with_ai=not args.no_ai)
    if "skipped" in summary:
        print("skipped:", summary["skipped"])
        return 1
    ok = failed = 0
    for r in summary["results"]:
        c = r["counts"]
        flag = "ok  " if r["status"] in ("success", "partial") else "FAIL"
        ok += r["status"] != "failed"
        failed += r["status"] == "failed"
        print(f"{flag} {r['source']:32} new={c['created'] + c['clustered']:3} (joined stories: {c['clustered']:2}) updated={c['updated']:2} unchanged={c['unchanged']:3} skipped={c['skipped']:3} invalid={c['invalid']:2}" + (f"  {r['error']}" if r["error"] else ""))
    print(f"\n{ok} source(s) ok, {failed} failed | enrichment: {summary['enrichment']} | stories rescored: {summary['rescored']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
