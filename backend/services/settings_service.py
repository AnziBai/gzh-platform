from pathlib import Path


ALLOWED_ENV_KEYS = {
    "WECHAT_APP_ID",
    "WECHAT_APP_SECRET",
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "CLAUDE_BIN",
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
