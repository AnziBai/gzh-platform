import re
from datetime import datetime, timezone
from typing import Iterable

from database import SessionLocal, init_db
from models import Article, ArticleStat


STANDARD_FIELDS = (
    "read_count",
    "share_count",
    "like_count",
    "recommend_count",
    "comment_count",
    "underline_count",
)


def utcnow():
    return datetime.now(timezone.utc)


def normalize_title(title: str | None) -> str:
    text = (title or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff%]+", "", text)


def to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_api_stats(stats_by_title: dict[str, dict]) -> list[dict]:
    records = []
    for title, stats in (stats_by_title or {}).items():
        records.append({
            "title": title,
            "read_count": to_int(stats.get("int_page_read_count")),
            "share_count": to_int(stats.get("share_count")),
            "like_count": to_int(stats.get("like_count")),
            "recommend_count": to_int(stats.get("recommend_count", stats.get("add_to_fav_count"))),
            "comment_count": to_int(stats.get("comment_count", stats.get("ori_page_read_count"))),
            "underline_count": to_int(stats.get("underline_count")),
            "source": "api",
        })
    return records


def normalize_legacy_scraped_stats(items: Iterable[dict]) -> list[dict]:
    records = []
    for item in items or []:
        records.append({
            "title": item.get("title"),
            "read_count": to_int(item.get("read_count", item.get("reads"))),
            "share_count": to_int(item.get("share_count", item.get("shares"))),
            "like_count": to_int(item.get("like_count", item.get("likes"))),
            "recommend_count": to_int(
                item.get("recommend_count", item.get("recommends", item.get("favorites")))
            ),
            "comment_count": to_int(item.get("comment_count", item.get("comments"))),
            "underline_count": to_int(item.get("underline_count", item.get("underlines"))),
            "source": item.get("source", "legacy"),
        })
    return records


def _find_article(db_by_title: dict[str, Article], title: str) -> Article | None:
    key = normalize_title(title)
    if key in db_by_title:
        return db_by_title[key]

    for db_key, article in db_by_title.items():
        if key and db_key and (key in db_key or db_key in key):
            return article
    return None


def _apply_record_to_stat(stat: ArticleStat, record: dict):
    stat.read_count = to_int(record.get("read_count"))
    stat.share_count = to_int(record.get("share_count"))
    stat.like_count = to_int(record.get("like_count"))
    stat.recommend_count = to_int(record.get("recommend_count"))
    stat.comment_count = to_int(record.get("comment_count"))
    stat.underline_count = to_int(record.get("underline_count"))
    stat.share_rate = round(stat.share_count / stat.read_count, 4) if stat.read_count else 0.0
    stat.like_rate = round(stat.like_count / stat.read_count, 4) if stat.read_count else 0.0
    stat.fetched_at = utcnow()


def sync_article_stats(
    records: list[dict],
    *,
    dry_run: bool = False,
    db=None,
    init_schema: bool = True,
) -> dict:
    """Upsert standard WeChat metric records into article_stats.

    This function deliberately does not create missing articles: unmatched titles
    are returned for operator review so a bad scrape cannot fill the DB with
    duplicate or malformed article rows.
    """
    owns_session = db is None
    if owns_session and init_schema:
        init_db()
    if owns_session:
        db = SessionLocal()
    try:
        db_articles = db.query(Article).all()
        db_by_title = {
            normalize_title(article.title): article
            for article in db_articles
            if normalize_title(article.title)
        }

        matched = 0
        updated = 0
        unmatched = []
        skipped = 0

        for raw in records or []:
            title = (raw.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            record = {field: to_int(raw.get(field)) for field in STANDARD_FIELDS}
            record["title"] = title

            if not any(record[field] for field in STANDARD_FIELDS):
                skipped += 1
                continue

            article = _find_article(db_by_title, title)
            if not article:
                unmatched.append(title)
                continue

            matched += 1
            updated += 1
            if dry_run:
                continue

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
            _apply_record_to_stat(stat, record)

        if owns_session and dry_run:
            db.rollback()
        elif owns_session:
            db.commit()

        return {
            "input": len(records or []),
            "matched": matched,
            "updated": updated,
            "skipped": skipped,
            "unmatched": unmatched,
            "dry_run": dry_run,
        }
    except Exception:
        if owns_session:
            db.rollback()
        raise
    finally:
        if owns_session:
            db.close()
