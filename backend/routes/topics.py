import json

from flask import Blueprint, request
from database import SessionLocal
from models import Topic
from utils import success_response, error_response

topics_bp = Blueprint("topics", __name__)


@topics_bp.route("/topics")
def list_topics():
    db = SessionLocal()
    try:
        status = request.args.get("status")
        q = db.query(Topic).order_by(Topic.discovered_at.desc())
        if status:
            q = q.filter(Topic.status == status)
        topics = q.limit(200).all()
        return success_response([_serialize(t) for t in topics])
    except Exception as e:
        return error_response(str(e), 500)
    finally:
        db.close()


@topics_bp.route("/topics/scrape", methods=["POST"])
def scrape_topics():
    from services.task_manager import task_manager
    from services.scraper_service import run_scrape

    body = request.get_json(silent=True) or {}
    platform = body.get("platform", "toutiao")
    source_group = body.get("source_group", "finance")
    mode = body.get("mode", "selected")
    category = body.get("category")
    since_hours = body.get("since_hours")
    keyword = body.get("keyword")

    task_id = task_manager.create_task("scrape", meta={"platform": platform, "source_group": source_group})
    task_manager.run(task_id, run_scrape, platform, source_group, mode, category, since_hours, keyword)
    return success_response({"task_id": task_id})


@topics_bp.route("/topics/<int:topic_id>/select", methods=["POST"])
def select_topic(topic_id):
    db = SessionLocal()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            return error_response("Topic not found", 404)
        topic.status = "selected"
        db.commit()
        return success_response(_serialize(topic))
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@topics_bp.route("/topics/<int:topic_id>/dismiss", methods=["POST"])
def dismiss_topic(topic_id):
    db = SessionLocal()
    try:
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        if not topic:
            return error_response("Topic not found", 404)
        topic.status = "dismissed"
        db.commit()
        return success_response(_serialize(topic))
    except Exception as e:
        db.rollback()
        return error_response(str(e), 500)
    finally:
        db.close()


@topics_bp.route("/topics/<int:topic_id>/brief", methods=["POST"])
def generate_topic_brief(topic_id):
    from services.task_manager import task_manager
    from services.topic_workflow_service import run_generate_brief

    body = request.get_json(silent=True) or {}
    material_ids = body.get("material_ids") or []
    reference_article_slug = body.get("reference_article_slug")
    knowledge_chunk_ids = body.get("knowledge_chunk_ids") or []

    task_id = task_manager.create_task("topic_brief", meta={"topic_id": topic_id})
    task_manager.run(task_id, run_generate_brief, topic_id, material_ids, reference_article_slug, knowledge_chunk_ids)
    return success_response({"task_id": task_id})


@topics_bp.route("/topics/<int:topic_id>/generate", methods=["POST"])
def generate_topic_article(topic_id):
    from services.task_manager import task_manager
    from services.topic_workflow_service import run_generate_from_topic

    task_id = task_manager.create_task("generate", meta={"topic_id": topic_id})
    task_manager.run(task_id, run_generate_from_topic, topic_id)
    return success_response({"task_id": task_id})


def _serialize(t: Topic) -> dict:
    material_ids = []
    knowledge_chunk_ids = _load_list_json(t.knowledge_chunk_ids_json)
    brief = None
    if t.material_ids_json:
        try:
            material_ids = json.loads(t.material_ids_json)
        except json.JSONDecodeError:
            material_ids = []
    if t.brief_json:
        try:
            brief = json.loads(t.brief_json)
        except json.JSONDecodeError:
            brief = None
    return {
        "id": t.id,
        "title": t.title,
        "platform": t.platform,
        "source_url": t.source_url,
        "hot_value": t.hot_value,
        "relevance_score": t.relevance_score,
        "relevance_reason": t.relevance_reason,
        "status": t.status,
        "brief": brief,
        "material_ids": material_ids,
        "knowledge_chunk_ids": knowledge_chunk_ids,
        "reference_article_slug": t.reference_article_slug,
        "generated_article_id": t.generated_article_id,
        "discovered_at": t.discovered_at.isoformat() if t.discovered_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _load_list_json(raw) -> list:
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []
