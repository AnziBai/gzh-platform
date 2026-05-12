import os
import shutil
import subprocess
from pathlib import Path

from services.ai_client import find_claude_bin
from services.prompt_loader import load_auditor_spec, load_writer_spec


def _status(ok: bool, label: str, detail: str, action: str = "", key: str = "") -> dict:
    status = {
        "ok": ok,
        "label": label,
        "detail": detail,
        "action": action,
    }
    if key:
        status["key"] = key
    return status


def _step(key: str, title: str, ok: bool, description: str, action: str) -> dict:
    return {
        "key": key,
        "title": title,
        "ok": ok,
        "description": description,
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


def _pdf_parser_check() -> dict:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return _status(
            False,
            "PDF parser",
            "Install pypdf to enable PDF knowledge uploads. Markdown and TXT uploads still work.",
            "Install pypdf to enable PDF knowledge uploads. Markdown and TXT uploads still work.",
            "pdf_parser",
        )

    return _status(
        True,
        "PDF parser",
        "pypdf is installed; PDF knowledge uploads are available.",
        "",
        "pdf_parser",
    )


def deployment_diagnostics(config) -> dict:
    checks = []

    env_path = Path(config.ENV_PATH)
    env_check = _status(
        env_path.exists(),
        ".env 配置文件",
        str(env_path),
        "复制 backend/.env.example 为 backend/.env，然后在设置页填写配置。",
    )
    checks.append(env_check)

    articles_dir = Path(config.ARTICLES_DIR)
    articles_check = _status(
        articles_dir.exists(),
        "文章目录",
        str(articles_dir),
        "设置 ARTICLES_DIR，或创建该目录用于保存生成文章。",
    )
    checks.append(articles_check)

    benchmarks_dir = Path(getattr(config, "BENCHMARKS_DIR", Path(config.ARTICLES_DIR).parent / "benchmarks"))
    benchmarks_check = _status(
        benchmarks_dir.exists(),
        "素材目录",
        str(benchmarks_dir),
        "设置 BENCHMARKS_DIR，或通过首次部署向导创建素材目录。",
    )
    checks.append(benchmarks_check)

    writer_spec, writer_source = load_writer_spec(config)
    auditor_spec, auditor_source = load_auditor_spec(config)
    writer_check = _status(bool(writer_spec.strip()), "写作规范", writer_source)
    auditor_check = _status(bool(auditor_spec.strip()), "审查规范", auditor_source)
    checks.append(writer_check)
    checks.append(auditor_check)

    provider = (config.AI_PROVIDER or "claude_cli").strip()
    if provider == "claude_cli":
        claude_bin = find_claude_bin(config)
        ai_check = _status(
            bool(claude_bin),
            "Claude CLI",
            claude_bin or "未找到 Claude CLI",
            "在设置页填写 Claude CLI 路径，或把 Provider 改为 OpenAI-compatible API。",
        )
        checks.append(ai_check)
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
        ai_check = _status(
            not missing,
            "OpenAI-compatible API",
            "已填写 Base URL / API Key / Model" if not missing else f"缺少：{', '.join(missing)}",
            "在设置页补齐 API Base URL、API Key 和 Model，然后点击测试 AI 连接。",
        )
        checks.append(ai_check)
    else:
        ai_check = _status(False, "AI Provider", f"不支持的 Provider：{provider}", "选择 Claude CLI 或 OpenAI-compatible API。")
        checks.append(ai_check)

    wechat_check = _status(
        bool((config.WECHAT_APP_ID or "").strip() and (config.WECHAT_APP_SECRET or "").strip()),
        "微信公众号凭证",
        "已填写 AppID 和 AppSecret" if config.WECHAT_APP_ID and config.WECHAT_APP_SECRET else "缺少 AppID 或 AppSecret",
        "在设置页填写自己的公众号 AppID/AppSecret，并把本机公网 IP 加入公众号后台白名单。",
    )
    checks.append(wechat_check)

    node_path = shutil.which("node")
    node_check = _status(
        bool(node_path),
        "Node.js",
        node_path or "未找到 node",
        "安装 Node.js，并确保 node 在 PATH 中。",
    )
    checks.append(node_check)

    publish_script = Path(__file__).resolve().parents[1] / "publish_wenyan.mjs"
    publish_script_check = _status(
        publish_script.exists(),
        "排版发布脚本",
        str(publish_script),
        "确认 backend/publish_wenyan.mjs 存在。",
    )
    checks.append(publish_script_check)

    wenyan_ok, wenyan_detail = _wenyan_core_exists()
    wenyan_check = _status(
        wenyan_ok,
        "Wenyan 排版依赖",
        wenyan_detail,
        "安装 @wenyan-md/mcp，或确保 npm 全局 prefix 下存在 @wenyan-md/mcp。",
    )
    checks.append(wenyan_check)

    pdf_parser_check = _pdf_parser_check()
    checks.append(pdf_parser_check)

    git_path = shutil.which("git")
    git_check = _status(
        bool(git_path),
        "Git",
        git_path or "未找到 git",
        "安装 Git；发布归档失败不阻止发布，但建议配置。",
    )
    checks.append(git_check)

    local_ready = all(item["ok"] for item in (env_check, articles_check, benchmarks_check, writer_check, auditor_check))
    ai_ready = ai_check["ok"]
    wechat_ready = wechat_check["ok"]
    publish_ready = all(item["ok"] for item in (wechat_check, node_check, publish_script_check, wenyan_check))

    setup_steps = [
        _step(
            "local_workspace",
            "准备本地工作区",
            local_ready,
            "文章目录、素材目录、写作规范和 .env 已准备好。",
            "点击首次部署向导创建目录；如仍失败，按下方诊断处理缺失项。",
        ),
        _step(
            "ai_writer",
            "配置 AI 写作",
            ai_ready,
            "热点简报和正文生成可以调用 AI。",
            "选择 Claude CLI 或 OpenAI-compatible API，保存后点击测试 AI 连接。",
        ),
        _step(
            "wechat_data",
            "连接微信公众号",
            wechat_ready,
            "可以同步公众号数据并测试凭证。",
            "填写 AppID/AppSecret，并在公众号后台把本机公网 IP 加入白名单。",
        ),
        _step(
            "publish_pipeline",
            "启用排版发布",
            publish_ready,
            "可以使用 Wenyan 排版并推送到公众号草稿箱。",
            "安装 Node.js 与 @wenyan-md/mcp；确认 publish_wenyan.mjs 存在。",
        ),
    ]

    capabilities = {
        "can_generate_articles": ai_ready and local_ready,
        "can_sync_wechat_data": wechat_ready,
        "can_publish_drafts": publish_ready and local_ready,
        "can_archive_outputs": git_check["ok"],
    }

    return {
        "ok": all(item["ok"] for item in checks if item.get("key") != "pdf_parser"),
        "checks": checks,
        "setup_steps": setup_steps,
        "capabilities": capabilities,
    }
