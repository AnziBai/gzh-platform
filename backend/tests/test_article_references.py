import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from models import Article, ArticleStat, KnowledgeChunk, KnowledgeFile
from routes.articles import articles_bp


class ArticleReferencesTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        self.app = Flask(__name__)
        self.app.register_blueprint(articles_bp, url_prefix="/api")
        self.client = self.app.test_client()

        self.session_patch = patch("routes.articles.SessionLocal", self.Session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def test_hot_references_include_only_hot_articles_with_local_files(self):
        db = self.Session()
        hot = Article(
            title="Hot Local",
            slug="hot-local",
            file_path="/tmp/hot-local.md",
            status="published",
        )
        cold = Article(
            title="Cold Local",
            slug="cold-local",
            file_path="/tmp/cold-local.md",
            status="published",
        )
        missing = Article(
            title="Hot Missing",
            slug="hot-missing",
            file_path="/tmp/hot-missing.md",
            status="published",
        )
        db.add_all([hot, cold, missing])
        db.flush()
        db.add_all(
            [
                ArticleStat(article_id=hot.id, read_count=800, fetched_at=datetime.now(timezone.utc)),
                ArticleStat(article_id=cold.id, read_count=499, fetched_at=datetime.now(timezone.utc)),
                ArticleStat(article_id=missing.id, read_count=900, fetched_at=datetime.now(timezone.utc)),
            ]
        )
        db.commit()
        db.close()

        def exists(path):
            return path == "/tmp/hot-local.md"

        with patch("os.path.exists", side_effect=exists):
            response = self.client.get("/api/articles/hot-references")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual(rows, [{"slug": "hot-local", "title": "Hot Local", "read_count": 800}])

    def test_generate_article_passes_reference_article_slug(self):
        with (
            patch("services.task_manager.task_manager.create_task", return_value="task-1"),
            patch("services.task_manager.task_manager.run") as run_task,
        ):
            response = self.client.post(
                "/api/articles/generate",
                json={"topic": "New Topic", "reference_article_slug": "hot-local"},
            )

        self.assertEqual(response.status_code, 200)
        args = run_task.call_args.args
        self.assertEqual(args[0], "task-1")
        self.assertEqual(args[2], "New Topic")
        self.assertIsNone(args[3])
        self.assertEqual(args[4], "hot-local")

    def test_generate_article_appends_selected_knowledge_chunks_to_context_hint(self):
        db = self.Session()
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
        chunk = KnowledgeChunk(
            file_id=file.id,
            chunk_index=0,
            title="Risk Control",
            content="Position sizing and drawdown rules from the internal playbook.",
            content_hash="hash-risk",
            keywords_json='["risk","control"]',
        )
        db.add(chunk)
        db.commit()
        chunk_id = chunk.id
        db.close()

        with (
            patch("services.task_manager.task_manager.create_task", return_value="task-2"),
            patch("services.task_manager.task_manager.run") as run_task,
        ):
            response = self.client.post(
                "/api/articles/generate",
                json={"topic": "Risk Topic", "knowledge_chunk_ids": [chunk_id]},
            )

        self.assertEqual(response.status_code, 200)
        context_hint = run_task.call_args.args[5]
        self.assertIn("Knowledge base snippets", context_hint)
        self.assertIn("Position sizing and drawdown rules", context_hint)
        self.assertIn("Source: alpha.md", context_hint)

    def test_generate_article_limits_and_deduplicates_knowledge_chunks(self):
        db = self.Session()
        file = KnowledgeFile(
            filename="limits.md",
            original_filename="limits.md",
            file_type="md",
            file_path="limits.md",
            status="ready",
            chunk_count=7,
        )
        db.add(file)
        db.flush()
        chunks = []
        for index in range(7):
            chunk = KnowledgeChunk(
                file_id=file.id,
                chunk_index=index,
                title=f"Limit Chunk {index}",
                content=f"Unique content {index}",
                content_hash=f"hash-limit-{index}",
                keywords_json="[]",
            )
            chunks.append(chunk)
        db.add_all(chunks)
        db.commit()
        chunk_ids = [chunk.id for chunk in chunks]
        db.close()

        with (
            patch("services.task_manager.task_manager.create_task", return_value="task-4"),
            patch("services.task_manager.task_manager.run") as run_task,
        ):
            response = self.client.post(
                "/api/articles/generate",
                json={
                    "topic": "Limit Topic",
                    "knowledge_chunk_ids": [
                        chunk_ids[0],
                        chunk_ids[1],
                        chunk_ids[1],
                        chunk_ids[2],
                        chunk_ids[3],
                        chunk_ids[4],
                        chunk_ids[5],
                        chunk_ids[6],
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        context_hint = run_task.call_args.args[5]
        self.assertEqual(context_hint.count("### Limit Chunk"), 5)
        self.assertEqual(context_hint.count("Unique content 1"), 1)
        self.assertIn("Unique content 4", context_hint)
        self.assertNotIn("Unique content 5", context_hint)
        self.assertNotIn("Unique content 6", context_hint)

    def test_generate_article_ignores_invalid_knowledge_chunk_ids(self):
        with (
            patch("services.task_manager.task_manager.create_task", return_value="task-3"),
            patch("services.task_manager.task_manager.run") as run_task,
        ):
            response = self.client.post(
                "/api/articles/generate",
                json={"topic": "Risk Topic", "knowledge_chunk_ids": "not-a-list"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_task.call_args.args[5], "")


if __name__ == "__main__":
    unittest.main()
