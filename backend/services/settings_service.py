from pathlib import Path


ALLOWED_ENV_KEYS = {
    "WECHAT_APP_ID",
    "WECHAT_APP_SECRET",
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "CLAUDE_BIN",
    "GZHPUBLISHER_ROOT",
    "ARTICLES_DIR",
    "BENCHMARKS_DIR",
    "ASSETS_DIR",
}


def settings_payload(config) -> dict:
    return {
        "wechat": {
            "app_id": config.WECHAT_APP_ID or "",
            "app_secret_configured": bool(config.WECHAT_APP_SECRET),
        },
        "ai_writer": {
            "provider": config.AI_PROVIDER or "claude_cli",
            "base_url": config.AI_BASE_URL or "",
            "api_key_configured": bool(config.AI_API_KEY),
            "model": config.AI_MODEL or "",
            "claude_bin": config.CLAUDE_BIN or "",
        },
        "directories": {
            "gzhpublisher_root": config.GZHPUBLISHER_ROOT or "",
            "articles_dir": config.ARTICLES_DIR or "",
            "benchmarks_dir": config.BENCHMARKS_DIR or "",
            "assets_dir": config.ASSETS_DIR or "",
            "database_dir": str(Path(config.DB_PATH).parent),
        },
    }


def flatten_settings(body: dict) -> dict[str, str]:
    wechat = body.get("wechat") or {}
    ai_writer = body.get("ai_writer") or {}
    values = {
        "WECHAT_APP_ID": wechat.get("app_id"),
        "WECHAT_APP_SECRET": wechat.get("app_secret"),
        "AI_PROVIDER": ai_writer.get("provider"),
        "AI_BASE_URL": ai_writer.get("base_url"),
        "AI_API_KEY": ai_writer.get("api_key"),
        "AI_MODEL": ai_writer.get("model"),
        "CLAUDE_BIN": ai_writer.get("claude_bin"),
    }
    return {
        key: str(value).strip()
        for key, value in values.items()
        if key in ALLOWED_ENV_KEYS and value is not None
    }


def update_env_file(env_path: str, updates: dict[str, str]) -> None:
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    output = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def bootstrap_directories(config, root_dir: str | None = None) -> dict:
    root = Path(root_dir or config.GZHPUBLISHER_ROOT).expanduser()
    articles_dir = root / "articles" / "published"
    benchmarks_dir = root / "skills" / "fuwei-geo" / "references" / "benchmark-articles"
    assets_dir = root / "assets"
    database_dir = Path(config.DB_PATH).parent

    for path in (root, articles_dir, benchmarks_dir, assets_dir, database_dir):
        path.mkdir(parents=True, exist_ok=True)

    updates = {
        "GZHPUBLISHER_ROOT": _normalize_path(root),
        "ARTICLES_DIR": _normalize_path(articles_dir),
        "BENCHMARKS_DIR": _normalize_path(benchmarks_dir),
        "ASSETS_DIR": _normalize_path(assets_dir),
    }
    update_env_file(config.ENV_PATH, updates)

    for key, value in updates.items():
        setattr(config, key, value)

    return {
        "created": updates | {"DATABASE_DIR": _normalize_path(database_dir)},
        "next_steps": [
            "Fill WeChat App ID and App Secret",
            "Fill AI provider credentials",
            "Configure WeChat IP whitelist",
            "Run diagnostics and connection tests",
        ],
    }


def _normalize_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")
