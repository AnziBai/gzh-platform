from __future__ import annotations

import hashlib
import json
import re
import uuid
from io import BytesIO
from pathlib import Path

from models import Benchmark, KnowledgeChunk, KnowledgeFile

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_RECOMMENDATION_CANDIDATES = 1000


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
        for token in _expand_token(match.group(0)):
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if limit is not None and len(keywords) >= limit:
                return keywords
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


def delete_file(db, file_id: int, upload_root: str | None = None) -> bool:
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if record is None:
        return False

    file_path = Path(record.file_path)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.file_id == file_id).delete()
    db.delete(record)
    db.commit()

    if _is_path_within_root(file_path, upload_root) and file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass
    return True


def recommend_for_topic(
    db,
    topic: str,
    hotspot_title: str | None = None,
    knowledge_file_ids: list[int] | None = None,
    limit: int = 5,
    config=None,
) -> dict:
    query = " ".join([topic or "", hotspot_title or ""]).strip()
    tokens = set(extract_keywords(query, limit=30))

    chunk_query = db.query(KnowledgeChunk)
    if knowledge_file_ids is not None:
        chunk_query = chunk_query.filter(KnowledgeChunk.file_id.in_(knowledge_file_ids))
    chunk_query = chunk_query.order_by(KnowledgeChunk.id.desc()).limit(MAX_RECOMMENDATION_CANDIDATES)

    benchmark_query = db.query(Benchmark).order_by(Benchmark.relevance_score.desc(), Benchmark.id.desc())

    chunks = _rank_chunks(chunk_query.all(), tokens)[:limit]
    facts = _rank_benchmarks(
        benchmark_query.filter(Benchmark.material_type == "fact_material").limit(MAX_RECOMMENDATION_CANDIDATES).all(),
        tokens,
    )[:3]
    references = _rank_benchmarks(
        benchmark_query.filter(Benchmark.material_type == "reference_article").limit(MAX_RECOMMENDATION_CANDIDATES).all(),
        tokens,
    )[:3]

    result = {
        "knowledge_chunks": chunks,
        "fact_materials": facts,
        "reference_articles": references,
        "warnings": [],
    }
    if config is not None and chunks:
        try:
            return _ai_rerank_or_fallback(config, query, result)
        except Exception as exc:
            result["warnings"].append(f"AI rerank failed, used local ranking: {exc}")
    return result


def _rank_chunks(chunks: list[KnowledgeChunk], tokens: set[str]) -> list[dict]:
    ranked = []
    for chunk in chunks:
        score, reason = _score_text_match(
            tokens,
            [chunk.title, chunk.content, " ".join(_load_keywords(chunk.keywords_json))],
        )
        if score <= 0:
            continue
        ranked.append((score, chunk.id or 0, serialize_chunk(chunk, reason=reason, score=score)))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def _rank_benchmarks(benchmarks: list[Benchmark], tokens: set[str]) -> list[dict]:
    ranked = []
    for benchmark in benchmarks:
        match_score, reason = _score_text_match(
            tokens,
            [
                benchmark.title,
                benchmark.platform,
                benchmark.source_url,
                benchmark.file_path,
                benchmark.keywords,
                benchmark.classification_reason,
            ],
        )
        relevance_score = float(benchmark.relevance_score or 0)
        if match_score <= 0:
            continue

        score = match_score + relevance_score
        ranked.append((score, benchmark.id or 0, _serialize_benchmark(benchmark, reason, score)))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def _serialize_benchmark(record: Benchmark, reason: str | None = None, score: float | None = None) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "platform": record.platform,
        "source_url": record.source_url,
        "file_path": record.file_path,
        "material_type": record.material_type,
        "reason": reason,
        "score": score,
    }


def _ai_rerank_or_fallback(config, query: str, result: dict) -> dict:
    return result


def _score_text_match(tokens: set[str], values: list[str | None]) -> tuple[float, str | None]:
    if not tokens:
        return 0.0, None

    haystack_tokens = set()
    for value in values:
        if value:
            haystack_tokens.update(extract_keywords(value))

    matches = sorted(tokens.intersection(haystack_tokens))
    if not matches:
        return 0.0, None
    return float(len(matches)), f"Matched keywords: {', '.join(matches[:5])}"


def _expand_token(token: str) -> list[str]:
    expanded = [token]
    if re.search(r"[\u4e00-\u9fff]", token):
        expanded.extend(token[index : index + 2] for index in range(len(token) - 1))
    return expanded


def _normalize_text(text: str) -> str:
    text = text.lstrip("\ufeff")
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


def _is_path_within_root(file_path: Path, upload_root: str | None) -> bool:
    if not upload_root:
        return False

    try:
        resolved_file = file_path.resolve(strict=False)
        resolved_root = Path(upload_root).resolve(strict=False)
        resolved_file.relative_to(resolved_root)
    except (OSError, ValueError):
        return False
    return True


def _isoformat(value) -> str | None:
    return value.isoformat() if value else None
