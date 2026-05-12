import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.rewrite_service import run_rewrite_for_publish


class FakeDb:
    def add(self, _record):
        pass

    def commit(self):
        pass

    def close(self):
        pass


class RewriteServiceTest(unittest.TestCase):
    def test_rewrite_wraps_body_without_frontmatter(self):
        # Regression: Browser-use QA found domestic-model rewrite output without frontmatter.
        # Found by /qa on 2026-05-12.
        # Report: Browser-use full workflow, publish pre-rewrite step.
        saved = {}

        def fake_save(content, _topic, _articles_dir):
            saved["content"] = content
            return "C:/articles/rewrite.md"

        with (
            patch("services.rewrite_service._find_article_path", return_value="C:/articles/source.md"),
            patch(
                "services.rewrite_service.parse_frontmatter",
                return_value={"frontmatter": {"title": "Source Title"}, "content": "Original body"},
            ),
            patch("services.rewrite_service._load_reference", return_value=""),
            patch(
                "services.rewrite_service.get_ai_client",
                return_value=SimpleNamespace(
                    label=lambda: "fake",
                    generate_text=lambda _prompt: SimpleNamespace(text="# 改写标题\n\n改写正文"),
                ),
            ),
            patch("services.rewrite_service._save_article", side_effect=fake_save),
            patch("services.rewrite_service.SessionLocal", return_value=FakeDb()),
            patch("config.Config.ARTICLES_DIR", "C:/articles"),
        ):
            result = run_rewrite_for_publish("task-1", "source-slug")

        self.assertEqual(result["slug"], "rewrite")
        self.assertTrue(saved["content"].startswith("---\n"))
        self.assertIn("title: 改写标题", saved["content"])
        self.assertIn("改写正文", saved["content"])


if __name__ == "__main__":
    unittest.main()
