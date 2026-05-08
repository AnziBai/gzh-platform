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

    def test_articles_endpoint_marks_hot_articles(self):
        db = self.Session()
        article = Article(
            title="Hot Article",
            slug="hot-article",
            file_path="/tmp/hot-article.md",
            status="published",
        )
        db.add(article)
        db.flush()
        db.add(
            ArticleStat(
                article_id=article.id,
                read_count=501,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.close()

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
        ):
            response = self.client.get("/api/analytics/articles")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual(rows[0]["slug"], "hot-article")
        self.assertTrue(rows[0]["is_hot"])

    def test_articles_endpoint_non_hot_at_threshold(self):
        db = self.Session()
        article = Article(
            title="Normal Article",
            slug="normal-article",
            file_path="/tmp/normal-article.md",
            status="published",
        )
        db.add(article)
        db.flush()
        db.add(
            ArticleStat(
                article_id=article.id,
                read_count=500,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.close()

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
        ):
            response = self.client.get("/api/analytics/articles")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertFalse(rows[0]["is_hot"])

    def test_insights_include_db_only_articles(self):
        db = self.Session()
        article = Article(
            title="Imported Article",
            slug="imported-article",
            file_path="C:/old-machine/imported-article.md",
            status="published",
            structure_type="case-study",
            word_count=2600,
        )
        db.add(article)
        db.flush()
        article_id = article.id
        db.add(
            ArticleStat(
                article_id=article_id,
                read_count=420,
                share_count=12,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.close()

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
        ):
            response = self.client.get("/api/analytics/insights?dimension=structure_type")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual(rows, [{"label": "case-study", "avg_reads": 420, "count": 1}])

    def test_fetch_stats_replaces_stale_higher_stat_with_wechat_value(self):
        db = self.Session()
        article = Article(
            title="Accurate Article",
            slug="accurate-article",
            file_path="/tmp/accurate-article.md",
            status="published",
        )
        db.add(article)
        db.flush()
        article_id = article.id
        db.add(
            ArticleStat(
                article_id=article_id,
                read_count=9999,
                share_count=999,
                like_count=99,
                comment_count=9,
                fetched_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        db.commit()
        db.close()

        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch(
                "services.wechat_service.get_published_articles",
                return_value={"Accurate Article": {"update_time": None}},
            ),
            patch(
                "services.wechat_service.fetch_real_stats",
                return_value={
                    "Accurate Article": {
                        "int_page_read_count": 321,
                        "share_count": 7,
                        "add_to_fav_count": 3,
                        "ori_page_read_count": 1,
                    }
                },
            ),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)

        db = self.Session()
        stat = db.query(ArticleStat).filter(ArticleStat.article_id == article_id).one()
        self.assertEqual(stat.read_count, 321)
        self.assertEqual(stat.share_count, 7)
        self.assertEqual(stat.like_count, 3)
        self.assertEqual(stat.comment_count, 1)
        db.close()

    def test_fetch_stats_requires_wechat_credentials(self):
        with (
            patch("config.Config.WECHAT_APP_ID", ""),
            patch("config.Config.WECHAT_APP_SECRET", ""),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["status"], -1)
        self.assertIn("WECHAT_APP_ID", data["message"])


if __name__ == "__main__":
    unittest.main()
