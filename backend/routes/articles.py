import os
from flask import Blueprint, request
from database import SessionLocal
from models import Article
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

        # DB records whose files no longer exist on disk
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


@articles_bp.route("/articles/generate", methods=["POST"])
def generate_article():
    """触发 Claude Code 子进程生成文章，返回 task_id。"""
    from services.task_manager import task_manager
    from services.generate_service import run_generate

    body = request.get_json(silent=True) or {}
    topic = body.get("topic", "").strip()
    if not topic:
        return error_response("topic 不能为空", 400)

    benchmark_slug = body.get("benchmark_slug")

    task_id = task_manager.create_task("generate", meta={"topic": topic})
    task_manager.run(task_id, run_generate, topic, benchmark_slug)

    return success_response({"task_id": task_id})


@articles_bp.route("/articles/<path:slug>/publish", methods=["POST"])
def publish_article(slug):
    """触发 wenyan-mcp 发布文章，返回 task_id。"""
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


@articles_bp.route("/articles/<int:article_id>", methods=["DELETE"])
def delete_article(article_id):
    db = SessionLocal()
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            return error_response("Article not found", 404)

        # Don't allow deleting published articles with media_id
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
