import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.generate_service import (
    _build_reference_article_hint,
    _find_claude_bin,
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


if __name__ == "__main__":
    unittest.main()
