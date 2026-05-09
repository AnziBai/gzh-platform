import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.ai_client import AIClientError, OpenAICompatibleClient, get_ai_client


class DummyConfig:
    AI_PROVIDER = "openai_compatible"
    AI_BASE_URL = "https://api.example.com/v1"
    AI_API_KEY = "sk-test"
    AI_MODEL = "writer-model"
    CLAUDE_BIN = ""
    GZHPUBLISHER_ROOT = "."


class AIClientTest(unittest.TestCase):
    def test_get_ai_client_returns_openai_compatible_client(self):
        client = get_ai_client(DummyConfig)
        self.assertIsInstance(client, OpenAICompatibleClient)

    def test_openai_compatible_generates_text(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "hello"}}],
        }

        with patch("requests.post", return_value=response) as post:
            result = OpenAICompatibleClient(DummyConfig).generate_text("prompt")

        self.assertEqual(result.text, "hello")
        self.assertEqual(result.provider, "openai_compatible")
        self.assertEqual(result.model, "writer-model")
        self.assertEqual(post.call_args.args[0], "https://api.example.com/v1/chat/completions")

    def test_openai_compatible_reports_auth_failure(self):
        response = Mock()
        response.status_code = 401
        response.text = "unauthorized"

        with patch("requests.post", return_value=response):
            with self.assertRaisesRegex(AIClientError, "鉴权失败"):
                OpenAICompatibleClient(DummyConfig).generate_text("prompt")

    def test_openai_compatible_rejects_bad_response_shape(self):
        response = Mock()
        response.status_code = 200
        response.text = "{}"
        response.json.return_value = {}

        with patch("requests.post", return_value=response):
            with self.assertRaisesRegex(AIClientError, "响应格式"):
                OpenAICompatibleClient(DummyConfig).generate_text("prompt")


if __name__ == "__main__":
    unittest.main()
