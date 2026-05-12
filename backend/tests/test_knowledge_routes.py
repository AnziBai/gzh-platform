import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from routes.knowledge import knowledge_bp


class KnowledgeRoutesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.tmp = tempfile.TemporaryDirectory()

        self.app = Flask(__name__)
        self.app.register_blueprint(knowledge_bp, url_prefix="/api")
        self.client = self.app.test_client()

        self.route_session_patch = patch("routes.knowledge.SessionLocal", self.Session)
        self.root_patch = patch("routes.knowledge.Config.GZHPUBLISHER_ROOT", self.tmp.name)
        self.route_session_patch.start()
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.route_session_patch.stop()
        self.tmp.cleanup()
        self.engine.dispose()

    def test_upload_markdown_then_list_then_delete(self):
        upload = self.client.post(
            "/api/knowledge/files",
            data={"file": (io.BytesIO(b"# Alpha\n\nUseful knowledge " * 20), "alpha.md")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200)
        created = upload.get_json()["data"]
        self.assertEqual(created["original_filename"], "alpha.md")
        self.assertEqual(created["status"], "ready")
        self.assertTrue(Path(created["file_path"]).exists())

        listing = self.client.get("/api/knowledge/files")
        self.assertEqual(listing.status_code, 200)
        rows = listing.get_json()["data"]
        self.assertEqual([row["id"] for row in rows], [created["id"]])

        deleted = self.client.delete(f"/api/knowledge/files/{created['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json()["data"], {"deleted": True})
        self.assertFalse(Path(created["file_path"]).exists())

    def test_unsupported_extension_returns_400(self):
        response = self.client.post(
            "/api/knowledge/files",
            data={"file": (io.BytesIO(b"not supported"), "alpha.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], -1)

    def test_recommend_requires_topic(self):
        response = self.client.post("/api/knowledge/recommend", json={"topic": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], -1)

    def test_recommend_with_topic_returns_stub_shape(self):
        response = self.client.post(
            "/api/knowledge/recommend",
            json={"topic": "AI search", "hotspot_title": "Hot", "knowledge_file_ids": [1], "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["data"],
            {"knowledge_chunks": [], "fact_materials": [], "reference_articles": [], "warnings": []},
        )


if __name__ == "__main__":
    unittest.main()
