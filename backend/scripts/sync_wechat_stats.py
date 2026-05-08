"""Unified WeChat stats sync entrypoint.

Supported sources:
- api: official WeChat datacube API
- html: saved publish-record HTML from mp.weixin.qq.com
- json: legacy scraped_articles.json produced by scrape_wechat_stats.py
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from services.wechat_publish_parser import parse_publish_records_html
from services.wechat_service import fetch_real_stats
from services.wechat_stats_sync import (
    normalize_api_stats,
    normalize_legacy_scraped_stats,
    sync_article_stats,
)


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
DEFAULT_HTML_PATH = SCRIPT_DIR / "debug_publish_page.html"
DEFAULT_JSON_PATH = BACKEND_DIR / "scraped_articles.json"


def load_records(args) -> list[dict]:
    if args.source == "api":
        stats = fetch_real_stats(days_back=args.days_back)
        return normalize_api_stats(stats)

    if args.source == "html":
        html = Path(args.html_path).read_text(encoding="utf-8", errors="ignore")
        return parse_publish_records_html(html)

    if args.source == "json":
        with Path(args.json_path).open("r", encoding="utf-8") as f:
            return normalize_legacy_scraped_stats(json.load(f))

    raise ValueError(f"Unsupported source: {args.source}")


def main():
    parser = argparse.ArgumentParser(description="Sync WeChat article stats")
    parser.add_argument("--source", choices=("api", "html", "json"), default="api")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days-back", type=int, default=Config.WECHAT_STATS_DAYS_BACK)
    parser.add_argument("--html-path", default=str(DEFAULT_HTML_PATH))
    parser.add_argument("--json-path", default=str(DEFAULT_JSON_PATH))
    args = parser.parse_args()

    records = load_records(args)
    result = sync_article_stats(records, dry_run=args.dry_run)
    result["parsed"] = len(records)

    print("=== WeChat Stats Sync ===")
    for key in ("parsed", "matched", "updated", "skipped", "dry_run"):
        print(f"{key}: {result[key]}")
    if result["unmatched"]:
        print("unmatched:")
        for title in result["unmatched"]:
            print(f"- {title}")


if __name__ == "__main__":
    main()
