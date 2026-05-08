import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from models import Article, ArticleStat
from routes.analytics import analytics_bp


class AnalyticsRoutesTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

        self.app = Flask(__name__)
        self.app.register_blueprint(analytics_bp, url_prefix="/api")
        self.client = self.app.test_client()

        self.session_patch = patch("routes.analytics.SessionLocal", self.Session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def test_overview_totals_use_latest_stat_per_article(self):
        db = self.Session()
        article = Article(
            title="Published Article",
            slug="published-article",
            file_path="/tmp/published.md",
            status="published",
            structure_type="case-study",
        )
        db.add(article)
        db.flush()

        now = datetime.now(timezone.utc)
        db.add_all(
            [
                ArticleStat(
                    article_id=article.id,
                    read_count=100,
                    share_count=10,
                    fetched_at=now - timedelta(days=1),
                ),
                ArticleStat(
                    article_id=article.id,
                    read_count=150,
                    share_count=12,
                    fetched_at=now,
                ),
            ]
        )
        db.commit()
        db.close()

        response = self.client.get("/api/analytics/overview")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total_reads"], 150)
        self.assertEqual(data["total_shares"], 12)
        self.assertEqual(data["avg_read_per_article"], 150.0)

    def test_articles_endpoint_does_not_duplicate_tracked_article_without_stats(self):
        db = self.Session()
        db.add(
            Article(
                title="Tracked Draft",
                slug="tracked-draft",
                file_path="/tmp/tracked-draft.md",
                status="draft",
            )
        )
        db.commit()
        db.close()

        fs_articles = [
            {
                "file_path": "/tmp/tracked-draft.md",
                "title": "Tracked Draft",
                "slug": "tracked-draft",
                "frontmatter": {},
                "word_count": 1200,
            }
        ]

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp"),
            patch("services.article_service.scan_articles_dir", return_value=fs_articles),
        ):
            response = self.client.get("/api/analytics/articles")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "tracked-draft")
        self.assertEqual(rows[0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
