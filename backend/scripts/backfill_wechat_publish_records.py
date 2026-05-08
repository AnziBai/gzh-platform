"""Backfill article stats from a saved WeChat publish-record HTML page.

The publish-record page exposes metrics with semantic CSS classes:
view/read, like, share, haokan/recommend, comment, and underline.
This script intentionally uses those classes instead of positional numbers.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db
from models import Article, ArticleStat
from services.wechat_publish_parser import parse_publish_records_html


def _normalize_title(title: str | None) -> str:
    text = (title or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff%]+", "", text)


def _find_article(db_by_title: dict[str, Article], title: str) -> Article | None:
    key = _normalize_title(title)
    if key in db_by_title:
        return db_by_title[key]

    for db_key, article in db_by_title.items():
        if key and db_key and (key in db_key or db_key in key):
            return article
    return None


def backfill_from_html(path: Path) -> dict:
    init_db()
    records = parse_publish_records_html(path.read_text(encoding="utf-8", errors="ignore"))
    db = SessionLocal()
    try:
        articles = db.query(Article).all()
        db_by_title = {_normalize_title(article.title): article for article in articles}
        now = datetime.now(timezone.utc)

        matched = 0
        updated = 0
        unmatched = []
        for record in records:
            article = _find_article(db_by_title, record["title"])
            if not article:
                unmatched.append(record["title"])
                continue

            matched += 1
            article.status = "published"
            stat = (
                db.query(ArticleStat)
                .filter(ArticleStat.article_id == article.id)
                .order_by(ArticleStat.fetched_at.desc(), ArticleStat.id.desc())
                .first()
            )
            if not stat:
                stat = ArticleStat(article_id=article.id)
                db.add(stat)

            stat.read_count = record["read_count"]
            stat.share_count = record["share_count"]
            stat.like_count = record["like_count"]
            stat.recommend_count = record["recommend_count"]
            stat.comment_count = record["comment_count"]
            stat.underline_count = record["underline_count"]
            stat.share_rate = round(stat.share_count / stat.read_count, 4) if stat.read_count else 0.0
            stat.like_rate = round(stat.like_count / stat.read_count, 4) if stat.read_count else 0.0
            stat.fetched_at = now
            updated += 1

        db.commit()
        return {
            "parsed": len(records),
            "matched": matched,
            "updated": updated,
            "unmatched": unmatched,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "html_path",
        nargs="?",
        default=str(Path(__file__).with_name("debug_publish_page.html")),
    )
    args = parser.parse_args()
    result = backfill_from_html(Path(args.html_path))
    print(result)


if __name__ == "__main__":
    main()
