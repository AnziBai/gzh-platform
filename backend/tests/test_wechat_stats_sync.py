import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import Base
from models import Article, ArticleStat
from services.wechat_stats_sync import normalize_api_stats, sync_article_stats


class WechatStatsSyncTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.session_patch = patch("services.wechat_stats_sync.SessionLocal", self.Session)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def test_sync_updates_standard_metric_fields(self):
        db = self.Session()
        article = Article(title="测试文章", slug="test-article", status="draft")
        db.add(article)
        db.commit()
        db.close()

        result = sync_article_stats([
            {
                "title": "测试文章",
                "read_count": 8,
                "share_count": 4,
                "like_count": 1,
                "recommend_count": 2,
                "comment_count": 3,
                "underline_count": 5,
            }
        ])

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["unmatched"], [])
        db = self.Session()
        article = db.query(Article).filter_by(slug="test-article").one()
        stat = db.query(ArticleStat).filter_by(article_id=article.id).one()
        self.assertEqual(article.status, "published")
        self.assertEqual(stat.read_count, 8)
        self.assertEqual(stat.share_count, 4)
        self.assertEqual(stat.like_count, 1)
        self.assertEqual(stat.recommend_count, 2)
        self.assertEqual(stat.comment_count, 3)
        self.assertEqual(stat.underline_count, 5)
        db.close()

    def test_sync_dry_run_does_not_write_database(self):
        db = self.Session()
        db.add(Article(title="测试文章", slug="test-article", status="draft"))
        db.commit()
        db.close()

        result = sync_article_stats([
            {"title": "测试文章", "read_count": 8, "share_count": 4}
        ], dry_run=True)

        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["updated"], 1)
        db = self.Session()
        article = db.query(Article).filter_by(slug="test-article").one()
        self.assertEqual(article.status, "draft")
        self.assertEqual(db.query(ArticleStat).count(), 0)
        db.close()

    def test_sync_reports_unmatched_without_creating_by_default(self):
        result = sync_article_stats([
            {"title": "陌生文章", "read_count": 8, "share_count": 4}
        ])

        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unmatched"], ["陌生文章"])
        db = self.Session()
        self.assertEqual(db.query(Article).count(), 0)
        self.assertEqual(db.query(ArticleStat).count(), 0)
        db.close()

    def test_normalize_api_stats_maps_supported_fields_only(self):
        records = normalize_api_stats({
            "测试文章": {
                "int_page_read_count": 8,
                "share_count": 4,
                "add_to_fav_count": 2,
                "ori_page_read_count": 1,
            }
        })

        self.assertEqual(records, [{
            "title": "测试文章",
            "read_count": 8,
            "share_count": 4,
            "like_count": 0,
            "recommend_count": 2,
            "comment_count": 0,
            "underline_count": 0,
            "source": "api",
        }])

    def test_sync_does_not_use_ambiguous_partial_title_match(self):
        db = self.Session()
        db.add_all([
            Article(title="alpha beta long", slug="alpha-beta-long", status="draft"),
            Article(title="alpha beta other", slug="alpha-beta-other", status="draft"),
        ])
        db.commit()
        db.close()

        result = sync_article_stats([
            {"title": "alpha beta", "read_count": 8, "share_count": 4}
        ])

        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unmatched"], [])
        self.assertEqual(result["ambiguous"], [{
            "title": "alpha beta",
            "candidates": ["alpha beta long", "alpha beta other"],
        }])
        db = self.Session()
        self.assertEqual(db.query(ArticleStat).count(), 0)
        db.close()

    def test_sync_reports_match_details_for_exact_and_partial_matches(self):
        db = self.Session()
        db.add_all([
            Article(title="Exact Article", slug="exact-article", status="draft"),
            Article(title="Long Unique Article", slug="long-unique-article", status="draft"),
        ])
        db.commit()
        db.close()

        result = sync_article_stats([
            {"title": "Exact Article", "read_count": 10},
            {"title": "Long Unique Art", "read_count": 8},
        ], dry_run=True)

        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["updated"], 2)
        self.assertEqual(result["matches"], [
            {"title": "Exact Article", "article_id": 1, "article_title": "Exact Article", "match_type": "exact", "confidence": 1.0},
            {"title": "Long Unique Art", "article_id": 2, "article_title": "Long Unique Article", "match_type": "partial", "confidence": 0.76},
        ])


if __name__ == "__main__":
    unittest.main()
