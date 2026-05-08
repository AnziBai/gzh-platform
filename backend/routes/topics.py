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

    task_id = task_manager.create_task("scrape", meta={"platform": platform})
    task_manager.run(task_id, run_scrape, platform)
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


def _serialize(t: Topic) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "platform": t.platform,
        "source_url": t.source_url,
        "hot_value": t.hot_value,
        "relevance_score": t.relevance_score,
        "relevance_reason": t.relevance_reason,
        "status": t.status,
        "discovered_at": t.discovered_at.isoformat() if t.discovered_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
