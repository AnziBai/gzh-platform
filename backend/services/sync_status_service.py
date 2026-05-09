import json
from datetime import datetime, timezone

from models import SyncStatus


def utcnow():
    return datetime.now(timezone.utc)


def get_sync_status(db) -> dict:
    row = db.query(SyncStatus).filter(SyncStatus.id == 1).first()
    if not row:
        return {
            "status": "never",
            "message": "尚未同步",
            "result": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
        }

    result = None
    if row.result_json:
        try:
            result = json.loads(row.result_json)
        except ValueError:
            result = None

    return {
        "status": row.status,
        "message": row.message or "",
        "result": result,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def record_sync_success(db, result: dict) -> SyncStatus:
    now = utcnow()
    row = db.query(SyncStatus).filter(SyncStatus.id == 1).first()
    if not row:
        row = SyncStatus(id=1)
        db.add(row)

    updated = int((result or {}).get("updated") or 0)
    ambiguous = len((result or {}).get("ambiguous") or [])
    unmatched = len((result or {}).get("unmatched") or [])
    row.status = "success"
    row.message = f"更新 {updated} 篇，歧义 {ambiguous} 条，未匹配 {unmatched} 条"
    row.result_json = json.dumps(result or {}, ensure_ascii=False)
    row.started_at = row.started_at or now
    row.finished_at = now
    row.updated_at = now
    return row


def record_sync_failure(db, message: str, result: dict | None = None) -> SyncStatus:
    now = utcnow()
    row = db.query(SyncStatus).filter(SyncStatus.id == 1).first()
    if not row:
        row = SyncStatus(id=1)
        db.add(row)

    row.status = "failed"
    row.message = message
    row.result_json = json.dumps(result or {}, ensure_ascii=False)
    row.started_at = row.started_at or now
    row.finished_at = now
    row.updated_at = now
    return row
