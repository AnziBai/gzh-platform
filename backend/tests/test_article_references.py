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
from models import Article, ArticleStat
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


if __name__ == "__main__":
    unittest.main()
