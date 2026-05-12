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
from models import MaterialCandidate
from routes.materials import materials_bp
from routes.settings import settings_bp
from services.material_collection_service import approve_candidate, upsert_candidate


class MaterialsUpgradeTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        self.app = Flask(__name__)
        self.app.register_blueprint(materials_bp, url_prefix="/api")
        self.app.register_blueprint(settings_bp, url_prefix="/api")
        self.client = self.app.test_client()

        self.route_session_patch = patch("routes.materials.SessionLocal", self.Session)
        self.service_session_patch = patch("services.material_collection_service.SessionLocal", self.Session)
        self.route_session_patch.start()
        self.service_session_patch.start()

    def tearDown(self):
        self.route_session_patch.stop()
        self.service_session_patch.stop()

    def test_candidate_approval_writes_benchmark_and_deduplicates(self):
        db = self.Session()
        candidate = upsert_candidate(
            db,
            title="AI search result",
            content="source-backed material",
            source_url="https://example.com/a",
            platform="search",
            suggested_material_type="fact_material",
            confidence=0.9,
            classification_reason="source-backed fact",
            source_kind="search_result",
        )
        db.commit()
        candidate_id = candidate.id
        db.close()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("config.Config.BENCHMARKS_DIR", tmp):
                first = approve_candidate(candidate_id)
                second = approve_candidate(candidate_id)

            self.assertFalse(first["deduplicated"])
            self.assertTrue(second["deduplicated"])
            self.assertEqual(len(list(Path(tmp).glob("*.md"))), 1)

    def test_candidates_endpoint_filters_status(self):
        db = self.Session()
        db.add(
            MaterialCandidate(
                title="candidate",
                content="body",
                source_url="https://example.com",
                platform="search",
                suggested_material_type="fact_material",
                status="candidate",
                source_kind="search_result",
                source_hash="hash-1",
            )
        )
        db.add(
            MaterialCandidate(
                title="rejected",
                content="body",
                source_url="https://example.com/2",
                platform="search",
                suggested_material_type="reference_article",
                status="rejected",
                source_kind="search_result",
                source_hash="hash-2",
            )
        )
        db.commit()
        db.close()

        response = self.client.get("/api/materials/candidates?status=candidate")
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual([row["title"] for row in rows], ["candidate"])

    def test_model_presets_shape_matches_frontend(self):
        response = self.client.get("/api/settings/model-presets")
        self.assertEqual(response.status_code, 200)
        first = response.get_json()["data"][0]
        self.assertIn("name", first)
        self.assertIn("provider", first)
        self.assertIn("base_url", first)
        self.assertIn("recommended_models", first)


if __name__ == "__main__":
    unittest.main()
