import os
from flask import Blueprint, request
from database import SessionLocal
from models import Article, ArticleStat
from services.article_service import scan_articles_dir, parse_frontmatter
from utils import success_response, error_response

articles_bp = Blueprint("articles", __name__)


@articles_bp.route("/articles")
def list_articles():
    from config import Config

    db = SessionLocal()
    try:
        db_articles = db.query(Article).all()
        db_by_path = {a.file_path: a for a in db_articles}

        fs_articles = scan_articles_dir(Config.ARTICLES_DIR)

        result = []
        seen_paths = set()

        for fs_item in fs_articles:
            file_path = fs_item["file_path"]
            seen_paths.add(file_path)
            db_record = db_by_path.get(file_path)

            item = {
                "id": db_record.id if db_record else None,
                "title": fs_item.get("title") or (db_record.title if db_record else ""),
                "slug": fs_item.get("slug") or (db_record.slug if db_record else ""),
                "file_path": file_path,
                "filename": fs_item["filename"],
                "status": db_record.status if db_record else "untracked",
                "media_id": db_record.media_id if db_record else None,
                "word_count": db_record.word_count if db_record else fs_item.get("word_count"),
                "image_count": db_record.image_count if db_record else fs_item.get("image_count"),
                "created_at": db_record.created_at.isoformat() if db_record and db_record.created_at else None,
                "updated_at": db_record.updated_at.isoformat() if db_record and db_record.updated_at else None,
                "frontmatter": fs_item.get("frontmatter", {}),
            }
            result.append(item)

        for file_path, db_record in db_by_path.items():
            if file_path not in seen_paths:
                item = {
                    "id": db_record.id,
                    "title": db_record.title,
                    "slug": db_record.slug,
                    "file_path": file_path,
                    "filename": os.path.basename(file_path) if file_path else "",
                    "status": db_record.status,
                    "media_id": db_record.media_id,
                    "word_count": db_record.word_count,
                    "image_count": db_record.image_count,
                    "created_at": db_record.created_at.isoformat() if db_record.created_at else None,
                    "updated_at": db_record.updated_at.isoformat() if db_record.updated_at else None,
                    "frontmatter": {},
                }
                result.append(item)

        return success_response(result)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


def _latest_stat(article):
    if not article.stats:
        return None
    from datetime import datetime, timezone

    fallback = datetime.min.replace(tzinfo=timezone.utc)
    return max(article.stats, key=lambda s: s.fetched_at or fallback)


@articles_bp.route("/articles/hot-references")
def hot_reference_articles():
    from sqlalchemy import func

    db = SessionLocal()
    try:
        result = []
        latest_stats = (
            db.query(
                ArticleStat.article_id.label("article_id"),
                func.max(ArticleStat.fetched_at).label("latest_fetched_at"),
            )
            .group_by(ArticleStat.article_id)
            .subquery()
        )
        rows = (
            db.query(Article, ArticleStat.read_count)
            .join(latest_stats, latest_stats.c.article_id == Article.id)
            .join(
                ArticleStat,
                (ArticleStat.article_id == latest_stats.c.article_id)
                & (ArticleStat.fetched_at == latest_stats.c.latest_fetched_at),
            )
            .filter(ArticleStat.read_count > 500)
            .order_by(ArticleStat.read_count.desc())
            .limit(100)
            .all()
        )
        for article, read_count in rows:
            if not article.file_path or not os.path.exists(article.file_path):
                continue
            result.append({
                "slug": article.slug,
                "title": article.title,
                "read_count": read_count,
            })

        return success_response(result)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@articles_bp.route("/articles/generate", methods=["POST"])
def generate_article():
    """Start an article generation task and return task_id."""
    from services.task_manager import task_manager
    from services.generate_service import run_generate

    body = request.get_json(silent=True) or {}
    topic = body.get("topic", "").strip()
    if not topic:
        return error_response("topic 不能为空", 400)

    benchmark_slug = body.get("benchmark_slug")
    reference_article_slug = body.get("reference_article_slug")
    material_ids = body.get("material_ids") or []
    knowledge_chunk_ids = body.get("knowledge_chunk_ids") or []
    context_parts = [
        part
        for part in [
            _build_material_context(material_ids),
            _build_knowledge_context(knowledge_chunk_ids),
        ]
        if part
    ]
    context_hint = "\n\n".join(context_parts)

    task_id = task_manager.create_task("generate", meta={"topic": topic})
    task_manager.run(task_id, run_generate, topic, benchmark_slug, reference_article_slug, context_hint)

    return success_response({"task_id": task_id})


@articles_bp.route("/articles/<path:slug>/rewrite-for-publish", methods=["POST"])
def rewrite_article_for_publish(slug):
    from services.rewrite_service import run_rewrite_for_publish
    from services.task_manager import task_manager

    body = request.get_json(silent=True) or {}
    reference_benchmark_id = body.get("reference_benchmark_id")
    task_id = task_manager.create_task(
        "rewrite_publish",
        meta={"slug": slug, "reference_benchmark_id": reference_benchmark_id},
    )
    task_manager.run(task_id, run_rewrite_for_publish, slug, reference_benchmark_id)
    return success_response({"task_id": task_id})


@articles_bp.route("/articles/<path:slug>/publish", methods=["POST"])
def publish_article(slug):
    """Start a publish task and return task_id."""
    from config import Config
    from services.task_manager import task_manager
    from services.publish_service import run_publish

    file_path = None
    db = SessionLocal()
    try:
        db_record = db.query(Article).filter(Article.slug == slug).first()
        if db_record and db_record.file_path and os.path.exists(db_record.file_path):
            file_path = db_record.file_path
    finally:
        db.close()

    if not file_path:
        candidate = os.path.join(Config.ARTICLES_DIR, f"{slug}.md")
        if os.path.exists(candidate):
            file_path = candidate

    if not file_path:
        return error_response(f"找不到文章文件：{slug}", 404)

    task_id = task_manager.create_task("publish", meta={"slug": slug, "file_path": file_path})
    task_manager.run(task_id, run_publish, file_path)

    return success_response({"task_id": task_id})


def _build_material_context(material_ids) -> str:
    if not isinstance(material_ids, list) or not material_ids:
        return ""
    ids = [int(item) for item in material_ids if str(item).isdigit()]
    if not ids:
        return ""
    from services.article_service import parse_frontmatter
    from models import Benchmark

    db = SessionLocal()
    try:
        records = db.query(Benchmark).filter(Benchmark.id.in_(ids)).all()
        parts = []
        for bm in records:
            if not bm.file_path or not os.path.exists(bm.file_path):
                continue
            parsed = parse_frontmatter(bm.file_path)
            content = (parsed.get("content") or "").strip()
            if content:
                source = bm.source_url or bm.platform or "local"
                parts.append(f"### {bm.title}\nSource: {source}\n\n{content[:3000]}")
        if not parts:
            return ""
        return "\n\n## Fact materials for citation\n\n" + "\n\n".join(parts)
    finally:
        db.close()


MAX_KNOWLEDGE_CHUNKS = 5
MAX_KNOWLEDGE_CONTEXT_CHARS = 8000
MAX_KNOWLEDGE_CHUNK_CHARS = 3000


def _build_knowledge_context(knowledge_chunk_ids: list[int]) -> str:
    if not isinstance(knowledge_chunk_ids, list) or not knowledge_chunk_ids:
        return ""
    ids = []
    seen_ids = set()
    for item in knowledge_chunk_ids:
        if not str(item).isdigit():
            continue
        chunk_id = int(item)
        if chunk_id in seen_ids:
            continue
        ids.append(chunk_id)
        seen_ids.add(chunk_id)
        if len(ids) >= MAX_KNOWLEDGE_CHUNKS:
            break
    if not ids:
        return ""

    from models import KnowledgeChunk, KnowledgeFile

    db = SessionLocal()
    try:
        rows = (
            db.query(KnowledgeChunk, KnowledgeFile)
            .join(KnowledgeFile, KnowledgeFile.id == KnowledgeChunk.file_id)
            .filter(KnowledgeChunk.id.in_(ids))
            .all()
        )
        by_id = {chunk.id: (chunk, file) for chunk, file in rows}
        parts = []
        remaining_chars = MAX_KNOWLEDGE_CONTEXT_CHARS
        for chunk_id in ids:
            row = by_id.get(chunk_id)
            if not row:
                continue
            chunk, file = row
            content = (chunk.content or "").strip()
            if not content:
                continue
            if remaining_chars <= 0:
                break
            title = chunk.title or file.original_filename or file.filename or f"Knowledge chunk {chunk.id}"
            source = file.original_filename or file.filename or file.file_path or "knowledge base"
            snippet = content[: min(MAX_KNOWLEDGE_CHUNK_CHARS, remaining_chars)]
            parts.append(f"### {title}\nSource: {source}\n\n{snippet}")
            remaining_chars -= len(snippet)
        if not parts:
            return ""
        return "\n\n## Knowledge base snippets\n\n" + "\n\n".join(parts)
    finally:
        db.close()


@articles_bp.route("/articles/<int:article_id>", methods=["DELETE"])
def delete_article(article_id):
    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            return error_response("Article not found", 404)

        if article.media_id:
            return error_response("已发布的文章不能删除", 400)

        title = article.title
        db.delete(article)
        db.commit()
        return success_response({"deleted": article_id, "title": title})
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@articles_bp.route("/articles/<int:article_id>")
def get_article(article_id):
    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            return error_response("Article not found", 404)

        parsed = parse_frontmatter(article.file_path)

        data = {
            "id": article.id,
            "title": article.title,
            "slug": article.slug,
            "file_path": article.file_path,
            "status": article.status,
            "media_id": article.media_id,
            "word_count": article.word_count,
            "image_count": article.image_count,
            "topic_id": article.topic_id,
            "benchmark_id": article.benchmark_id,
            "structure_type": article.structure_type,
            "publish_timestamp": article.publish_timestamp.isoformat() if article.publish_timestamp else None,
            "created_at": article.created_at.isoformat() if article.created_at else None,
            "updated_at": article.updated_at.isoformat() if article.updated_at else None,
            "frontmatter": parsed["frontmatter"],
            "content": parsed["content"],
        }
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@articles_bp.route("/articles/by-slug/<path:slug>")
def get_article_by_slug(slug):
    from config import Config

    db = SessionLocal()
    try:
        db_record = db.query(Article).filter(Article.slug == slug).first()

        file_path = None
        if db_record and db_record.file_path and os.path.exists(db_record.file_path):
            file_path = db_record.file_path
        else:
            articles_dir = Config.ARTICLES_DIR
            for fname in os.listdir(articles_dir):
                if not fname.endswith(".md"):
                    continue
                candidate_slug = os.path.splitext(fname)[0]
                if candidate_slug == slug:
                    file_path = os.path.join(articles_dir, fname)
                    break

        if not file_path or not os.path.exists(file_path):
            return error_response("Article not found", 404)

        parsed = parse_frontmatter(file_path)

        data = {
            "id": db_record.id if db_record else None,
            "title": parsed["frontmatter"].get("title") or (db_record.title if db_record else slug),
            "slug": slug,
            "file_path": file_path,
            "status": db_record.status if db_record else "untracked",
            "media_id": db_record.media_id if db_record else None,
            "word_count": db_record.word_count if db_record else parsed.get("word_count"),
            "image_count": db_record.image_count if db_record else parsed.get("image_count"),
            "created_at": db_record.created_at.isoformat() if db_record and db_record.created_at else None,
            "updated_at": db_record.updated_at.isoformat() if db_record and db_record.updated_at else None,
            "frontmatter": parsed["frontmatter"],
            "content": parsed["content"],
        }
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()
