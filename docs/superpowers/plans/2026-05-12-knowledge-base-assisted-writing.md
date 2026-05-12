# Knowledge Base Assisted Writing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a v1 knowledge base upload and recommendation workflow that lets users upload Markdown, TXT, and PDF files, retrieve relevant snippets for a topic/hotspot, and generate articles using knowledge snippets plus fact materials and viral reference articles.

**Architecture:** Add `KnowledgeFile` and `KnowledgeChunk` SQLite models, a focused parsing/recommendation service, and a `/api/knowledge` route. Extend existing article/topic generation to accept `knowledge_chunk_ids`, then surface upload and recommendation controls in the material library, article workshop, and hotspot brief modal.

**Tech Stack:** Flask, SQLAlchemy, SQLite, optional `pypdf`, React, TypeScript, Ant Design, React Query, existing task manager and AI client.

---

## File Structure

- Create `backend/services/knowledge_service.py`: file validation, upload persistence, text parsing, chunking, local retrieval, AI rerank fallback, serialization.
- Create `backend/routes/knowledge.py`: Flask endpoints for upload/list/delete/recommend.
- Modify `backend/models.py`: add `KnowledgeFile` and `KnowledgeChunk`; extend `Topic` with `knowledge_chunk_ids_json`.
- Modify `backend/database.py`: import new models and add idempotent topic column migration.
- Modify `backend/app.py`: register `knowledge_bp`.
- Modify `backend/routes/articles.py`: accept `knowledge_chunk_ids` and include knowledge context in generation.
- Modify `backend/routes/topics.py`: accept and serialize `knowledge_chunk_ids`.
- Modify `backend/services/topic_workflow_service.py`: store/load knowledge chunks for brief and generated article.
- Modify `backend/services/environment_check_service.py`: add optional PDF parser diagnostic.
- Add backend tests in `backend/tests/test_knowledge_service.py` and `backend/tests/test_knowledge_routes.py`.
- Modify existing backend tests where required: `backend/tests/test_database.py`, `backend/tests/test_article_references.py`.
- Create `frontend/src/api/knowledge.ts`: frontend API client and types.
- Modify `frontend/src/pages/BenchmarksPage.tsx`: add knowledge upload/list/delete section.
- Modify `frontend/src/pages/WorkshopPage.tsx`: add hotspot selector, knowledge scope selector, recommendation action, recommendation display, and generate payload.
- Modify `frontend/src/pages/TopicsPage.tsx`: add knowledge selector to creative brief modal and submit selected chunk IDs.
- Modify `frontend/src/api/articles.ts` and `frontend/src/api/topics.ts`: add `knowledge_chunk_ids`.

---

### Task 1: Backend Knowledge Models and Migration

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Write the failing database test**

Add this test to `backend/tests/test_database.py`:

```python
def test_init_db_creates_knowledge_tables_and_topic_column(self):
    init_db()

    with engine.connect() as conn:
        tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("knowledge_files", tables)
        self.assertIn("knowledge_chunks", tables)

        topic_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(topics)")}
        self.assertIn("knowledge_chunk_ids_json", topic_columns)
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest backend/tests/test_database.py::DatabaseTest::test_init_db_creates_knowledge_tables_and_topic_column -q
```

Expected: FAIL because the new tables and topic column do not exist.

- [ ] **Step 3: Add models**

Add to `backend/models.py`:

```python
class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="processing")
    chunk_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("knowledge_files.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    title = Column(String)
    content = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    keywords_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Add to `Topic`:

```python
knowledge_chunk_ids_json = Column(Text)
```

- [ ] **Step 4: Update database initialization**

In `backend/database.py`, import `KnowledgeFile` and `KnowledgeChunk` with the existing model imports. Add this topic migration entry:

```python
"knowledge_chunk_ids_json": "TEXT",
```

No manual `CREATE TABLE` is needed because `Base.metadata.create_all(bind=engine)` creates the new tables.

- [ ] **Step 5: Run database tests**

Run:

```powershell
python -m pytest backend/tests/test_database.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/models.py backend/database.py backend/tests/test_database.py
git commit -m "Add knowledge base database models"
```

---

### Task 2: Knowledge Parsing and Upload Service

**Files:**
- Create: `backend/services/knowledge_service.py`
- Test: `backend/tests/test_knowledge_service.py`

- [ ] **Step 1: Write service tests**

Create `backend/tests/test_knowledge_service.py`:

```python
import io
import tempfile
import unittest
from pathlib import Path

from database import Base, SessionLocal, engine
from services.knowledge_service import (
    UnsupportedKnowledgeFile,
    chunk_text,
    extract_keywords,
    parse_uploaded_text,
    save_uploaded_file,
)


class KnowledgeServiceTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()
        Base.metadata.drop_all(bind=engine)

    def test_parse_markdown_preserves_text(self):
        text = parse_uploaded_text("alpha.md", b"# Title\n\nImportant domain fact.")
        self.assertIn("Title", text)
        self.assertIn("Important domain fact", text)

    def test_parse_txt_reads_utf8(self):
        text = parse_uploaded_text("note.txt", "hello knowledge".encode("utf-8"))
        self.assertEqual(text, "hello knowledge")

    def test_unsupported_file_type_raises(self):
        with self.assertRaises(UnsupportedKnowledgeFile):
            parse_uploaded_text("sheet.xlsx", b"data")

    def test_chunk_text_splits_and_hashes(self):
        chunks = chunk_text("# Alpha\n" + ("risk control " * 160), target_size=300)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(item["content_hash"] for item in chunks))
        self.assertEqual(chunks[0]["title"], "Alpha")

    def test_extract_keywords_returns_unique_terms(self):
        keywords = extract_keywords("alpha beta alpha gamma")
        self.assertEqual(keywords[:3], ["alpha", "beta", "gamma"])

    def test_save_uploaded_file_creates_file_and_chunks(self):
        db = SessionLocal()
        try:
            result = save_uploaded_file(
                db,
                upload_dir=self.tmp.name,
                original_filename="kb.md",
                content=b"# KB\n\n" + b"alpha beta " * 200,
            )
            self.assertEqual(result["status"], "ready")
            self.assertGreater(result["chunk_count"], 0)
            self.assertTrue(Path(result["file_path"]).exists())
        finally:
            db.close()
```

- [ ] **Step 2: Run the failing service tests**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_service.py -q
```

Expected: FAIL because `knowledge_service.py` does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/services/knowledge_service.py` with these functions/classes:

```python
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from models import Benchmark, KnowledgeChunk, KnowledgeFile

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UnsupportedKnowledgeFile(RuntimeError):
    pass


class KnowledgeParseError(RuntimeError):
    pass


def parse_uploaded_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedKnowledgeFile("Only .md, .txt, and .pdf files are supported")
    if len(content) > MAX_UPLOAD_BYTES:
        raise KnowledgeParseError("File is larger than the 10 MB upload limit")
    if suffix in {".md", ".txt"}:
        return _clean_text(content.decode("utf-8", errors="replace"))
    return _parse_pdf(content)


def save_uploaded_file(db, upload_dir: str, original_filename: str, content: bytes) -> dict:
    file_type = Path(original_filename).suffix.lower().lstrip(".")
    safe_name = _safe_filename(original_filename)
    stored_name = f"{uuid.uuid4().hex}-{safe_name}"
    root = Path(upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / stored_name

    record = KnowledgeFile(
        filename=stored_name,
        original_filename=original_filename,
        file_type=file_type,
        file_path=str(file_path),
        status="processing",
    )
    db.add(record)
    db.flush()

    try:
        text = parse_uploaded_text(original_filename, content)
        if not text.strip():
            raise KnowledgeParseError("No usable text was parsed")
        file_path.write_bytes(content)
        chunks = chunk_text(text)
        created = 0
        seen_hashes = set()
        for item in chunks:
            if item["content_hash"] in seen_hashes:
                continue
            seen_hashes.add(item["content_hash"])
            db.add(KnowledgeChunk(
                file_id=record.id,
                chunk_index=created,
                title=item["title"],
                content=item["content"],
                content_hash=item["content_hash"],
                keywords_json=json.dumps(extract_keywords(item["content"]), ensure_ascii=False),
            ))
            created += 1
        record.status = "ready"
        record.chunk_count = created
        record.error_message = None
        db.commit()
    except Exception as exc:
        record.status = "failed"
        record.chunk_count = 0
        record.error_message = str(exc)
        db.commit()
        if isinstance(exc, UnsupportedKnowledgeFile):
            raise
        if isinstance(exc, KnowledgeParseError):
            raise
    return serialize_file(record)


def chunk_text(text: str, target_size: int = 1000) -> list[dict]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    blocks = re.split(r"\n(?=#{1,6}\s+)", cleaned)
    chunks = []
    current = ""
    current_title = None
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", block.splitlines()[0])
        if heading and not current_title:
            current_title = heading.group(1).strip()[:120]
        if current and len(current) + len(block) > target_size:
            chunks.extend(_split_large_block(current, current_title, target_size))
            current = block
            current_title = heading.group(1).strip()[:120] if heading else current_title
        else:
            current = f"{current}\n\n{block}".strip()
    if current:
        chunks.extend(_split_large_block(current, current_title, target_size))
    return chunks


def extract_keywords(text: str, limit: int = 20) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    result = []
    for token in tokens:
        if token not in result:
            result.append(token)
        if len(result) >= limit:
            break
    return result


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
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def serialize_chunk(record: KnowledgeChunk, reason: str | None = None, score: float | None = None) -> dict:
    return {
        "id": record.id,
        "file_id": record.file_id,
        "chunk_index": record.chunk_index,
        "title": record.title,
        "content": record.content,
        "content_hash": record.content_hash,
        "keywords": json.loads(record.keywords_json or "[]"),
        "reason": reason,
        "score": score,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def delete_file(db, file_id: int) -> bool:
    record = db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()
    if not record:
        return False
    db.query(KnowledgeChunk).filter(KnowledgeChunk.file_id == file_id).delete()
    path = record.file_path
    db.delete(record)
    db.commit()
    if path and os.path.exists(path):
        os.remove(path)
    return True


def _parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise KnowledgeParseError("PDF parsing dependency is missing. Install pypdf to upload PDFs.") from exc
    try:
        reader = PdfReader(__import__("io").BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return _clean_text("\n\n".join(pages))
    except Exception as exc:
        raise KnowledgeParseError(f"PDF parsing failed: {exc}") from exc


def _clean_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _split_large_block(text: str, title: str | None, target_size: int) -> list[dict]:
    parts = []
    start = 0
    while start < len(text):
        part = text[start:start + target_size].strip()
        if part:
            digest = hashlib.sha256(part.encode("utf-8")).hexdigest()
            parts.append({"title": title, "content": part, "content_hash": digest})
        start += target_size
    return parts


def _safe_filename(filename: str) -> str:
    stem = re.sub(r"[^\w.\-\u4e00-\u9fff]", "-", Path(filename).name).strip("-")
    return stem or "knowledge.txt"
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/knowledge_service.py backend/tests/test_knowledge_service.py
git commit -m "Add knowledge file parsing service"
```

---

### Task 3: Knowledge API Routes

**Files:**
- Create: `backend/routes/knowledge.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_knowledge_routes.py`

- [ ] **Step 1: Write route tests**

Create `backend/tests/test_knowledge_routes.py`:

```python
import io
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from database import Base, engine


class KnowledgeRoutesTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        Base.metadata.drop_all(bind=engine)

    @patch("routes.knowledge.Config")
    def test_upload_markdown_lists_and_deletes(self, config):
        config.GZHPUBLISHER_ROOT = self.tmp.name
        response = self.client.post(
            "/api/knowledge/files",
            data={"file": (io.BytesIO(b"# Alpha\n\nDomain knowledge."), "alpha.md")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        file_id = response.get_json()["data"]["id"]

        list_response = self.client.get("/api/knowledge/files")
        rows = list_response.get_json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["original_filename"], "alpha.md")

        delete_response = self.client.delete(f"/api/knowledge/files/{file_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.get_json()["data"]["deleted"])

    @patch("routes.knowledge.Config")
    def test_upload_rejects_unsupported_extension(self, config):
        config.GZHPUBLISHER_ROOT = self.tmp.name
        response = self.client.post(
            "/api/knowledge/files",
            data={"file": (io.BytesIO(b"x"), "alpha.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_recommend_requires_topic(self):
        response = self.client.post("/api/knowledge/recommend", json={"topic": ""})
        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Run failing route tests**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_routes.py -q
```

Expected: FAIL because route does not exist.

- [ ] **Step 3: Implement route**

Create `backend/routes/knowledge.py`:

```python
from flask import Blueprint, request

from config import Config
from database import SessionLocal
from models import KnowledgeFile
from routes import error_response, success_response
from services.knowledge_service import (
    KnowledgeParseError,
    UnsupportedKnowledgeFile,
    delete_file,
    recommend_for_topic,
    save_uploaded_file,
    serialize_file,
)

knowledge_bp = Blueprint("knowledge", __name__)


@knowledge_bp.route("/knowledge/files", methods=["POST"])
def upload_knowledge_file():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return error_response("file is required", 400)
    db = SessionLocal()
    try:
        upload_dir = f"{Config.GZHPUBLISHER_ROOT}/knowledge"
        result = save_uploaded_file(db, upload_dir, upload.filename, upload.read())
        return success_response(result)
    except UnsupportedKnowledgeFile as exc:
        return error_response(str(exc), 400)
    except KnowledgeParseError as exc:
        return error_response(str(exc), 400)
    finally:
        db.close()


@knowledge_bp.route("/knowledge/files", methods=["GET"])
def list_knowledge_files():
    db = SessionLocal()
    try:
        rows = db.query(KnowledgeFile).order_by(KnowledgeFile.created_at.desc()).all()
        return success_response([serialize_file(row) for row in rows])
    finally:
        db.close()


@knowledge_bp.route("/knowledge/files/<int:file_id>", methods=["DELETE"])
def delete_knowledge_file(file_id):
    db = SessionLocal()
    try:
        return success_response({"deleted": delete_file(db, file_id)})
    finally:
        db.close()


@knowledge_bp.route("/knowledge/recommend", methods=["POST"])
def recommend_knowledge():
    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or "").strip()
    if not topic:
        return error_response("topic is required", 400)
    db = SessionLocal()
    try:
        result = recommend_for_topic(
            db,
            topic=topic,
            hotspot_title=body.get("hotspot_title"),
            knowledge_file_ids=body.get("knowledge_file_ids") or None,
            limit=int(body.get("limit") or 5),
            config=Config,
        )
        return success_response(result)
    finally:
        db.close()
```

Register in `backend/app.py`:

```python
from routes.knowledge import knowledge_bp
app.register_blueprint(knowledge_bp, url_prefix="/api")
```

- [ ] **Step 4: Add a temporary stub for recommendation**

If Task 4 is not complete yet, add this function to `knowledge_service.py` so route tests pass:

```python
def recommend_for_topic(db, topic: str, hotspot_title: str | None = None, knowledge_file_ids: list[int] | None = None, limit: int = 5, config=None) -> dict:
    return {"knowledge_chunks": [], "fact_materials": [], "reference_articles": [], "warnings": []}
```

- [ ] **Step 5: Run route tests**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/routes/knowledge.py backend/app.py backend/services/knowledge_service.py backend/tests/test_knowledge_routes.py
git commit -m "Add knowledge file API"
```

---

### Task 4: Knowledge Recommendation Service

**Files:**
- Modify: `backend/services/knowledge_service.py`
- Test: `backend/tests/test_knowledge_service.py`

- [ ] **Step 1: Add recommendation tests**

Append to `KnowledgeServiceTest`:

```python
    def test_recommend_for_topic_returns_ranked_chunks_and_materials(self):
        from models import Benchmark, KnowledgeChunk, KnowledgeFile
        from services.knowledge_service import recommend_for_topic

        db = SessionLocal()
        try:
            file = KnowledgeFile(
                filename="alpha.md",
                original_filename="alpha.md",
                file_type="md",
                file_path="alpha.md",
                status="ready",
                chunk_count=1,
            )
            db.add(file)
            db.flush()
            db.add(KnowledgeChunk(
                file_id=file.id,
                chunk_index=0,
                title="Risk Control",
                content="Risk control position sizing drawdown alpha",
                content_hash="hash-a",
                keywords_json='["risk","control","drawdown"]',
            ))
            db.add(Benchmark(
                title="Risk Case",
                platform="manual",
                material_type="fact_material",
                source_url="https://example.com/risk",
                file_path=None,
                relevance_score=0.5,
            ))
            db.add(Benchmark(
                title="Viral Trading Article",
                platform="manual",
                material_type="reference_article",
                source_url="https://example.com/ref",
                file_path=None,
                relevance_score=0.8,
            ))
            db.commit()

            result = recommend_for_topic(db, topic="risk control drawdown", config=None)
            self.assertEqual(result["knowledge_chunks"][0]["title"], "Risk Control")
            self.assertEqual(result["fact_materials"][0]["title"], "Risk Case")
            self.assertEqual(result["reference_articles"][0]["title"], "Viral Trading Article")
        finally:
            db.close()
```

- [ ] **Step 2: Run failing recommendation test**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_service.py::KnowledgeServiceTest::test_recommend_for_topic_returns_ranked_chunks_and_materials -q
```

Expected: FAIL if the stub returns empty results.

- [ ] **Step 3: Implement local retrieval and optional AI rerank**

Replace the stub in `knowledge_service.py` with:

```python
def recommend_for_topic(db, topic: str, hotspot_title: str | None = None, knowledge_file_ids: list[int] | None = None, limit: int = 5, config=None) -> dict:
    query = " ".join([topic or "", hotspot_title or ""]).strip()
    tokens = set(extract_keywords(query, limit=30))
    chunk_query = db.query(KnowledgeChunk)
    if knowledge_file_ids:
        chunk_query = chunk_query.filter(KnowledgeChunk.file_id.in_(knowledge_file_ids))
    chunks = _rank_chunks(chunk_query.all(), tokens)[:limit]
    facts = _rank_benchmarks(db.query(Benchmark).filter(Benchmark.material_type == "fact_material").all(), tokens)[:3]
    references = _rank_benchmarks(db.query(Benchmark).filter(Benchmark.material_type == "reference_article").all(), tokens)[:3]

    result = {
        "knowledge_chunks": [serialize_chunk(item["record"], item["reason"], item["score"]) for item in chunks],
        "fact_materials": [_serialize_benchmark(item["record"], item["reason"], item["score"]) for item in facts],
        "reference_articles": [_serialize_benchmark(item["record"], item["reason"], item["score"]) for item in references],
        "warnings": [],
    }
    if config is not None and chunks:
        try:
            return _ai_rerank_or_fallback(config, query, result)
        except Exception as exc:
            result["warnings"].append(f"AI rerank failed, used local ranking: {exc}")
    return result


def _rank_chunks(chunks: list[KnowledgeChunk], tokens: set[str]) -> list[dict]:
    rows = []
    for chunk in chunks:
        haystack = f"{chunk.title or ''} {chunk.content}".lower()
        score = sum(1 for token in tokens if token in haystack)
        if score > 0 or not tokens:
            rows.append({"record": chunk, "score": float(score), "reason": f"Matched {score} query keywords"})
    return sorted(rows, key=lambda item: item["score"], reverse=True)


def _rank_benchmarks(records: list[Benchmark], tokens: set[str]) -> list[dict]:
    rows = []
    for record in records:
        haystack = f"{record.title or ''} {record.source_url or ''}".lower()
        score = sum(1 for token in tokens if token in haystack) + float(record.relevance_score or 0)
        rows.append({"record": record, "score": float(score), "reason": f"Matched topic with score {score:.2f}"})
    return sorted(rows, key=lambda item: item["score"], reverse=True)


def _serialize_benchmark(record: Benchmark, reason: str | None = None, score: float | None = None) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "platform": record.platform,
        "source_url": record.source_url,
        "file_path": record.file_path,
        "material_type": record.material_type or "reference_article",
        "reason": reason,
        "score": score,
    }
```

Implement `_ai_rerank_or_fallback` as a conservative no-op first:

```python
def _ai_rerank_or_fallback(config, query: str, result: dict) -> dict:
    return result
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
python -m pytest backend/tests/test_knowledge_service.py backend/tests/test_knowledge_routes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/knowledge_service.py backend/tests/test_knowledge_service.py
git commit -m "Add knowledge recommendation retrieval"
```

---

### Task 5: Article Generation Uses Knowledge Chunks

**Files:**
- Modify: `backend/routes/articles.py`
- Modify: `backend/services/generate_service.py` only if current prompt assembly requires a helper
- Test: `backend/tests/test_article_references.py`

- [ ] **Step 1: Write generation route test**

Add to `backend/tests/test_article_references.py`:

```python
def test_generate_article_passes_knowledge_context(self):
    from models import KnowledgeChunk, KnowledgeFile

    db = SessionLocal()
    try:
        file = KnowledgeFile(filename="kb.md", original_filename="kb.md", file_type="md", file_path="kb.md", status="ready", chunk_count=1)
        db.add(file)
        db.flush()
        chunk = KnowledgeChunk(file_id=file.id, chunk_index=0, title="Internal Alpha", content="Internal alpha context", content_hash="kh")
        db.add(chunk)
        db.commit()
        chunk_id = chunk.id
    finally:
        db.close()

    with patch("routes.articles.task_manager") as manager, patch("routes.articles.run_generate") as run_generate:
        manager.create_task.return_value = "task-1"
        response = self.client.post("/api/articles/generate", json={
            "topic": "alpha topic",
            "knowledge_chunk_ids": [chunk_id],
        })
        self.assertEqual(response.status_code, 200)
        args = manager.run.call_args.args
        self.assertIn("Internal alpha context", args[-1])
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest backend/tests/test_article_references.py::ArticleReferencesTest::test_generate_article_passes_knowledge_context -q
```

Expected: FAIL because `knowledge_chunk_ids` is ignored.

- [ ] **Step 3: Implement knowledge context builder**

In `backend/routes/articles.py`, add:

```python
def _build_knowledge_context(knowledge_chunk_ids: list[int]) -> str:
    if not knowledge_chunk_ids:
        return ""
    from database import SessionLocal
    from models import KnowledgeChunk, KnowledgeFile

    db = SessionLocal()
    try:
        chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(knowledge_chunk_ids)).all()
        by_id = {chunk.id: chunk for chunk in chunks}
        lines = []
        for chunk_id in knowledge_chunk_ids:
            chunk = by_id.get(chunk_id)
            if not chunk:
                continue
            file = db.query(KnowledgeFile).filter(KnowledgeFile.id == chunk.file_id).first()
            source = file.original_filename if file else "knowledge"
            lines.append(f"### Knowledge: {chunk.title or source}\nSource: {source}\n{chunk.content}")
        return "\n\n".join(lines)
    finally:
        db.close()
```

In `generate_article`, read IDs and append to `context_hint`:

```python
knowledge_chunk_ids = body.get("knowledge_chunk_ids") or []
knowledge_context = _build_knowledge_context(knowledge_chunk_ids)
context_hint = "\n\n".join(part for part in [context_hint, knowledge_context] if part)
```

- [ ] **Step 4: Run generation tests**

Run:

```powershell
python -m pytest backend/tests/test_article_references.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/routes/articles.py backend/tests/test_article_references.py
git commit -m "Use knowledge chunks in article generation"
```

---

### Task 6: Topic Brief and Topic Generation Use Knowledge Chunks

**Files:**
- Modify: `backend/routes/topics.py`
- Modify: `backend/services/topic_workflow_service.py`
- Test: `backend/tests/test_topic_workflow.py` or create it if absent

- [ ] **Step 1: Write topic workflow tests**

Create `backend/tests/test_topic_workflow.py` if it does not exist:

```python
import unittest
from unittest.mock import patch

from database import Base, SessionLocal, engine
from models import KnowledgeChunk, KnowledgeFile, Topic
from services.topic_workflow_service import run_generate_brief


class TopicWorkflowKnowledgeTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_generate_brief_saves_knowledge_chunk_ids(self):
        db = SessionLocal()
        try:
            topic = Topic(title="AI risk hotspot", platform="sina", status="new")
            db.add(topic)
            file = KnowledgeFile(filename="kb.md", original_filename="kb.md", file_type="md", file_path="kb.md", status="ready", chunk_count=1)
            db.add(file)
            db.flush()
            chunk = KnowledgeChunk(file_id=file.id, chunk_index=0, title="Risk", content="Internal risk notes", content_hash="k1")
            db.add(chunk)
            db.commit()
            topic_id = topic.id
            chunk_id = chunk.id
        finally:
            db.close()

        class DummyClient:
            def label(self):
                return "dummy"
            def generate_text(self, prompt):
                self.prompt = prompt
                return type("Resp", (), {"text": '{"recommended_title":"T","title_angles":[],"audience_pain_points":[],"outline":[],"usable_materials":[],"risk_notes":[]}'})()

        dummy = DummyClient()
        with patch("services.topic_workflow_service.get_ai_client", return_value=dummy):
            run_generate_brief("task-1", topic_id, material_ids=[], reference_article_slug=None, knowledge_chunk_ids=[chunk_id])

        db = SessionLocal()
        try:
            fresh = db.query(Topic).filter(Topic.id == topic_id).one()
            self.assertEqual(fresh.knowledge_chunk_ids_json, f"[{chunk_id}]")
            self.assertIn("Internal risk notes", dummy.prompt)
        finally:
            db.close()
```

- [ ] **Step 2: Run failing topic test**

Run:

```powershell
python -m pytest backend/tests/test_topic_workflow.py -q
```

Expected: FAIL because `run_generate_brief` does not accept `knowledge_chunk_ids`.

- [ ] **Step 3: Extend topic route and service signatures**

In `backend/routes/topics.py`, read and pass IDs:

```python
knowledge_chunk_ids = body.get("knowledge_chunk_ids") or []
task_manager.run(task_id, run_generate_brief, topic_id, material_ids, reference_article_slug, knowledge_chunk_ids)
```

In `_serialize_topic`, include:

```python
"knowledge_chunk_ids": knowledge_chunk_ids,
```

In `backend/services/topic_workflow_service.py`, update:

```python
def run_generate_brief(task_id: str, topic_id: int, material_ids: list[int] | None = None, reference_article_slug: str | None = None, knowledge_chunk_ids: list[int] | None = None):
```

Normalize IDs, load chunks, include in prompt, and save:

```python
knowledge_chunk_ids = _normalize_ids(knowledge_chunk_ids)
knowledge_chunks = _load_knowledge_chunks(db, knowledge_chunk_ids)
prompt = _build_brief_prompt(topic, materials, reference_hint, knowledge_chunks)
topic.knowledge_chunk_ids_json = json.dumps(knowledge_chunk_ids)
```

Add helper:

```python
def _load_knowledge_chunks(db, chunk_ids: list[int]) -> list[dict]:
    from models import KnowledgeChunk, KnowledgeFile
    if not chunk_ids:
        return []
    records = db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(chunk_ids)).all()
    by_id = {record.id: record for record in records}
    result = []
    for chunk_id in chunk_ids:
        chunk = by_id.get(chunk_id)
        if not chunk:
            continue
        file = db.query(KnowledgeFile).filter(KnowledgeFile.id == chunk.file_id).first()
        result.append({
            "id": chunk.id,
            "title": chunk.title,
            "content": chunk.content,
            "source": file.original_filename if file else "knowledge",
        })
    return result
```

- [ ] **Step 4: Update prompt/context builders**

Update `_build_brief_prompt` and `_build_article_context_hint` to include:

```python
knowledge_text = "\n\n".join(
    f"- {item['title'] or item['source']} ({item['source']}):\n{item['content']}"
    for item in knowledge_chunks
) or "No knowledge chunks selected."
```

Add a `## Knowledge base snippets` section and say snippets are user-provided context.

- [ ] **Step 5: Run topic workflow tests**

Run:

```powershell
python -m pytest backend/tests/test_topic_workflow.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/routes/topics.py backend/services/topic_workflow_service.py backend/tests/test_topic_workflow.py
git commit -m "Use knowledge chunks in topic workflow"
```

---

### Task 7: Optional PDF Diagnostic

**Files:**
- Modify: `backend/services/environment_check_service.py`
- Test: `backend/tests/test_environment_check_service.py`

- [ ] **Step 1: Add diagnostic test**

Add to `backend/tests/test_environment_check_service.py`:

```python
def test_pdf_parser_diagnostic_is_reported(self):
    result = run_environment_check(DummyConfig)
    keys = [item["key"] for item in result["checks"]]
    self.assertIn("pdf_parser", keys)
```

- [ ] **Step 2: Run failing diagnostic test**

Run:

```powershell
python -m pytest backend/tests/test_environment_check_service.py::EnvironmentCheckServiceTest::test_pdf_parser_diagnostic_is_reported -q
```

Expected: FAIL because `pdf_parser` is not reported.

- [ ] **Step 3: Add optional diagnostic**

In `run_environment_check`, add a check equivalent to:

```python
try:
    import pypdf  # noqa: F401
    pdf_ok = True
except Exception:
    pdf_ok = False

checks.append(_status(
    pdf_ok,
    "pdf_parser",
    "PDF parser",
    "pypdf is installed; PDF knowledge uploads are available.",
    "Install pypdf to enable PDF knowledge uploads. Markdown and TXT uploads still work.",
))
```

- [ ] **Step 4: Run environment tests**

Run:

```powershell
python -m pytest backend/tests/test_environment_check_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/environment_check_service.py backend/tests/test_environment_check_service.py
git commit -m "Report optional PDF parser diagnostic"
```

---

### Task 8: Frontend Knowledge API

**Files:**
- Create: `frontend/src/api/knowledge.ts`
- Modify: `frontend/src/api/articles.ts`
- Modify: `frontend/src/api/topics.ts`

- [ ] **Step 1: Add knowledge API client**

Create `frontend/src/api/knowledge.ts`:

```ts
import client from './client'
import type { ApiResponse } from './client'
import type { Benchmark } from './benchmarks'

export interface KnowledgeFile {
  id: number
  filename: string
  original_filename: string
  file_type: string
  file_path: string
  status: 'ready' | 'processing' | 'failed'
  chunk_count: number
  error_message: string | null
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeChunk {
  id: number
  file_id: number
  chunk_index: number
  title: string | null
  content: string
  content_hash: string
  keywords: string[]
  reason?: string | null
  score?: number | null
  created_at: string | null
}

export interface KnowledgeRecommendation {
  knowledge_chunks: KnowledgeChunk[]
  fact_materials: Benchmark[]
  reference_articles: Benchmark[]
  warnings: string[]
}

export async function getKnowledgeFiles(): Promise<KnowledgeFile[]> {
  const response = await client.get<ApiResponse<KnowledgeFile[]>>('/knowledge/files')
  return response.data.data
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeFile> {
  const form = new FormData()
  form.append('file', file)
  const response = await client.post<ApiResponse<KnowledgeFile>>('/knowledge/files', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data.data
}

export async function deleteKnowledgeFile(id: number): Promise<{ deleted: boolean }> {
  const response = await client.delete<ApiResponse<{ deleted: boolean }>>(`/knowledge/files/${id}`)
  return response.data.data
}

export async function recommendKnowledge(data: {
  topic: string
  hotspot_title?: string
  knowledge_file_ids?: number[]
  limit?: number
}): Promise<KnowledgeRecommendation> {
  const response = await client.post<ApiResponse<KnowledgeRecommendation>>('/knowledge/recommend', data)
  return response.data.data
}
```

- [ ] **Step 2: Extend generate article API**

In `frontend/src/api/articles.ts`, change `generateArticle` signature:

```ts
export async function generateArticle(
  topic: string,
  benchmarkSlug?: string,
  referenceArticleSlug?: string,
  materialIds?: number[],
  knowledgeChunkIds?: number[],
): Promise<TaskResponse> {
```

Add payload field:

```ts
knowledge_chunk_ids: knowledgeChunkIds,
```

- [ ] **Step 3: Extend topic API**

In `frontend/src/api/topics.ts`, add to `Topic`:

```ts
knowledge_chunk_ids: number[]
```

Change `generateTopicBrief` data type:

```ts
data: { material_ids?: number[]; reference_article_slug?: string | null; knowledge_chunk_ids?: number[] },
```

- [ ] **Step 4: Run TypeScript check**

Run:

```powershell
npm run build
```

Expected: PASS or fail only where callers need new argument handling in later tasks.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/api/knowledge.ts frontend/src/api/articles.ts frontend/src/api/topics.ts
git commit -m "Add frontend knowledge API client"
```

---

### Task 9: Knowledge Upload UI in Material Library

**Files:**
- Modify: `frontend/src/pages/BenchmarksPage.tsx`

- [ ] **Step 1: Import knowledge APIs and Upload component**

Add imports:

```ts
import { UploadOutlined } from '@ant-design/icons'
import { Upload } from 'antd'
import { deleteKnowledgeFile, getKnowledgeFiles, uploadKnowledgeFile } from '../api/knowledge'
import type { KnowledgeFile } from '../api/knowledge'
```

- [ ] **Step 2: Add query and mutations**

Inside `BenchmarksPage`, add:

```ts
const { data: knowledgeFiles, isLoading: knowledgeLoading } = useQuery({
  queryKey: ['knowledge-files'],
  queryFn: getKnowledgeFiles,
})

const uploadKnowledgeMutation = useMutation({
  mutationFn: uploadKnowledgeFile,
  onSuccess: () => {
    messageApi.success('Knowledge file uploaded')
    queryClient.invalidateQueries({ queryKey: ['knowledge-files'] })
  },
  onError: (err: Error) => messageApi.error(err.message),
})

const deleteKnowledgeMutation = useMutation({
  mutationFn: deleteKnowledgeFile,
  onSuccess: () => {
    messageApi.success('Knowledge file deleted')
    queryClient.invalidateQueries({ queryKey: ['knowledge-files'] })
  },
  onError: (err: Error) => messageApi.error(err.message),
})
```

- [ ] **Step 3: Add knowledge columns**

Add:

```ts
const knowledgeColumns: ColumnsType<KnowledgeFile> = [
  { title: 'File', dataIndex: 'original_filename', key: 'original_filename' },
  { title: 'Type', dataIndex: 'file_type', key: 'file_type', width: 80, render: (value) => <Tag>{value}</Tag> },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 120, render: (value, record) => (
    <div>
      <Tag color={value === 'ready' ? 'success' : value === 'failed' ? 'error' : 'processing'}>{value}</Tag>
      {record.error_message && <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>{record.error_message}</Text>}
    </div>
  ) },
  { title: 'Chunks', dataIndex: 'chunk_count', key: 'chunk_count', width: 90 },
  { title: 'Action', key: 'action', width: 90, render: (_, record) => (
    <Popconfirm title="Delete this knowledge file?" onConfirm={() => deleteKnowledgeMutation.mutate(record.id)}>
      <Button danger size="small">Delete</Button>
    </Popconfirm>
  ) },
]
```

- [ ] **Step 4: Render the Knowledge Base card**

Place above the existing benchmark list:

```tsx
<div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', padding: 20, marginBottom: 16 }}>
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
    <div>
      <Text strong>Knowledge Base</Text>
      <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>Upload internal Markdown, TXT, or PDF files for AI-assisted writing.</Text>
    </div>
    <Upload
      accept=".md,.txt,.pdf"
      showUploadList={false}
      beforeUpload={(file) => {
        uploadKnowledgeMutation.mutate(file)
        return false
      }}
    >
      <Button icon={<UploadOutlined />} loading={uploadKnowledgeMutation.isPending}>Upload</Button>
    </Upload>
  </div>
  <Table<KnowledgeFile>
    dataSource={knowledgeFiles ?? []}
    columns={knowledgeColumns}
    rowKey="id"
    size="small"
    loading={knowledgeLoading}
    pagination={false}
  />
</div>
```

- [ ] **Step 5: Run frontend checks**

Run:

```powershell
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/pages/BenchmarksPage.tsx
git commit -m "Add knowledge upload UI"
```

---

### Task 10: Workshop Recommendation and Generation UI

**Files:**
- Modify: `frontend/src/pages/WorkshopPage.tsx`

- [ ] **Step 1: Add state and queries**

Import:

```ts
import { getKnowledgeFiles, recommendKnowledge } from '../api/knowledge'
import type { KnowledgeChunk } from '../api/knowledge'
import { getTopics } from '../api/topics'
```

Add state:

```ts
const [selectedKnowledgeFileIds, setSelectedKnowledgeFileIds] = useState<number[]>([])
const [selectedKnowledgeChunkIds, setSelectedKnowledgeChunkIds] = useState<number[]>([])
const [recommendedKnowledgeChunks, setRecommendedKnowledgeChunks] = useState<KnowledgeChunk[]>([])
const [selectedTopicId, setSelectedTopicId] = useState<number | undefined>()
```

Add queries:

```ts
const { data: knowledgeFiles } = useQuery({ queryKey: ['knowledge-files'], queryFn: getKnowledgeFiles })
const { data: topics } = useQuery({ queryKey: ['topics'], queryFn: () => getTopics() })
```

- [ ] **Step 2: Replace recommendation handler**

Update the existing recommendation handler to call `recommendKnowledge`:

```ts
const handleRecommend = async () => {
  if (!topic.trim()) {
    messageApi.warning('Please enter a topic first')
    return
  }
  setRecommending(true)
  try {
    const selectedTopic = topics?.find((item) => item.id === selectedTopicId)
    const result = await recommendKnowledge({
      topic: topic.trim(),
      hotspot_title: selectedTopic?.title,
      knowledge_file_ids: selectedKnowledgeFileIds.length ? selectedKnowledgeFileIds : undefined,
    })
    setRecommendedKnowledgeChunks(result.knowledge_chunks)
    setRecommendedFacts(result.fact_materials)
    setRecommendedReferences(result.reference_articles)
    setSelectedKnowledgeChunkIds(result.knowledge_chunks.slice(0, 5).map((item) => item.id))
    setSelectedMaterialIds(result.fact_materials.filter((item) => item.id != null).slice(0, 3).map((item) => item.id as number))
    setReferenceBenchmarkId(result.reference_articles.find((item) => item.id != null)?.id ?? undefined)
  } catch (e) {
    messageApi.error(`Recommendation failed: ${(e as Error).message}`)
  } finally {
    setRecommending(false)
  }
}
```

- [ ] **Step 3: Pass knowledge chunks into generation**

Update `generateArticle` call:

```ts
const { task_id } = await generateArticle(
  topic,
  undefined,
  referenceBenchmark?.file_path ? referenceBenchmark.file_path.split('/').pop()?.replace(/\.md$/, '') : undefined,
  selectedMaterialIds,
  selectedKnowledgeChunkIds,
)
```

- [ ] **Step 4: Render controls and recommendation results**

Add controls near topic input:

```tsx
<Select
  allowClear
  placeholder="Optional hotspot"
  value={selectedTopicId}
  onChange={setSelectedTopicId}
  style={{ width: '100%' }}
  options={(topics ?? []).map((item) => ({ value: item.id, label: item.title }))}
/>
<Select
  mode="multiple"
  placeholder="Optional knowledge files"
  value={selectedKnowledgeFileIds}
  onChange={setSelectedKnowledgeFileIds}
  style={{ width: '100%' }}
  options={(knowledgeFiles ?? []).filter((item) => item.status === 'ready').map((item) => ({ value: item.id, label: item.original_filename }))}
/>
```

Add a knowledge chunk selector next to existing fact/reference selectors:

```tsx
<Select
  mode="multiple"
  placeholder="Knowledge snippets"
  value={selectedKnowledgeChunkIds}
  onChange={setSelectedKnowledgeChunkIds}
  style={{ width: '100%' }}
  options={recommendedKnowledgeChunks.map((item) => ({
    value: item.id,
    label: `${item.title || `Chunk ${item.chunk_index + 1}`} - ${item.reason || 'recommended'}`,
  }))}
/>
```

- [ ] **Step 5: Run frontend checks**

Run:

```powershell
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/pages/WorkshopPage.tsx
git commit -m "Recommend knowledge in article workshop"
```

---

### Task 11: Topic Brief UI Knowledge Selection

**Files:**
- Modify: `frontend/src/pages/TopicsPage.tsx`

- [ ] **Step 1: Add imports and state**

Import:

```ts
import { getKnowledgeFiles, recommendKnowledge } from '../api/knowledge'
import type { KnowledgeChunk } from '../api/knowledge'
```

Add state:

```ts
const [selectedKnowledgeFileIds, setSelectedKnowledgeFileIds] = useState<number[]>([])
const [selectedKnowledgeChunkIds, setSelectedKnowledgeChunkIds] = useState<number[]>([])
const [recommendedKnowledgeChunks, setRecommendedKnowledgeChunks] = useState<KnowledgeChunk[]>([])
```

Add query:

```ts
const { data: knowledgeFiles } = useQuery({ queryKey: ['knowledge-files'], queryFn: getKnowledgeFiles })
```

- [ ] **Step 2: Recommend knowledge when opening brief modal**

Update `openBriefModal`:

```ts
const openBriefModal = async (topic: Topic) => {
  setBriefTopic(topic)
  setSelectedMaterialIds(topic.material_ids ?? [])
  setSelectedReferenceSlug(topic.reference_article_slug ?? null)
  setSelectedKnowledgeChunkIds(topic.knowledge_chunk_ids ?? [])
  try {
    const result = await recommendKnowledge({ topic: topic.title, hotspot_title: topic.title })
    setRecommendedKnowledgeChunks(result.knowledge_chunks)
    setSelectedKnowledgeChunkIds((topic.knowledge_chunk_ids?.length ? topic.knowledge_chunk_ids : result.knowledge_chunks.slice(0, 5).map((item) => item.id)))
  } catch {
    setRecommendedKnowledgeChunks([])
  }
}
```

- [ ] **Step 3: Submit knowledge IDs with brief**

Update `generateTopicBrief` call:

```ts
const { task_id } = await generateTopicBrief(briefTopic.id, {
  material_ids: selectedMaterialIds,
  reference_article_slug: selectedReferenceSlug,
  knowledge_chunk_ids: selectedKnowledgeChunkIds,
})
```

- [ ] **Step 4: Render selectors**

In the brief modal, add:

```tsx
<Select
  mode="multiple"
  placeholder="Limit knowledge files"
  value={selectedKnowledgeFileIds}
  onChange={setSelectedKnowledgeFileIds}
  options={(knowledgeFiles ?? []).filter((item) => item.status === 'ready').map((item) => ({
    value: item.id,
    label: item.original_filename,
  }))}
/>

<Select
  mode="multiple"
  placeholder="Knowledge snippets"
  value={selectedKnowledgeChunkIds}
  onChange={setSelectedKnowledgeChunkIds}
  options={recommendedKnowledgeChunks.map((item) => ({
    value: item.id,
    label: `${item.title || `Chunk ${item.chunk_index + 1}`} - ${item.reason || 'recommended'}`,
  }))}
/>
```

If `selectedKnowledgeFileIds` changes, call `recommendKnowledge` again with `knowledge_file_ids`.

- [ ] **Step 5: Run frontend checks**

Run:

```powershell
npm run lint
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/pages/TopicsPage.tsx frontend/src/api/topics.ts
git commit -m "Add knowledge selection to topic briefs"
```

---

### Task 12: End-to-End Verification

**Files:**
- No product files unless failures are found.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
python -m pytest backend/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend checks**

Run:

```powershell
cd frontend
npm run lint
npm run build
```

Expected: lint and build pass. Vite may warn about bundle size; that is acceptable if build exits 0.

- [ ] **Step 3: Start or reuse local services**

Run:

```powershell
try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5001/api/settings' -TimeoutSec 5).StatusCode } catch { 'backend down' }
try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/settings' -TimeoutSec 5).StatusCode } catch { 'frontend down' }
```

If either is down, start backend on 5001 and frontend on 5173 using the repo's established commands.

- [ ] **Step 4: Browser smoke with Playwright**

Use local Chrome to:

1. Open `http://127.0.0.1:5173/benchmarks`.
2. Upload a temporary `.md` file.
3. Confirm it appears in the Knowledge Base table with `ready` and chunk count > 0.
4. Open `http://127.0.0.1:5173/workshop`.
5. Enter a topic.
6. Run Smart Recommend Materials.
7. Confirm knowledge snippets and reference/fact recommendations appear.
8. Start article generation and poll task to completion.

Expected: no browser console errors, no failed requests, generated article remains `draft`.

- [ ] **Step 5: Commit fixes if needed**

If browser QA reveals bugs, fix them in focused commits named after the bug. If no code changed, do not create an empty commit.

- [ ] **Step 6: Final status**

Report:

- tests run
- browser QA result
- generated article slug if one was generated
- remaining external blockers, if any

