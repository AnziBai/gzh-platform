import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

import requests


class AIClientError(RuntimeError):
    pass


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", text or "")


def find_claude_bin(config) -> str | None:
    configured = (getattr(config, "CLAUDE_BIN", "") or "").strip()
    if configured and os.path.isfile(configured):
        return configured

    found = shutil.which("claude")
    if found:
        return found

    candidates = [
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/AppData/Local/Programs/claude/claude.exe"),
        os.path.expanduser("~/AppData/Roaming/npm/claude"),
        os.path.expanduser("~/AppData/Roaming/npm/claude.cmd"),
        "C:/Users/anzib/AppData/Roaming/npm/claude",
        "C:/Users/anzib/AppData/Roaming/npm/claude.cmd",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str = ""
    cost_usd: float | None = None
    duration_ms: int | None = None


class ClaudeCliClient:
    provider = "claude_cli"

    def __init__(self, config):
        self.config = config
        self.bin_path = find_claude_bin(config)

    def label(self) -> str:
        return f"Claude CLI ({self.bin_path or 'not configured'})"

    def generate_text(self, prompt: str) -> AIResponse:
        if not self.bin_path:
            raise AIClientError("找不到 Claude CLI，请在设置页填写 Claude CLI 路径，或改用 OpenAI-compatible API。")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [self.bin_path, "--print", "--output-format", "stream-json", "--verbose"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                cwd=getattr(self.config, "GZHPUBLISHER_ROOT", None) or None,
            )
            proc.stdin.write(prompt)
            proc.stdin.close()

            chunks = []
            duration_ms = None
            cost_usd = None
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    clean = strip_ansi(line)
                    if clean:
                        chunks.append(clean + "\n")
                    continue

                if obj.get("type") == "assistant":
                    for block in obj.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            chunks.append(block["text"])
                elif obj.get("type") == "result":
                    duration_ms = obj.get("duration_ms")
                    cost_usd = obj.get("cost_usd")
            proc.wait()
        except OSError as exc:
            raise AIClientError(f"Claude CLI 启动失败: {exc}") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.read()
            raise AIClientError(f"Claude CLI 退出码 {proc.returncode}: {stderr[:500]}")

        text = "".join(chunks).strip()
        if not text:
            raise AIClientError("Claude CLI 未输出任何内容。")
        return AIResponse(text=text, provider=self.provider, duration_ms=duration_ms, cost_usd=cost_usd)


class OpenAICompatibleClient:
    provider = "openai_compatible"

    def __init__(self, config):
        self.base_url = (getattr(config, "AI_BASE_URL", "") or "").strip().rstrip("/")
        self.api_key = (getattr(config, "AI_API_KEY", "") or "").strip()
        self.model = (getattr(config, "AI_MODEL", "") or "").strip()
        self.extra_body = _parse_extra_body(getattr(config, "AI_EXTRA_BODY_JSON", "") or "")

    def label(self) -> str:
        return f"OpenAI-compatible API ({self.model or 'model not configured'})"

    def generate_text(self, prompt: str) -> AIResponse:
        if not self.base_url:
            raise AIClientError("AI Base URL 未配置。")
        if not self.api_key:
            raise AIClientError("AI API Key 未配置。")
        if not self.model:
            raise AIClientError("AI Model 未配置。")

        url = self.base_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if "mimo" in self.base_url.lower() or "xiaomi" in self.base_url.lower():
                headers["api-key"] = self.api_key

            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                } | self.extra_body,
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AIClientError(f"AI API 请求失败: {exc}") from exc

        if response.status_code == 401:
            raise AIClientError("AI API 鉴权失败，请检查 API Key。")
        if response.status_code == 404:
            raise AIClientError("AI API 地址或模型不存在，请检查 Base URL 和 Model。")
        if response.status_code >= 400:
            raise AIClientError(f"AI API 返回错误 {response.status_code}: {response.text[:300]}")

        try:
            payload = response.json()
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIClientError(f"AI API 响应格式不兼容: {response.text[:300]}") from exc

        text = (text or "").strip()
        if not text:
            raise AIClientError("AI API 返回空内容。")
        return AIResponse(text=text, provider=self.provider, model=self.model)


def get_ai_client(config):
    provider = (getattr(config, "AI_PROVIDER", "") or "claude_cli").strip()
    if provider == "claude_cli":
        return ClaudeCliClient(config)
    if provider == "openai_compatible":
        return OpenAICompatibleClient(config)
    raise AIClientError(f"不支持的 AI Provider: {provider}")


def _parse_extra_body(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIClientError(f"AI_EXTRA_BODY_JSON 不是合法 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AIClientError("AI_EXTRA_BODY_JSON 必须是 JSON object")
    return parsed


def test_ai_connection(config) -> dict:
    client = get_ai_client(config)
    response = client.generate_text("请只回复 OK，用于测试模型连接。")
    return {
        "ok": True,
        "provider": response.provider,
        "model": response.model or getattr(config, "AI_MODEL", "") or "",
        "message": response.text[:120],
    }
