import os
import shutil
import subprocess
from pathlib import Path

from services.ai_client import find_claude_bin
from services.prompt_loader import load_auditor_spec, load_writer_spec


def _status(ok: bool, label: str, detail: str, action: str = "") -> dict:
    return {
        "ok": ok,
        "label": label,
        "detail": detail,
        "action": action,
    }


def _npm_prefix() -> str:
    try:
        proc = subprocess.run(
            ["npm", "config", "get", "prefix"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return ""


def _wenyan_core_exists() -> tuple[bool, str]:
    prefix = os.environ.get("npm_config_prefix") or _npm_prefix()
    candidates = []
    if prefix:
        candidates.append(Path(prefix) / "node_modules" / "@wenyan-md" / "mcp")
    candidates.append(Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@wenyan-md" / "mcp")

    for root in candidates:
        wrapper = root / "node_modules" / "@wenyan-md" / "core" / "dist" / "wrapper.js"
        utils = root / "dist" / "utils.js"
        if wrapper.exists() and utils.exists():
            return True, str(root)
    return False, "未找到 @wenyan-md/mcp 的全局安装目录"


def deployment_diagnostics(config) -> dict:
    checks = []

    env_path = Path(config.ENV_PATH)
    checks.append(_status(
        env_path.exists(),
        ".env 配置文件",
        str(env_path),
        "复制 backend/.env.example 为 backend/.env，然后在设置页填写配置。",
    ))

    articles_dir = Path(config.ARTICLES_DIR)
    checks.append(_status(
        articles_dir.exists(),
        "文章目录",
        str(articles_dir),
        "设置 ARTICLES_DIR，或创建该目录用于保存生成文章。",
    ))

    benchmarks_dir = Path(getattr(config, "BENCHMARKS_DIR", Path(config.ARTICLES_DIR).parent / "benchmarks"))
    checks.append(_status(
        benchmarks_dir.exists(),
        "素材目录",
        str(benchmarks_dir),
        "设置 BENCHMARKS_DIR，或通过首次部署向导创建素材目录。",
    ))

    writer_spec, writer_source = load_writer_spec(config)
    auditor_spec, auditor_source = load_auditor_spec(config)
    checks.append(_status(bool(writer_spec.strip()), "写作规范", writer_source))
    checks.append(_status(bool(auditor_spec.strip()), "审查规范", auditor_source))

    provider = (config.AI_PROVIDER or "claude_cli").strip()
    if provider == "claude_cli":
        claude_bin = find_claude_bin(config)
        checks.append(_status(
            bool(claude_bin),
            "Claude CLI",
            claude_bin or "未找到 Claude CLI",
            "在设置页填写 Claude CLI 路径，或把 Provider 改为 OpenAI-compatible API。",
        ))
    elif provider == "openai_compatible":
        missing = [
            name
            for name, value in (
                ("AI_BASE_URL", config.AI_BASE_URL),
                ("AI_API_KEY", config.AI_API_KEY),
                ("AI_MODEL", config.AI_MODEL),
            )
            if not (value or "").strip()
        ]
        checks.append(_status(
            not missing,
            "OpenAI-compatible API",
            "已填写 Base URL / API Key / Model" if not missing else f"缺少：{', '.join(missing)}",
            "在设置页补齐 API Base URL、API Key 和 Model，然后点击测试 AI 连接。",
        ))
    else:
        checks.append(_status(False, "AI Provider", f"不支持的 Provider：{provider}", "选择 Claude CLI 或 OpenAI-compatible API。"))

    checks.append(_status(
        bool((config.WECHAT_APP_ID or "").strip() and (config.WECHAT_APP_SECRET or "").strip()),
        "微信公众号凭证",
        "已填写 AppID 和 AppSecret" if config.WECHAT_APP_ID and config.WECHAT_APP_SECRET else "缺少 AppID 或 AppSecret",
        "在设置页填写自己的公众号 AppID/AppSecret，并把本机公网 IP 加入公众号后台白名单。",
    ))

    node_path = shutil.which("node")
    checks.append(_status(
        bool(node_path),
        "Node.js",
        node_path or "未找到 node",
        "安装 Node.js，并确保 node 在 PATH 中。",
    ))

    publish_script = Path(__file__).resolve().parents[1] / "publish_wenyan.mjs"
    checks.append(_status(
        publish_script.exists(),
        "排版发布脚本",
        str(publish_script),
        "确认 backend/publish_wenyan.mjs 存在。",
    ))

    wenyan_ok, wenyan_detail = _wenyan_core_exists()
    checks.append(_status(
        wenyan_ok,
        "Wenyan 排版依赖",
        wenyan_detail,
        "安装 @wenyan-md/mcp，或确保 npm 全局 prefix 下存在 @wenyan-md/mcp。",
    ))

    git_path = shutil.which("git")
    checks.append(_status(
        bool(git_path),
        "Git",
        git_path or "未找到 git",
        "安装 Git；发布归档失败不阻止发布，但建议配置。",
    ))

    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }
