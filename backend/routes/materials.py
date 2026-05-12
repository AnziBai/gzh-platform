from flask import Blueprint, request

from database import SessionLocal
from models import MaterialCandidate
from utils import error_response, success_response

materials_bp = Blueprint("materials", __name__)


@materials_bp.route("/materials/candidates")
def list_candidates():
    db = SessionLocal()
    try:
        status = request.args.get("status")
        q = db.query(MaterialCandidate).order_by(MaterialCandidate.created_at.desc())
        if status:
            q = q.filter(MaterialCandidate.status == status)
        return success_response([_serialize(candidate) for candidate in q.limit(300).all()])
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        db.close()


@materials_bp.route("/materials/collect", methods=["POST"])
def collect_materials():
    from services.material_collection_service import collect_from_articles, collect_from_search, collect_from_topic_ids
    from services.task_manager import task_manager

    body = request.get_json(silent=True) or {}
    source = body.get("source", "topics")
    task_id = task_manager.create_task("material_collect", meta={"source": source})

    if source == "articles":
        task_manager.run(task_id, collect_from_articles, False)
    elif source == "hot_articles":
        task_manager.run(task_id, collect_from_articles, True)
    elif source == "search":
        task_manager.run(task_id, collect_from_search, body.get("keyword", ""))
    else:
        task_manager.run(task_id, collect_from_topic_ids, body.get("topic_ids") or None)
    return success_response({"task_id": task_id})


@materials_bp.route("/materials/candidates/<int:candidate_id>/approve", methods=["POST"])
def approve(candidate_id):
    from services.material_collection_service import approve_candidate

    body = request.get_json(silent=True) or {}
    try:
        return success_response(approve_candidate(candidate_id, body.get("material_type")))
    except Exception as exc:
        return error_response(str(exc), 400)


@materials_bp.route("/materials/candidates/<int:candidate_id>/reject", methods=["POST"])
def reject(candidate_id):
    from services.material_collection_service import reject_candidate

    try:
        return success_response(reject_candidate(candidate_id))
    except Exception as exc:
        return error_response(str(exc), 400)


def _serialize(candidate: MaterialCandidate) -> dict:
    return {
        "id": candidate.id,
        "title": candidate.title,
        "content": candidate.content,
        "source_url": candidate.source_url,
        "platform": candidate.platform,
        "suggested_material_type": candidate.suggested_material_type,
        "status": candidate.status,
        "confidence": candidate.confidence,
        "classification_reason": candidate.classification_reason,
        "source_kind": candidate.source_kind,
        "topic_id": candidate.topic_id,
        "article_id": candidate.article_id,
        "source_hash": candidate.source_hash,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }
