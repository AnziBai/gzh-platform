"""
Sync all scraped WeChat data into the database.
1. Create missing article entries
2. Upsert stats for all articles
"""
import json
import os
import sys
import re
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Article, ArticleStat


def utcnow():
    return datetime.now(timezone.utc)


def sync():
    db = SessionLocal()
    try:
        scraped_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraped_articles.json")
        with open(scraped_path, "r", encoding="utf-8") as f:
            scraped = json.load(f)

        db_articles = db.query(Article).all()
        db_by_title = {}
        for a in db_articles:
            key = (a.title or "").strip()
            if key:
                db_by_title[key] = a

        created_articles = 0
        updated_stats = 0
        created_stats = 0

        for item in scraped:
            title = item["title"].strip()
            reads = item["reads"]
            shares = item["shares"]
            favorites = item["favorites"]
            likes = item["likes"]

            # Find matching article
            article = db_by_title.get(title)
            if not article:
                # Fuzzy match
                for db_t, db_a in db_by_title.items():
                    if title in db_t or db_t in title:
                        article = db_a
                        break

            if not article:
                # Create new article entry
                slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', title).strip('-').lower()
                if not slug:
                    slug = f"article-{random.randint(1000, 9999)}"
                # Check slug uniqueness
                existing_slug = db.query(Article).filter(Article.slug == slug).first()
                if existing_slug:
                    slug = f"{slug}-{random.randint(1000, 9999)}"

                article = Article(
                    title=title,
                    slug=slug,
                    file_path="",  # No local file for these
                    status="published",
                    structure_type=None,
                    word_count=None,
                    image_count=None,
                )
                db.add(article)
                db.flush()
                db_by_title[title] = article
                created_articles += 1

            # Ensure status is published
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
                existing_stat.comment_count = favorites
                existing_stat.share_rate = round(shares / reads, 4) if reads > 0 else 0.0
                existing_stat.like_rate = round(likes / reads, 4) if reads > 0 else 0.0
                existing_stat.fetched_at = utcnow()
                updated_stats += 1
            else:
                db.add(ArticleStat(
                    article_id=article.id,
                    read_count=reads,
                    share_count=shares,
                    like_count=likes,
                    comment_count=favorites,
                    share_rate=round(shares / reads, 4) if reads > 0 else 0.0,
                    like_rate=round(likes / reads, 4) if reads > 0 else 0.0,
                    fetched_at=utcnow(),
                ))
                created_stats += 1

        db.commit()

        # Summary
        from sqlalchemy import func
        total = db.query(Article).count()
        total_stats = db.query(ArticleStat).count()
        total_reads = db.query(func.sum(ArticleStat.read_count)).scalar() or 0

        print(f"=== Sync Complete ===")
        print(f"New articles created: {created_articles}")
        print(f"Stats updated: {updated_stats}")
        print(f"Stats created: {created_stats}")
        print(f"Total articles in DB: {total}")
        print(f"Total stats records: {total_stats}")
        print(f"Total reads: {total_reads}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sync()
