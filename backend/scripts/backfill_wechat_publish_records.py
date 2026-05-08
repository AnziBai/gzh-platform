"""Backfill article stats from a saved WeChat publish-record HTML page.

The publish-record page exposes metrics with semantic CSS classes:
view/read, like, share, haokan/recommend, comment, and underline.
This script intentionally uses those classes instead of positional numbers.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wechat_publish_parser import parse_publish_records_html
from services.wechat_stats_sync import sync_article_stats


def backfill_from_html(path: Path, *, dry_run: bool = False) -> dict:
    records = parse_publish_records_html(path.read_text(encoding="utf-8", errors="ignore"))
    result = sync_article_stats(records, dry_run=dry_run)
    result["parsed"] = len(records)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "html_path",
        nargs="?",
        default=str(Path(__file__).with_name("debug_publish_page.html")),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = backfill_from_html(Path(args.html_path), dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
