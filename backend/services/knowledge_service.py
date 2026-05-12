from __future__ import annotations

import hashlib
import json
import re
import uuid
from io import BytesIO
from pathlib import Path

from models import KnowledgeChunk, KnowledgeFile

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UnsupportedKnowledgeFile(Exception):
    pass


class KnowledgeParseError(Exception):
    pass


def parse_uploaded_text(filename: str, content: bytes) -> str:
    if len(content) > MAX_UPLOAD_BYTES:
        raise KnowledgeParseError("Knowledge file exceeds the 10MB upload limit.")

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedKnowledgeFile(f"Unsupported knowledge file type: {extension or 'unknown'}")

    if extension in {".md", ".txt"}:
        return _normalize_text(content.decode("utf-8", errors="replace"))

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeParseError("PDF parsing dependency is missing. Install pypdf to upload PDFs.") from exc

    try:
        reader = PdfReader(BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise KnowledgeParseError(f"Unable to parse PDF: {exc}") from exc
    return _normalize_text(text)


def save_uploaded_file(db, upload_dir: str, original_filename: str, content: bytes) -> dict:
    extension = Path(original_filename).suffix.lower()
    upload_path = Path(upload_dir)
    filename = f"{uuid.uuid4().hex}_{_safe_filename(original_filename)}"
    file_path = upload_path / filename

    record = KnowledgeFile(
        filename=filename,
        original_filename=Path(original_filename).name,
        file_type=extension.lstrip(".") or "unknown",
        file_path=str(file_path),
        status="processing",
        chunk_count=0,
    )
    db.add(record)
    db.flush()

    try:
        text = parse_uploaded_text(original_filename, content)
        if not text.strip():
            raise KnowledgeParseError("No usable text was parsed")
        upload_path.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        created_chunks = []
        seen_hashes = set()
        for item in chunk_text(text):
            if item["content_hash"] in seen_hashes:
                continue
            seen_hashes.add(item["content_hash"])
            created_chunks.append(
                KnowledgeChunk(
                    file_id=record.id,
                    chunk_index=len(created_chunks),
                    title=item.get("title"),
                    content=item["content"],
                    content_hash=item["content_hash"],
                    keywords_json=json.dumps(extract_keywords(item["content"]), ensure_ascii=False),
                )
            )

        db.add_all(created_chunks)
        record.status = "ready"
        record.chunk_count = len(created_chunks)
        record.error_message = None
        db.commit()
        db.refresh(record)
        return serialize_file(record)
    except (UnsupportedKnowledgeFile, KnowledgeParseError) as exc:
        if file_path.exists():
            file_path.unlink()
        db.rollback()
        record.status = "failed"
        record.error_message = str(exc)
        db.add(record)
        db.commit()
        raise
    except Exception as exc:
        if file_path.exists():
            file_path.unlink()
        db.rollback()
        record.status = "failed"
        record.error_message = str(exc)
        db.add(record)
        db.commit()
        raise KnowledgeParseError(f"Unable to save knowledge file: {exc}") from exc


def chunk_text(text: str, target_size: int = 1000) -> list[dict]:
    normalized = _normalize_text(text).strip()
    if not normalized:
        return []

    chunks = []
    current = ""
    for part in _split_parts(normalized):
        if not current:
            current = part
            continue
        separator = "\n\n" if "\n" in current or "\n" in part else " "
        candidate = f"{current}{separator}{part}"
        if len(candidate) <= target_size:
            current = candidate
            continue
        chunks.extend(_chunk_oversized(current, target_size))
        current = part
    if current:
        chunks.extend(_chunk_oversized(current, target_size))

    result = []
    title = None
    for content in (chunk for chunk in chunks if chunk.strip()):
        title = _first_markdown_heading(content) or title
        result.append(
            {
                "chunk_index": len(result),
                "title": title,
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "keywords": extract_keywords(content),
            }
        )
    return result


def extract_keywords(text: str, limit: int | None = None) -> list[str]:
    keywords = []
    seen = set()
    for match in re.finditer(r"[\w\u4e00-\u9fff]{2,}", text.lower()):
        token = match.group(0)
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if limit is not None and len(keywords) >= limit:
            break
    return keywords


def serialize_file(record: KnowledgeFile) -> dict:
    return {
        "id": record.id,
        "filename": record.filename,
        "original_filename": record.original_filename,
        "file_type": record.file_type,
        "file_path": record.file_path,
        "status": record.status,
        "chunk_count": record.chunk_count,
        "error_message": record.error_message,
        "created_at": _isoformat(record.created_at),
        "updated_at": _isoformat(record.updated_at),
    }


def serialize_chunk(record: KnowledgeChunk, reason: str | None = None, score: float | None = None) -> dict:
    payload = {
        "id": record.id,
        "file_id": record.file_id,
        "chunk_index": record.chunk_index,
        "title": record.title,
        "content": record.content,
        "content_hash": record.content_hash,
        "keywords": _load_keywords(record.keywords_json),
        "created_at": _isoformat(record.created_at),
    }
    if reason is not None:
        payload["reason"] = reason
    if score is not None:
        payload["score"] = score
    return payload


def delete_file(db, file_id: int) -> bool:
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if record is None:
        return False

    file_path = Path(record.file_path)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.file_id == file_id).delete()
    db.delete(record)
    db.commit()

    if file_path.exists():
        file_path.unlink()
    return True


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _safe_filename(filename: str) -> str:
    name = Path(filename).name or "knowledge"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return safe or "knowledge"


def _first_markdown_heading(text: str) -> str | None:
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _split_parts(text: str) -> list[str]:
    parts = re.split(r"\n{2,}", text)
    return [part.strip() for part in parts if part.strip()]


def _chunk_oversized(text: str, target_size: int) -> list[str]:
    if len(text) <= target_size:
        return [text.strip()]

    chunks = []
    current = ""
    for word in re.split(r"(\s+)", text):
        if not word:
            continue
        if current and len(current) + len(word) > target_size:
            chunks.append(current.strip())
            current = word.lstrip()
        else:
            current += word
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _load_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _isoformat(value) -> str | None:
    return value.isoformat() if value else None
