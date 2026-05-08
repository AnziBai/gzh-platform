"""Sync scraped WeChat metric JSON into the database.

This is a compatibility entrypoint for older scraped_articles.json files.
It normalizes legacy field names and delegates matching/upsert behavior to the
shared stats sync service.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wechat_stats_sync import normalize_legacy_scraped_stats, sync_article_stats


DEFAULT_JSON_PATH = Path(__file__).resolve().parents[1] / "scraped_articles.json"


def sync(json_path: Path = DEFAULT_JSON_PATH, *, dry_run: bool = False) -> dict:
    with json_path.open("r", encoding="utf-8") as f:
        scraped = json.load(f)

    records = normalize_legacy_scraped_stats(scraped)
    result = sync_article_stats(records, dry_run=dry_run)
    result["parsed"] = len(records)
    result["json_path"] = str(json_path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", nargs="?", default=str(DEFAULT_JSON_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = sync(Path(args.json_path), dry_run=args.dry_run)
    print("=== WeChat JSON Sync ===")
    for key in ("json_path", "parsed", "matched", "updated", "skipped", "dry_run"):
        print(f"{key}: {result[key]}")
    if result["unmatched"]:
        print("unmatched:")
        for title in result["unmatched"]:
            print(f"- {title}")


if __name__ == "__main__":
    main()
