import os

from flask import Blueprint, request

from config import Config
from database import SessionLocal
from models import KnowledgeFile
from services.knowledge_service import (
    KnowledgeParseError,
    UnsupportedKnowledgeFile,
    delete_file,
    recommend_for_topic,
    save_uploaded_file,
    serialize_file,
)
from utils import error_response, success_response

knowledge_bp = Blueprint("knowledge", __name__)


@knowledge_bp.route("/knowledge/files", methods=["POST"])
def upload_file():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return error_response("file is required", 400)

    db = SessionLocal()
    try:
        data = save_uploaded_file(
            db,
            upload_dir=os.path.join(Config.GZHPUBLISHER_ROOT, "knowledge"),
            original_filename=upload.filename,
            content=upload.read(),
        )
        return success_response(data)
    except (UnsupportedKnowledgeFile, KnowledgeParseError) as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        db.close()


@knowledge_bp.route("/knowledge/files")
def list_files():
    db = SessionLocal()
    try:
        rows = db.query(KnowledgeFile).order_by(KnowledgeFile.created_at.desc(), KnowledgeFile.id.desc()).all()
        return success_response([serialize_file(row) for row in rows])
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        db.close()


@knowledge_bp.route("/knowledge/files/<int:file_id>", methods=["DELETE"])
def remove_file(file_id):
    db = SessionLocal()
    try:
        upload_root = os.path.join(Config.GZHPUBLISHER_ROOT, "knowledge")
        return success_response({"deleted": delete_file(db, file_id, upload_root=upload_root)})
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        db.close()


@knowledge_bp.route("/knowledge/recommend", methods=["POST"])
def recommend():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return error_response("topic is required", 400)

    topic_value = body.get("topic")
    if not isinstance(topic_value, str):
        return error_response("topic is required", 400)

    topic = topic_value.strip()
    if not topic:
        return error_response("topic is required", 400)

    db = SessionLocal()
    try:
        result = recommend_for_topic(
            db,
            topic=topic,
            hotspot_title=body.get("hotspot_title"),
            knowledge_file_ids=body.get("knowledge_file_ids"),
            limit=body.get("limit", 5),
            config=Config,
        )
        return success_response(result)
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        db.close()
