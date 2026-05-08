import random
from datetime import datetime, timezone
import re

from flask import Blueprint, request
from sqlalchemy import func

from database import SessionLocal
from models import Article, ArticleStat
from utils import success_response, error_response

analytics_bp = Blueprint("analytics", __name__)


def utcnow():
    return datetime.now(timezone.utc)


def _latest_stat(article):
    if not article.stats:
        return None
    fallback = datetime.min.replace(tzinfo=timezone.utc)
    return max(article.stats, key=lambda s: s.fetched_at or fallback)


def _normalize_title(title):
    text = (title or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _title_lookup(items):
    lookup = {}
    for title, payload in items.items():
        normalized = _normalize_title(title)
        if normalized and normalized not in lookup:
            lookup[normalized] = payload
    return lookup


def _match_by_title(items, lookup, title):
    title = (title or "").strip()
    if title in items:
        return items[title]
    return lookup.get(_normalize_title(title))


@analytics_bp.route("/analytics/overview")
def overview():
    db = SessionLocal()
    try:
        total_articles = db.query(func.count(Article.id)).scalar() or 0
        published_articles = (
            db.query(func.count(Article.id))
            .filter(Article.status == "published")
            .scalar() or 0
        )
        draft_articles = total_articles - published_articles

        articles = db.query(Article).all()
        latest_stats = [_latest_stat(article) for article in articles]
        latest_stats = [stat for stat in latest_stats if stat is not None]
        total_reads = sum(stat.read_count or 0 for stat in latest_stats)
        total_shares = sum(stat.share_count or 0 for stat in latest_stats)

        avg_read_per_article = (
            round(total_reads / published_articles, 1) if published_articles > 0 else 0.0
        )

        # top structure types: group by structure_type, get avg reads from latest stat per article
        articles_with_stats = [article for article in articles if article.structure_type]

        structure_data = {}
        for article in articles_with_stats:
            stype = article.structure_type
            if not stype:
                continue
            latest_stat = _latest_stat(article)
            reads = latest_stat.read_count if latest_stat else 0
            if stype not in structure_data:
                structure_data[stype] = {"count": 0, "total_reads": 0}
            structure_data[stype]["count"] += 1
            structure_data[stype]["total_reads"] += reads

        top_structure_types = [
            {
                "structure_type": stype,
                "count": vals["count"],
                "avg_reads": round(vals["total_reads"] / vals["count"], 1) if vals["count"] > 0 else 0.0,
            }
            for stype, vals in structure_data.items()
        ]
        top_structure_types.sort(key=lambda x: x["avg_reads"], reverse=True)

        return success_response({
            "total_articles": total_articles,
            "published_articles": published_articles,
            "draft_articles": draft_articles,
            "total_reads": total_reads,
            "total_shares": total_shares,
            "avg_read_per_article": avg_read_per_article,
            "top_structure_types": top_structure_types,
        })
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@analytics_bp.route("/analytics/articles")
def list_articles_analytics():
    from config import Config
    from services.article_service import scan_articles_dir
    db = SessionLocal()
    try:
        # Build DB lookup by file_path
        db_articles = db.query(Article).all()
        db_by_path = {a.file_path: a for a in db_articles}

        fs_articles = scan_articles_dir(Config.ARTICLES_DIR)

        result = []
        seen_db_ids = set()

        for fs_item in fs_articles:
            file_path = fs_item["file_path"]
            db_record = db_by_path.get(file_path)
            fm = fs_item.get("frontmatter", {})

            latest_stat = None
            if db_record:
                seen_db_ids.add(db_record.id)
                latest_stat = _latest_stat(db_record)

            result.append({
                "id": db_record.id if db_record else None,
                "title": fs_item.get("title") or (db_record.title if db_record else ""),
                "slug": fs_item.get("slug") or (db_record.slug if db_record else ""),
                "status": db_record.status if db_record else "untracked",
                "structure_type": fm.get("structure_type") or (db_record.structure_type if db_record else None),
                "word_count": db_record.word_count if db_record else fs_item.get("word_count"),
                "publish_timestamp": db_record.publish_timestamp.isoformat() if db_record and db_record.publish_timestamp else None,
                "latest_read_count": latest_stat.read_count if latest_stat else 0,
                "is_hot": bool(latest_stat and (latest_stat.read_count or 0) > 500),
                "latest_share_count": latest_stat.share_count if latest_stat else 0,
                "latest_like_count": latest_stat.like_count if latest_stat else 0,
                "stats_count": len(db_record.stats) if db_record else 0,
                "stats_fetched_at": latest_stat.fetched_at.isoformat() if latest_stat and latest_stat.fetched_at else None,
            })

        # Include DB-only articles (not in filesystem)
        for db_art in db_articles:
            if db_art.id in seen_db_ids:
                continue
            latest_stat = _latest_stat(db_art)
            result.append({
                "id": db_art.id,
                "title": db_art.title or "",
                "slug": db_art.slug or "",
                "status": db_art.status,
                "structure_type": db_art.structure_type,
                "word_count": db_art.word_count,
                "publish_timestamp": db_art.publish_timestamp.isoformat() if db_art.publish_timestamp else None,
                "latest_read_count": latest_stat.read_count if latest_stat else 0,
                "is_hot": bool(latest_stat and (latest_stat.read_count or 0) > 500),
                "latest_share_count": latest_stat.share_count if latest_stat else 0,
                "latest_like_count": latest_stat.like_count if latest_stat else 0,
                "stats_count": len(db_art.stats) if db_art.stats else 0,
                "stats_fetched_at": latest_stat.fetched_at.isoformat() if latest_stat and latest_stat.fetched_at else None,
            })

        # Sort by read_count desc (backend side)
        result.sort(key=lambda x: x["latest_read_count"], reverse=True)
        return success_response(result)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@analytics_bp.route("/analytics/articles/<int:article_id>/trend")
def article_trend(article_id):
    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            return error_response("Article not found", 404)

        fallback = datetime.min.replace(tzinfo=timezone.utc)
        stats = sorted(article.stats, key=lambda s: s.fetched_at or fallback)
        trend = [
            {
                "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
                "read_count": s.read_count,
                "share_count": s.share_count,
                "like_count": s.like_count,
                "comment_count": s.comment_count,
            }
            for s in stats
        ]

        return success_response({
            "article": {"id": article.id, "title": article.title},
            "trend": trend,
        })
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@analytics_bp.route("/analytics/fetch-stats", methods=["POST"])
def fetch_stats():
    from config import Config
    from services.article_service import scan_articles_dir, infer_structure_type
    if not Config.WECHAT_APP_ID or not Config.WECHAT_APP_SECRET:
        return error_response(
            "WECHAT_APP_ID 或 WECHAT_APP_SECRET 未配置，无法拉取微信真实阅读数据。请在 backend/.env 中配置后重启后端。",
            400,
        )

    db = SessionLocal()
    try:
        # ── 步骤 1：Upsert 本地文章到数据库 ──
        fs_articles = scan_articles_dir(Config.ARTICLES_DIR)
        db_articles = db.query(Article).all()
        db_by_path = {a.file_path: a for a in db_articles if a.file_path}

        for fs_item in fs_articles:
            file_path = fs_item["file_path"]
            fm = fs_item.get("frontmatter", {})
            if file_path not in db_by_path:
                slug = fs_item.get("slug") or ""
                existing = db.query(Article).filter(Article.slug == slug).first()
                if existing:
                    import re
                    slug = re.sub(r'-\d+$', '', slug) + f"-{random.randint(1000,9999)}"
                art = Article(
                    title=fs_item.get("title") or slug,
                    slug=slug,
                    file_path=file_path,
                    status="draft",  # 先标记为草稿，后面根据微信数据更新
                    structure_type=fm.get("structure_type") or infer_structure_type(fs_item.get("title", ""), fs_item.get("content", "")),
                    word_count=fs_item.get("word_count"),
                    image_count=fs_item.get("image_count"),
                )
                db.add(art)
                db_by_path[file_path] = art
                db_articles.append(art)
            else:
                # 已有记录：补充 structure_type（如果为空）
                db_rec = db_by_path[file_path]
                if not db_rec.structure_type:
                    db_rec.structure_type = fm.get("structure_type") or infer_structure_type(fs_item.get("title", ""), fs_item.get("content", ""))
        db.flush()

        # ── 步骤 2：从微信获取已发布文章列表，更新状态和发布时间 ──
        from services.wechat_service import get_published_articles
        published_on_wechat = {}
        wechat_publish_error = None
        try:
            published_on_wechat = get_published_articles()
        except RuntimeError as e:
            wechat_publish_error = str(e)

        synced = 0
        if published_on_wechat:
            published_lookup = _title_lookup(published_on_wechat)
            for article in db_articles:
                if article.id is None:
                    continue
                title_key = (article.title or "").strip()
                wx_info = _match_by_title(published_on_wechat, published_lookup, title_key)
                if wx_info:
                    article.status = "published"
                    if wx_info.get("update_time"):
                        article.publish_timestamp = wx_info["update_time"]
                    synced += 1
                # 未匹配的保持 draft 状态

        # ── 步骤 3：从微信 datacube 拉取阅读数据 ──
        from services.wechat_service import fetch_real_stats
        wechat_data = {}
        wechat_stats_error = None
        try:
            wechat_data = fetch_real_stats(days_back=90)
        except RuntimeError as e:
            wechat_stats_error = str(e)

        # 更新统计数据（upsert：已有则更新，没有则创建）
        # 注意：API 只返回近 90 天有活动的文章，老文章可能不在 API 结果中。
        # 对于已有数据的文章，只在 API 数据更大时才更新（防止降级）。
        stats_updated = 0
        wechat_stats_lookup = _title_lookup(wechat_data)
        for article in db_articles:
            if article.id is None:
                continue
            title_key = (article.title or "").strip()
            wx_stats = _match_by_title(wechat_data, wechat_stats_lookup, title_key)
            if not wx_stats:
                continue

            new_reads = wx_stats.get("int_page_read_count", 0)
            new_shares = wx_stats.get("share_count", 0)
            new_likes = wx_stats.get("add_to_fav_count", 0)
            new_comments = wx_stats.get("ori_page_read_count", 0)

            # 查找已有的统计记录
            existing_stat = (
                db.query(ArticleStat)
                .filter(ArticleStat.article_id == article.id)
                .order_by(ArticleStat.fetched_at.desc(), ArticleStat.id.desc())
                .first()
            )

            if existing_stat:
                # WeChat is the source of truth; overwrite stale imported stats.
                existing_stat.read_count = new_reads
                existing_stat.share_count = new_shares
                existing_stat.like_count = new_likes
                existing_stat.comment_count = new_comments
                existing_stat.share_rate = round(new_shares / new_reads, 4) if new_reads > 0 else 0.0
                existing_stat.like_rate = round(new_likes / new_reads, 4) if new_reads > 0 else 0.0
                existing_stat.fetched_at = utcnow()
            else:
                share_rate = round(new_shares / new_reads, 4) if new_reads > 0 else 0.0
                like_rate = round(new_likes / new_reads, 4) if new_reads > 0 else 0.0
                db.add(ArticleStat(
                    article_id=article.id,
                    read_count=new_reads,
                    share_count=new_shares,
                    like_count=new_likes,
                    comment_count=new_comments,
                    share_rate=share_rate,
                    like_rate=like_rate,
                    fetched_at=utcnow(),
                ))
            stats_updated += 1

        db.commit()

        # 构造错误信息（如果有）
        errors = []
        if wechat_publish_error:
            errors.append(f"文章列表拉取失败: {wechat_publish_error}")
        if wechat_stats_error:
            errors.append(f"统计数据拉取失败: {wechat_stats_error}")

        return success_response({
            "updated": stats_updated,
            "synced": synced,
            "wechat_articles_found": len(wechat_data),
            "published_on_wechat": len(published_on_wechat),
            "errors": errors,
        })
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@analytics_bp.route("/analytics/insights")
def insights():
    db = SessionLocal()
    try:
        dimension = request.args.get("dimension", "structure_type")

        from config import Config
        from services.article_service import scan_articles_dir
        fs_articles = scan_articles_dir(Config.ARTICLES_DIR)
        db_articles = db.query(Article).all()
        db_by_path = {a.file_path: a for a in db_articles}

        # Build unified article list with structure_type and latest stats
        class _Art:
            pass
        unified = []
        seen_db_ids = set()
        for fs_item in fs_articles:
            fp = fs_item["file_path"]
            db_rec = db_by_path.get(fp)
            fm = fs_item.get("frontmatter", {})
            a = _Art()
            a.structure_type = fm.get("structure_type") or (db_rec.structure_type if db_rec else None)
            a.word_count = db_rec.word_count if db_rec else fs_item.get("word_count")
            a.stats = db_rec.stats if db_rec else []
            unified.append(a)
            if db_rec:
                seen_db_ids.add(db_rec.id)

        for db_rec in db_articles:
            if db_rec.id in seen_db_ids:
                continue
            a = _Art()
            a.structure_type = db_rec.structure_type
            a.word_count = db_rec.word_count
            a.stats = db_rec.stats or []
            unified.append(a)

        articles = unified

        if dimension == "structure_type":
            buckets = {}
            for article in articles:
                label = article.structure_type or "未分类"
                latest_stat = _latest_stat(article)
                reads = latest_stat.read_count if latest_stat else 0
                if label not in buckets:
                    buckets[label] = {"total_reads": 0, "count": 0}
                buckets[label]["total_reads"] += reads
                buckets[label]["count"] += 1

            result = [
                {
                    "label": label,
                    "avg_reads": round(vals["total_reads"] / vals["count"]) if vals["count"] > 0 else 0,
                    "count": vals["count"],
                }
                for label, vals in buckets.items()
            ]
            result.sort(key=lambda x: x["avg_reads"], reverse=True)

        elif dimension == "word_count_bucket":
            bucket_defs = [
                ("<2000字", lambda wc: wc is not None and wc < 2000),
                ("2000-3000字", lambda wc: wc is not None and 2000 <= wc < 3000),
                ("3000-4000字", lambda wc: wc is not None and 3000 <= wc < 4000),
                ("4000+字", lambda wc: wc is not None and wc >= 4000),
            ]

            buckets = {label: {"total_reads": 0, "count": 0} for label, _ in bucket_defs}

            for article in articles:
                matched_label = None
                for label, condition in bucket_defs:
                    if condition(article.word_count):
                        matched_label = label
                        break
                if not matched_label:
                    continue

                latest_stat = _latest_stat(article)
                reads = latest_stat.read_count if latest_stat else 0
                buckets[matched_label]["total_reads"] += reads
                buckets[matched_label]["count"] += 1

            result = [
                {
                    "label": label,
                    "avg_reads": round(buckets[label]["total_reads"] / buckets[label]["count"]) if buckets[label]["count"] > 0 else 0,
                    "count": buckets[label]["count"],
                }
                for label, _ in bucket_defs
            ]
        else:
            return error_response(f"不支持的 dimension: {dimension}", 400)

        return success_response(result)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()
