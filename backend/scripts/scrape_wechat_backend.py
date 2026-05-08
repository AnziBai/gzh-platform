"""
Scrape WeChat backend published articles list and update database.
Run this script manually after collecting data from Playwright.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from database import SessionLocal, engine, Base
from models import Article, ArticleStat


def update_db_from_scraped_data(data_file: str):
    """Read scraped JSON and upsert into database."""
    with open(data_file, "r", encoding="utf-8") as f:
        all_articles = json.load(f)

    db = SessionLocal()
    try:
        db_articles = db.query(Article).all()
        db_by_title = {}
        for a in db_articles:
            key = (a.title or "").strip()
            if key:
                db_by_title[key] = a

        updated = 0
        created = 0
        not_found = []

        for item in all_articles:
            title = item["title"].strip()
            reads = item["reads"]
            shares = item["shares"]
            favorites = item["favorites"]
            likes = item["likes"]

            article = db_by_title.get(title)
            if not article:
                # Try fuzzy match
                for db_title, db_art in db_by_title.items():
                    if title in db_title or db_title in title:
                        article = db_art
                        break

            if not article:
                not_found.append(title)
                continue

            # Update article status to published
            article.status = "published"

            # Upsert stats
            existing_stat = (
                db.query(ArticleStat)
                .filter(ArticleStat.article_id == article.id)
                .first()
            )

            if existing_stat:
                existing_stat.read_count = reads
                existing_stat.share_count = shares
                existing_stat.like_count = likes
                existing_stat.comment_count = favorites  # 收藏数 → comment_count field
                existing_stat.share_rate = round(shares / reads, 4) if reads > 0 else 0.0
                existing_stat.like_rate = round(likes / reads, 4) if reads > 0 else 0.0
                existing_stat.fetched_at = datetime.now(timezone.utc)
                updated += 1
            else:
                db.add(ArticleStat(
                    article_id=article.id,
                    read_count=reads,
                    share_count=shares,
                    like_count=likes,
                    comment_count=favorites,
                    share_rate=round(shares / reads, 4) if reads > 0 else 0.0,
                    like_rate=round(likes / reads, 4) if reads > 0 else 0.0,
                    fetched_at=datetime.now(timezone.utc),
                ))
                created += 1

        db.commit()
        print(f"Done! Updated: {updated}, Created: {created}")
        if not_found:
            print(f"Not found in DB ({len(not_found)}):")
            for t in not_found:
                print(f"  - {t}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    data_file = sys.argv[1] if len(sys.argv) > 1 else "scraped_articles.json"
    update_db_from_scraped_data(data_file)
