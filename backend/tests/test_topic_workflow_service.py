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
from models import Article, Benchmark, Topic
from services.topic_workflow_service import run_generate_brief, run_generate_from_topic


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def label(self):
        return "fake"

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.text, duration_ms=None, cost_usd=None)


class TopicWorkflowServiceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        self.session_patch = patch("services.topic_workflow_service.SessionLocal", self.Session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def test_generate_brief_saves_json_and_selected_materials(self):
        db = self.Session()
        topic = Topic(title="热点标题", platform="toutiao", hot_value=1000)
        material = Benchmark(
            title="事实材料",
            platform="manual",
            file_path=None,
            material_type="fact_material",
        )
        db.add_all([topic, material])
        db.commit()
        topic_id = topic.id
        material_id = material.id
        db.close()

        client = FakeClient(json.dumps({"recommended_title": "推荐标题", "outline": ["一", "二"]}, ensure_ascii=False))
        with patch("services.topic_workflow_service.get_ai_client", return_value=client):
            result = run_generate_brief("task-1", topic_id, [material_id], "hot-ref")

        db = self.Session()
        saved = db.query(Topic).filter(Topic.id == topic_id).first()
        self.assertEqual(saved.status, "selected")
        self.assertEqual(json.loads(saved.brief_json)["recommended_title"], "推荐标题")
        self.assertEqual(json.loads(saved.material_ids_json), [material_id])
        self.assertEqual(saved.reference_article_slug, "hot-ref")
        self.assertEqual(result["brief"]["outline"], ["一", "二"])
        self.assertIn("事实材料", client.prompts[0])
        db.close()

    def test_generate_from_topic_marks_used_and_links_article(self):
        db = self.Session()
        topic = Topic(
            title="热点标题",
            platform="toutiao",
            brief_json=json.dumps({"recommended_title": "推荐标题"}, ensure_ascii=False),
            material_ids_json="[]",
            reference_article_slug="hot-ref",
            status="selected",
        )
        db.add(topic)
        db.commit()
        topic_id = topic.id
        db.close()

        with (
            patch(
                "services.topic_workflow_service.run_generate",
                return_value={"file_path": "C:/articles/generated.md", "slug": "generated"},
            ) as run_generate,
            patch(
                "services.topic_workflow_service.parse_frontmatter",
                return_value={"frontmatter": {"title": "生成文章"}, "content": "正文"},
            ),
        ):
            result = run_generate_from_topic("task-2", topic_id)

        run_generate.assert_called_once()
        db = self.Session()
        saved = db.query(Topic).filter(Topic.id == topic_id).first()
        article = db.query(Article).filter(Article.slug == "generated").first()
        self.assertEqual(saved.status, "used")
        self.assertEqual(saved.generated_article_id, article.id)
        self.assertEqual(result["article_id"], article.id)
        db.close()


if __name__ == "__main__":
    unittest.main()
