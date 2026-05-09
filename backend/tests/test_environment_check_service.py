import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.environment_check_service import deployment_diagnostics


class DummyConfig:
    ENV_PATH = "backend/.env"
    ARTICLES_DIR = "articles"
    GZHPUBLISHER_ROOT = "missing-gzhpublisher"
    AI_PROVIDER = "openai_compatible"
    AI_BASE_URL = "https://api.example.com/v1"
    AI_API_KEY = "sk-test"
    AI_MODEL = "model"
    CLAUDE_BIN = ""
    WECHAT_APP_ID = "wx"
    WECHAT_APP_SECRET = "secret"


class EnvironmentCheckServiceTest(unittest.TestCase):
    def test_deployment_diagnostics_reports_expected_sections(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("services.environment_check_service._wenyan_core_exists", return_value=(True, "wenyan")),
            patch("shutil.which", return_value="C:/bin/tool.exe"),
        ):
            result = deployment_diagnostics(DummyConfig)

        labels = [check["label"] for check in result["checks"]]
        self.assertIn("OpenAI-compatible API", labels)
        self.assertIn("微信公众号凭证", labels)
        self.assertIn("Wenyan 排版依赖", labels)
        self.assertTrue(result["ok"])

    def test_deployment_diagnostics_flags_missing_openai_config(self):
        class MissingAI(DummyConfig):
            AI_API_KEY = ""

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("services.environment_check_service._wenyan_core_exists", return_value=(True, "wenyan")),
            patch("shutil.which", return_value="C:/bin/tool.exe"),
        ):
            result = deployment_diagnostics(MissingAI)

        api_check = next(check for check in result["checks"] if check["label"] == "OpenAI-compatible API")
        self.assertFalse(api_check["ok"])
        self.assertIn("AI_API_KEY", api_check["detail"])


if __name__ == "__main__":
    unittest.main()
