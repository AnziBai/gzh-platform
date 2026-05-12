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
from models import KnowledgeFile
from services.knowledge_service import (
    UnsupportedKnowledgeFile,
    KnowledgeParseError,
    chunk_text,
    extract_keywords,
    parse_uploaded_text,
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
