import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from routes.settings import settings_bp


class SettingsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(settings_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_get_settings_masks_secrets(self):
        with (
            patch("config.Config.WECHAT_APP_ID", "wx123"),
            patch("config.Config.WECHAT_APP_SECRET", "secret"),
            patch("config.Config.AI_PROVIDER", "openai_compatible"),
            patch("config.Config.AI_BASE_URL", "https://api.example.com/v1"),
            patch("config.Config.AI_API_KEY", "sk-real"),
            patch("config.Config.AI_MODEL", "writer-model"),
            patch("config.Config.CLAUDE_BIN", "C:/tools/claude.cmd"),
        ):
            response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["wechat"]["app_id"], "wx123")
        self.assertTrue(data["wechat"]["app_secret_configured"])
        self.assertNotIn("'secret'", str(data))
        self.assertEqual(data["ai_writer"]["provider"], "openai_compatible")
        self.assertTrue(data["ai_writer"]["api_key_configured"])
        self.assertNotIn("sk-real", str(data))

    def test_update_settings_writes_allowed_env_values(self):
        with (
            patch("config.Config.ENV_PATH", "backend/.env"),
            patch("services.settings_service.update_env_file") as update_env_file,
            patch("services.wechat_service.reset_access_token_cache") as reset_access_token_cache,
        ):
            response = self.client.put(
                "/api/settings",
                json={
                    "wechat": {
                        "app_id": "wx-new",
                        "app_secret": "wx-secret",
                    },
                    "ai_writer": {
                        "provider": "openai_compatible",
                        "base_url": "https://api.example.com/v1",
                        "api_key": "sk-new",
                        "model": "deepseek-chat",
                        "claude_bin": "C:/tools/claude.cmd",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        update_env_file.assert_called_once()
        reset_access_token_cache.assert_called_once()
        _, updates = update_env_file.call_args.args
        self.assertEqual(updates["WECHAT_APP_ID"], "wx-new")
        self.assertEqual(updates["WECHAT_APP_SECRET"], "wx-secret")
        self.assertEqual(updates["AI_PROVIDER"], "openai_compatible")
        self.assertEqual(updates["AI_API_KEY"], "sk-new")
        self.assertEqual(updates["AI_MODEL"], "deepseek-chat")

        data = response.get_json()["data"]
        self.assertTrue(data["wechat"]["app_secret_configured"])
        self.assertTrue(data["ai_writer"]["api_key_configured"])
        self.assertNotIn("wx-secret", str(data))
        self.assertNotIn("sk-new", str(data))

    def test_test_ai_settings_returns_masked_result(self):
        with patch(
            "services.ai_client.test_ai_connection",
            return_value={"ok": True, "provider": "openai_compatible", "model": "m", "message": "OK"},
        ):
            response = self.client.post("/api/settings/test-ai")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["message"], "OK")

    def test_test_wechat_settings_requires_credentials(self):
        with (
            patch("config.Config.WECHAT_APP_ID", ""),
            patch("config.Config.WECHAT_APP_SECRET", ""),
        ):
            response = self.client.post("/api/settings/test-wechat")

        self.assertEqual(response.status_code, 400)

    def test_settings_diagnostics_returns_checks(self):
        with patch(
            "services.environment_check_service.deployment_diagnostics",
            return_value={
                "ok": False,
                "checks": [{"ok": False, "label": "Git", "detail": "missing", "action": "install"}],
                "setup_steps": [{"key": "local_workspace", "title": "准备本地工作区", "ok": False}],
                "capabilities": {"can_generate_articles": False},
            },
        ):
            response = self.client.get("/api/settings/diagnostics")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["checks"][0]["label"], "Git")
        self.assertEqual(data["setup_steps"][0]["key"], "local_workspace")
        self.assertFalse(data["capabilities"]["can_generate_articles"])

    def test_bootstrap_settings_creates_directories_and_returns_diagnostics(self):
        with (
            patch("services.settings_service.bootstrap_directories", return_value={"created": {"ARTICLES_DIR": "C:/content/articles/published"}, "next_steps": []}) as bootstrap,
            patch("services.environment_check_service.deployment_diagnostics", return_value={"ok": True, "checks": []}) as diagnostics,
        ):
            response = self.client.post("/api/settings/bootstrap", json={"root_dir": "C:/content"})

        self.assertEqual(response.status_code, 200)
        bootstrap.assert_called_once()
        diagnostics.assert_called_once()
        data = response.get_json()["data"]
        self.assertEqual(data["created"]["ARTICLES_DIR"], "C:/content/articles/published")
        self.assertTrue(data["diagnostics"]["ok"])

    def test_model_presets_include_openai_and_mimo(self):
        response = self.client.get("/api/settings/model-presets")

        self.assertEqual(response.status_code, 200)
        presets = {item["key"]: item for item in response.get_json()["data"]}
        self.assertEqual(presets["openai"]["base_url"], "https://api.openai.com/v1")
        self.assertEqual(presets["mimo"]["base_url"], "https://api.mimo-v2.com/v1")
        self.assertIn("mimo-v2-pro", presets["mimo"]["recommended_models"])

    def test_credential_discovery_masks_env_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-1234567890"}, clear=False):
            response = self.client.get("/api/settings/credential-discovery")

        self.assertEqual(response.status_code, 200)
        openai = next(item for item in response.get_json()["data"]["providers"] if item["key"] == "openai")
        self.assertTrue(openai["has_key"])
        self.assertEqual(openai["key_name"], "OPENAI_API_KEY")
        self.assertNotIn("1234567890", str(openai))

    def test_setup_wizard_uses_discovered_key_and_writes_env(self):
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-setup"}, clear=False),
            patch("config.Config.ENV_PATH", "backend/.env"),
            patch("services.settings_service.update_env_file") as update_env_file,
            patch("services.environment_check_service.deployment_diagnostics", return_value={"ok": True, "checks": []}),
        ):
            response = self.client.post(
                "/api/settings/setup-wizard",
                json={"preset_provider": "openai", "model": "gpt-4.1-mini"},
            )

        self.assertEqual(response.status_code, 200)
        _, updates = update_env_file.call_args.args
        self.assertEqual(updates["AI_PROVIDER"], "openai_compatible")
        self.assertEqual(updates["AI_PRESET_PROVIDER"], "openai")
        self.assertEqual(updates["AI_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(updates["AI_MODEL"], "gpt-4.1-mini")
        self.assertEqual(updates["AI_API_KEY"], "sk-test-setup")
        self.assertTrue(response.get_json()["data"]["used_discovered_key"])


if __name__ == "__main__":
    unittest.main()
