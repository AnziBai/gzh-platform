import tempfile
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base, SessionLocal, engine
from models import KnowledgeFile
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

    def test_failed_save_records_error_status(self):
        db = SessionLocal()
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
