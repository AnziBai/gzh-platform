import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from models import Benchmark, KnowledgeChunk, KnowledgeFile
from services.knowledge_service import (
    UnsupportedKnowledgeFile,
    KnowledgeParseError,
    chunk_text,
    delete_file,
    extract_keywords,
    parse_uploaded_text,
    recommend_for_topic,
    save_uploaded_file,
)


class KnowledgeServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()
        self.engine.dispose()

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

    def test_chunk_text_updates_title_after_new_markdown_heading(self):
        chunks = chunk_text(
            "# First\n\n" + ("alpha " * 40) + "\n\n# Second\n\n" + ("beta " * 40),
            target_size=80,
        )
        self.assertIn("Second", [item["title"] for item in chunks[1:]])

    def test_extract_keywords_returns_unique_terms(self):
        keywords = extract_keywords("alpha beta alpha gamma")
        self.assertEqual(keywords[:3], ["alpha", "beta", "gamma"])

    def test_extract_keywords_expands_chinese_bigrams(self):
        keywords = extract_keywords("风险控制回撤")
        self.assertIn("风险控制回撤", keywords)
        self.assertIn("风险", keywords)
        self.assertIn("险控", keywords)
        self.assertIn("控制", keywords)
        self.assertIn("制回", keywords)
        self.assertIn("回撤", keywords)

    def test_extract_keywords_default_returns_more_than_twenty_terms(self):
        text = " ".join(f"term{i:02d}" for i in range(25))
        keywords = extract_keywords(text)
        self.assertEqual(len(keywords), 25)
        self.assertEqual(keywords[-1], "term24")

    def test_save_uploaded_file_creates_file_and_chunks(self):
        db = self.Session()
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

    def test_failed_save_records_error_status(self):
        db = self.Session()
        try:
            with self.assertRaises(UnsupportedKnowledgeFile):
                save_uploaded_file(
                    db,
                    upload_dir=self.tmp.name,
                    original_filename="sheet.xlsx",
                    content=b"data",
                )
            record = db.query(KnowledgeFile).one()
            self.assertEqual(record.status, "failed")
            self.assertIn("Unsupported knowledge file type", record.error_message)
        finally:
            db.close()

    def test_empty_parsed_text_records_failed_status(self):
        db = self.Session()
        try:
            with self.assertRaises(KnowledgeParseError) as ctx:
                save_uploaded_file(
                    db,
                    upload_dir=self.tmp.name,
                    original_filename="empty.txt",
                    content=b"   \n\n",
                )
            self.assertEqual(str(ctx.exception), "No usable text was parsed")

            record = db.query(KnowledgeFile).one()
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.error_message, "No usable text was parsed")
            self.assertEqual(record.chunk_count, 0)
            if record.file_path:
                self.assertFalse(Path(record.file_path).exists())
        finally:
            db.close()

    def test_failed_chunking_removes_written_upload_file(self):
        db = self.Session()
        try:
            with patch("services.knowledge_service.chunk_text", side_effect=RuntimeError("chunk boom")):
                with self.assertRaises(KnowledgeParseError):
                    save_uploaded_file(
                        db,
                        upload_dir=self.tmp.name,
                        original_filename="kb.md",
                        content=b"# KB\n\nalpha beta gamma",
                    )
            record = db.query(KnowledgeFile).one()
            self.assertEqual(record.status, "failed")
            self.assertFalse(Path(record.file_path).exists())
        finally:
            db.close()

    def test_delete_file_does_not_unlink_outside_upload_root(self):
        db = self.Session()
        sentinel = Path(self.tmp.name) / "sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        upload_root = Path(self.tmp.name) / "knowledge"
        upload_root.mkdir()
        try:
            record = KnowledgeFile(
                filename="sentinel.txt",
                original_filename="sentinel.txt",
                file_type="txt",
                file_path=str(sentinel),
                status="ready",
                chunk_count=0,
            )
            db.add(record)
            db.commit()
            file_id = record.id

            self.assertTrue(delete_file(db, file_id, upload_root=str(upload_root)))
            self.assertIsNone(db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first())
            self.assertTrue(sentinel.exists())
        finally:
            db.close()

    def test_recommend_for_topic_returns_ranked_chunks_and_materials(self):
        db = self.Session()
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
            db.add(
                KnowledgeChunk(
                    file_id=file.id,
                    chunk_index=0,
                    title="Risk Control",
                    content="Risk control position sizing drawdown alpha",
                    content_hash="hash-a",
                    keywords_json='["risk","control","drawdown"]',
                )
            )
            db.add(
                Benchmark(
                    title="Risk Case",
                    platform="manual",
                    material_type="fact_material",
                    source_url="https://example.com/risk",
                    file_path=None,
                    relevance_score=0.5,
                )
            )
            db.add(
                Benchmark(
                    title="Risk Trading Article",
                    platform="manual",
                    material_type="reference_article",
                    source_url="https://example.com/ref",
                    file_path=None,
                    relevance_score=0.8,
                )
            )
            db.commit()

            result = recommend_for_topic(db, topic="risk control drawdown", config=None)

            self.assertEqual(result["knowledge_chunks"][0]["title"], "Risk Control")
            self.assertEqual(result["fact_materials"][0]["title"], "Risk Case")
            self.assertEqual(result["reference_articles"][0]["title"], "Risk Trading Article")
            self.assertEqual(result["warnings"], [])
        finally:
            db.close()

    def test_recommend_for_topic_scopes_chunks_to_requested_file_ids(self):
        db = self.Session()
        try:
            file1 = KnowledgeFile(
                filename="alpha.md",
                original_filename="alpha.md",
                file_type="md",
                file_path="alpha.md",
                status="ready",
                chunk_count=1,
            )
            file2 = KnowledgeFile(
                filename="beta.md",
                original_filename="beta.md",
                file_type="md",
                file_path="beta.md",
                status="ready",
                chunk_count=1,
            )
            db.add_all([file1, file2])
            db.flush()
            db.add_all(
                [
                    KnowledgeChunk(
                        file_id=file1.id,
                        chunk_index=0,
                        title="Excluded Risk",
                        content="risk control drawdown",
                        content_hash="hash-a",
                        keywords_json='["risk","control","drawdown"]',
                    ),
                    KnowledgeChunk(
                        file_id=file2.id,
                        chunk_index=0,
                        title="Included Risk",
                        content="risk control drawdown",
                        content_hash="hash-b",
                        keywords_json='["risk","control","drawdown"]',
                    ),
                ]
            )
            db.commit()

            result = recommend_for_topic(db, topic="risk control", knowledge_file_ids=[file2.id])

            self.assertEqual([item["title"] for item in result["knowledge_chunks"]], ["Included Risk"])
        finally:
            db.close()

    def test_recommend_for_topic_empty_file_ids_returns_no_chunks(self):
        db = self.Session()
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
            db.add(
                KnowledgeChunk(
                    file_id=file.id,
                    chunk_index=0,
                    title="Risk Control",
                    content="risk control drawdown",
                    content_hash="hash-a",
                    keywords_json='["risk","control","drawdown"]',
                )
            )
            db.commit()

            result = recommend_for_topic(db, topic="risk control", knowledge_file_ids=[])

            self.assertEqual(result["knowledge_chunks"], [])
        finally:
            db.close()

    def test_recommend_for_topic_chinese_bigram_match(self):
        db = self.Session()
        try:
            file = KnowledgeFile(
                filename="risk.md",
                original_filename="risk.md",
                file_type="md",
                file_path="risk.md",
                status="ready",
                chunk_count=1,
            )
            db.add(file)
            db.flush()
            db.add(
                KnowledgeChunk(
                    file_id=file.id,
                    chunk_index=0,
                    title="策略风控",
                    content="风险控制是降低回撤的核心",
                    content_hash="hash-cn",
                    keywords_json='["风险控制是降低回撤的核心"]',
                )
            )
            db.commit()

            result = recommend_for_topic(db, topic="风险控制回撤")

            self.assertEqual(result["knowledge_chunks"][0]["title"], "策略风控")
        finally:
            db.close()

    def test_recommend_for_topic_excludes_positive_relevance_without_token_match(self):
        db = self.Session()
        try:
            db.add_all(
                [
                    Benchmark(
                        title="Unrelated Viral Article",
                        platform="manual",
                        material_type="reference_article",
                        source_url="https://example.com/viral",
                        relevance_score=10,
                    ),
                    Benchmark(
                        title="Risk Matched Article",
                        platform="manual",
                        material_type="reference_article",
                        source_url="https://example.com/risk",
                        relevance_score=0.1,
                    ),
                ]
            )
            db.commit()

            result = recommend_for_topic(db, topic="risk control")

            self.assertEqual([item["title"] for item in result["reference_articles"]], ["Risk Matched Article"])
        finally:
            db.close()

    def test_recommend_for_topic_empty_matches_returns_empty_arrays_and_warnings(self):
        db = self.Session()
        try:
            db.add(
                Benchmark(
                    title="Unrelated",
                    platform="manual",
                    material_type="fact_material",
                    source_url="https://example.com/other",
                    relevance_score=0,
                )
            )
            db.commit()

            result = recommend_for_topic(db, topic="risk control")

            self.assertEqual(result["knowledge_chunks"], [])
            self.assertEqual(result["fact_materials"], [])
            self.assertEqual(result["reference_articles"], [])
            self.assertIsInstance(result["warnings"], list)
        finally:
            db.close()
