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
from models import Article, ArticleStat, SyncStatus
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
                    like_count=5,
                    recommend_count=3,
                    underline_count=2,
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

    def test_overview_totals_ignore_draft_stats(self):
        db = self.Session()
        published = Article(
            title="Published Article",
            slug="published-article",
            file_path="/tmp/published.md",
            status="published",
            structure_type="case-study",
        )
        draft = Article(
            title="Draft Article",
            slug="draft-article",
            file_path="/tmp/draft.md",
            status="draft",
            structure_type="case-study",
        )
        db.add_all([published, draft])
        db.flush()
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                ArticleStat(
                    article_id=published.id,
                    read_count=100,
                    share_count=10,
                    fetched_at=now,
                ),
                ArticleStat(
                    article_id=draft.id,
                    read_count=900,
                    share_count=90,
                    fetched_at=now,
                ),
            ]
        )
        db.commit()
        db.close()

        response = self.client.get("/api/analytics/overview")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total_reads"], 100)
        self.assertEqual(data["total_shares"], 10)
        self.assertEqual(data["avg_read_per_article"], 100.0)
        self.assertEqual(data["top_structure_types"], [
            {"structure_type": "case-study", "count": 1, "avg_reads": 100.0}
        ])

    def test_overview_groups_missing_structure_as_uncategorized(self):
        db = self.Session()
        article = Article(
            title="Uncategorized Article",
            slug="uncategorized-article",
            file_path="/tmp/uncategorized.md",
            status="published",
            structure_type=None,
        )
        db.add(article)
        db.flush()
        db.add(
            ArticleStat(
                article_id=article.id,
                read_count=80,
                fetched_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        db.close()

        response = self.client.get("/api/analytics/overview")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["top_structure_types"], [
            {"structure_type": "未分类", "count": 1, "avg_reads": 80.0}
        ])

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
            response = self.client.get("/api/analytics/articles?status=all")

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
                share_count=4,
                like_count=3,
                recommend_count=2,
                underline_count=1,
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
        self.assertEqual(rows[0]["latest_share_count"], 4)
        self.assertEqual(rows[0]["latest_like_count"], 3)
        self.assertEqual(rows[0]["latest_recommend_count"], 2)
        self.assertEqual(rows[0]["latest_underline_count"], 1)

    def test_articles_endpoint_defaults_to_published_articles_only(self):
        db = self.Session()
        published = Article(
            title="Published Article",
            slug="published-article",
            file_path="/tmp/published.md",
            status="published",
        )
        draft = Article(
            title="Draft Article",
            slug="draft-article",
            file_path="/tmp/draft.md",
            status="draft",
        )
        db.add_all([published, draft])
        db.flush()
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                ArticleStat(article_id=published.id, read_count=100, fetched_at=now),
                ArticleStat(article_id=draft.id, read_count=900, fetched_at=now),
            ]
        )
        db.commit()
        db.close()

        fs_articles = [
            {
                "file_path": "/tmp/published.md",
                "title": "Published Article",
                "slug": "published-article",
                "frontmatter": {},
                "word_count": 1200,
            },
            {
                "file_path": "/tmp/draft.md",
                "title": "Draft Article",
                "slug": "draft-article",
                "frontmatter": {},
                "word_count": 900,
            },
        ]

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp"),
            patch("services.article_service.scan_articles_dir", return_value=fs_articles),
        ):
            response = self.client.get("/api/analytics/articles")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual([row["slug"] for row in rows], ["published-article"])

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

    def test_insights_ignore_draft_articles(self):
        db = self.Session()
        published = Article(
            title="Published Article",
            slug="published-article",
            file_path="/tmp/published.md",
            status="published",
            structure_type="case-study",
            word_count=2600,
        )
        draft = Article(
            title="Draft Article",
            slug="draft-article",
            file_path="/tmp/draft.md",
            status="draft",
            structure_type="case-study",
            word_count=2600,
        )
        db.add_all([published, draft])
        db.flush()
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                ArticleStat(article_id=published.id, read_count=100, fetched_at=now),
                ArticleStat(article_id=draft.id, read_count=900, fetched_at=now),
            ]
        )
        db.commit()
        db.close()

        fs_articles = [
            {
                "file_path": "/tmp/published.md",
                "title": "Published Article",
                "slug": "published-article",
                "frontmatter": {"structure_type": "case-study"},
                "word_count": 2600,
            },
            {
                "file_path": "/tmp/draft.md",
                "title": "Draft Article",
                "slug": "draft-article",
                "frontmatter": {"structure_type": "case-study"},
                "word_count": 2600,
            },
        ]

        with (
            patch("config.Config.ARTICLES_DIR", "/tmp"),
            patch("services.article_service.scan_articles_dir", return_value=fs_articles),
        ):
            response = self.client.get("/api/analytics/insights?dimension=structure_type")

        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["data"]
        self.assertEqual(rows, [{"label": "case-study", "avg_reads": 100, "count": 1}])

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
                    recommend_count=8,
                    underline_count=7,
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
                        "like_count": 3,
                        "recommend_count": 2,
                        "comment_count": 1,
                        "underline_count": 4,
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
        self.assertEqual(stat.recommend_count, 2)
        self.assertEqual(stat.underline_count, 4)
        db.close()

    def test_fetch_stats_updates_articles_with_duplicate_file_paths(self):
        db = self.Session()
        first = Article(
            title="First Duplicate Path",
            slug="first-duplicate-path",
            file_path="/tmp/shared.md",
            status="draft",
        )
        second = Article(
            title="Second Duplicate Path",
            slug="second-duplicate-path",
            file_path="/tmp/shared.md",
            status="draft",
        )
        db.add_all([first, second])
        db.commit()
        db.close()

        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch(
                "services.wechat_service.get_published_articles",
                return_value={
                    "First Duplicate Path": {"update_time": None},
                    "Second Duplicate Path": {"update_time": None},
                },
            ),
            patch(
                "services.wechat_service.fetch_real_stats",
                return_value={
                    "First Duplicate Path": {
                        "int_page_read_count": 11,
                        "share_count": 1,
                        "add_to_fav_count": 0,
                        "ori_page_read_count": 0,
                    },
                    "Second Duplicate Path": {
                        "int_page_read_count": 22,
                        "share_count": 2,
                        "add_to_fav_count": 0,
                        "ori_page_read_count": 0,
                    },
                },
            ),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)
        db = self.Session()
        stats = {
            article.title: article.stats[0].read_count
            for article in db.query(Article).all()
        }
        self.assertEqual(stats["First Duplicate Path"], 11)
        self.assertEqual(stats["Second Duplicate Path"], 22)
        db.close()

    def test_fetch_stats_does_not_demote_unmatched_published_articles(self):
        db = self.Session()
        article = Article(
            title="Published But Unmatched",
            slug="published-but-unmatched",
            file_path="/tmp/published-but-unmatched.md",
            status="published",
        )
        db.add(article)
        db.commit()
        db.close()

        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch(
                "services.wechat_service.get_published_articles",
                return_value={"Other Published": {"update_time": None}},
            ),
            patch("services.wechat_service.fetch_real_stats", return_value={}),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)
        db = self.Session()
        status = db.query(Article).filter(Article.slug == "published-but-unmatched").one().status
        self.assertEqual(status, "published")
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

    def test_fetch_stats_uses_configured_history_window(self):
        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.WECHAT_STATS_DAYS_BACK", 365),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch("services.wechat_service.get_published_articles", return_value={}),
            patch("services.wechat_service.fetch_real_stats", return_value={}) as fetch_real_stats,
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)
        fetch_real_stats.assert_called_once_with(days_back=365)

    def test_sync_status_endpoint_returns_latest_sync_state(self):
        db = self.Session()
        db.add(
            SyncStatus(
                id=1,
                status="success",
                message="updated 2 articles",
                result_json='{"updated": 2}',
            )
        )
        db.commit()
        db.close()

        response = self.client.get("/api/analytics/sync-status")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "updated 2 articles")
        self.assertEqual(data["result"]["updated"], 2)

    def test_fetch_stats_records_successful_sync_status(self):
        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.WECHAT_STATS_DAYS_BACK", 365),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch("services.wechat_service.get_published_articles", return_value={}),
            patch("services.wechat_service.fetch_real_stats", return_value={}),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)
        db = self.Session()
        status = db.query(SyncStatus).filter_by(id=1).one()
        self.assertEqual(status.status, "success")
        self.assertIn("更新 0 篇", status.message)
        self.assertIn('"updated": 0', status.result_json)
        db.close()

    def test_fetch_stats_reports_ambiguous_matches_without_writing_stats(self):
        db = self.Session()
        db.add_all([
            Article(title="alpha beta long", slug="alpha-beta-long", status="draft"),
            Article(title="alpha beta other", slug="alpha-beta-other", status="draft"),
        ])
        db.commit()
        db.close()

        with (
            patch("config.Config.WECHAT_APP_ID", "appid"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.ARTICLES_DIR", "/tmp/missing"),
            patch("services.article_service.scan_articles_dir", return_value=[]),
            patch("services.wechat_service.get_published_articles", return_value={}),
            patch(
                "services.wechat_service.fetch_real_stats",
                return_value={"alpha beta": {"int_page_read_count": 8, "share_count": 1}},
            ),
        ):
            response = self.client.post("/api/analytics/fetch-stats")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["updated"], 0)
        self.assertEqual(data["ambiguous"], [{
            "title": "alpha beta",
            "candidates": ["alpha beta long", "alpha beta other"],
        }])
        self.assertGreaterEqual(len(data["warnings"]), 1)
        db = self.Session()
        self.assertEqual(db.query(ArticleStat).count(), 0)
        db.close()


if __name__ == "__main__":
    unittest.main()
