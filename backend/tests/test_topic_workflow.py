import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from models import KnowledgeChunk, KnowledgeFile, Topic
from services.topic_workflow_service import run_generate_brief, run_generate_from_topic


class DummyBriefClient:
    def __init__(self):
        self.prompts = []

    def label(self):
        return "dummy"

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(
            text=json.dumps(
                {
                    "recommended_title": "Knowledge assisted title",
                    "title_angles": ["angle"],
                    "audience_pain_points": ["pain"],
                    "outline": ["intro", "body"],
                    "usable_materials": ["knowledge"],
                    "risk_notes": ["verify claims"],
                }
            ),
            duration_ms=None,
            cost_usd=None,
        )


class TopicWorkflowKnowledgeTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.session_patch = patch("services.topic_workflow_service.SessionLocal", self.Session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def _create_topic_with_chunk(self):
        db = self.Session()
        topic = Topic(title="Hot topic", platform="toutiao", hot_value=88)
        file = KnowledgeFile(
            filename="policy.md",
            original_filename="Policy Notes.md",
            file_type="md",
            file_path="C:/knowledge/policy.md",
            status="ready",
            chunk_count=1,
        )
        db.add_all([topic, file])
        db.flush()
        chunk = KnowledgeChunk(
            file_id=file.id,
            chunk_index=0,
            title="Policy Section",
            content="Knowledge chunk content for topic workflow.",
            content_hash="chunk-hash",
        )
        db.add(chunk)
        db.commit()
        topic_id = topic.id
        chunk_id = chunk.id
        db.close()
        return topic_id, chunk_id

    def test_generate_brief_saves_and_includes_knowledge_chunks(self):
        topic_id, chunk_id = self._create_topic_with_chunk()
        client = DummyBriefClient()

        with patch("services.topic_workflow_service.get_ai_client", return_value=client):
            run_generate_brief("task-brief", topic_id, knowledge_chunk_ids=[chunk_id])

        db = self.Session()
        saved = db.query(Topic).filter(Topic.id == topic_id).first()
        self.assertEqual(saved.knowledge_chunk_ids_json, f"[{chunk_id}]")
        db.close()
        self.assertIn("Knowledge base snippets", client.prompts[0])
        self.assertIn("Knowledge chunk content for topic workflow.", client.prompts[0])

    def test_generate_from_topic_includes_saved_knowledge_chunks_in_context(self):
        topic_id, chunk_id = self._create_topic_with_chunk()
        db = self.Session()
        topic = db.query(Topic).filter(Topic.id == topic_id).first()
        topic.brief_json = json.dumps({"recommended_title": "Generated from brief"})
        topic.material_ids_json = "[]"
        topic.knowledge_chunk_ids_json = f"[{chunk_id}]"
        topic.status = "selected"
        db.commit()
        db.close()

        captured = {}

        def fake_run_generate(task_id, topic, benchmark_slug=None, reference_article_slug=None, context_hint=None):
            captured["context_hint"] = context_hint
            return {"file_path": "C:/articles/generated.md", "slug": "generated"}

        with (
            patch("services.topic_workflow_service.run_generate", side_effect=fake_run_generate),
            patch(
                "services.topic_workflow_service.parse_frontmatter",
                return_value={"frontmatter": {"title": "Generated Article"}, "content": "Article body"},
            ),
        ):
            run_generate_from_topic("task-generate", topic_id)

        self.assertIn("Knowledge base snippets", captured["context_hint"])
        self.assertIn("Knowledge chunk content for topic workflow.", captured["context_hint"])
        self.assertIn("user-provided context", captured["context_hint"])


if __name__ == "__main__":
    unittest.main()
