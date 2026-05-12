import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.generate_service import (
    _build_reference_article_hint,
    _find_claude_bin,
    _normalize_generated_article,
    _validate_generated_article,
)


class GenerateServiceTest(unittest.TestCase):
    def test_find_claude_bin_prefers_configured_path(self):
        with (
            patch("config.Config.CLAUDE_BIN", "C:/tools/claude.cmd"),
            patch("os.path.isfile", return_value=True),
            patch("shutil.which", return_value="C:/path/claude.cmd"),
        ):
            self.assertEqual(_find_claude_bin(), "C:/tools/claude.cmd")

    def test_find_claude_bin_ignores_missing_configured_path(self):
        with (
            patch("config.Config.CLAUDE_BIN", "C:/missing/claude.cmd"),
            patch("os.path.isfile", return_value=False),
            patch("shutil.which", return_value="C:/path/claude.cmd"),
        ):
            self.assertEqual(_find_claude_bin(), "C:/path/claude.cmd")

    def test_build_reference_article_hint_reads_local_article(self):
        with (
            patch("config.Config.ARTICLES_DIR", "C:/articles"),
            patch("os.path.exists", return_value=True),
            patch("services.article_service.parse_frontmatter", return_value={"content": "参考正文"}),
        ):
            hint = _build_reference_article_hint("hot-slug")

        self.assertIn("hot-slug", hint)
        self.assertIn("参考正文", hint)

    def test_validate_generated_article_requires_frontmatter(self):
        with self.assertRaisesRegex(RuntimeError, "frontmatter"):
            _validate_generated_article("# title\n\nbody")

    def test_validate_generated_article_requires_title(self):
        with self.assertRaisesRegex(RuntimeError, "title"):
            _validate_generated_article("---\nslug: test\n---\n\n正文")

    def test_validate_generated_article_accepts_title_and_body(self):
        _validate_generated_article("---\ntitle: Test\nslug: test\n---\n\n正文")

    def test_normalize_generated_article_trims_preface_before_frontmatter(self):
        output = _normalize_generated_article(
            "Here is the article:\n\n---\ntitle: Test\nslug: test\n---\n\n正文",
            "Fallback Topic",
        )

        self.assertTrue(output.startswith("---\ntitle: Test"))
        self.assertNotIn("Here is the article", output)

    def test_normalize_generated_article_wraps_body_without_frontmatter(self):
        output = _normalize_generated_article(
            "# 风险控制回撤\n\n正文内容",
            "风险控制回撤的实战方法",
        )

        self.assertTrue(output.startswith("---\n"))
        self.assertIn("title: 风险控制回撤", output)
        self.assertIn("slug:", output)
        self.assertIn("正文内容", output)
        _validate_generated_article(output)


if __name__ == "__main__":
    unittest.main()
