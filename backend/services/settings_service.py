import os
from pathlib import Path

from services.model_preset_service import find_model_preset, model_presets


ALLOWED_ENV_KEYS = {
    "WECHAT_APP_ID",
    "WECHAT_APP_SECRET",
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_PRESET_PROVIDER",
    "AI_EXTRA_BODY_JSON",
    "CLAUDE_BIN",
    "SEARCH_PROVIDER",
    "SEARCH_API_KEY",
    "SEARCH_BASE_URL",
    "HOT_SOURCE_PRESETS_JSON",
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
            "preset_provider": config.AI_PRESET_PROVIDER or "",
            "extra_body_json": config.AI_EXTRA_BODY_JSON or "",
            "claude_bin": config.CLAUDE_BIN or "",
        },
        "search": {
            "provider": config.SEARCH_PROVIDER or "",
            "base_url": config.SEARCH_BASE_URL or "",
            "api_key_configured": bool(config.SEARCH_API_KEY),
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
        "AI_PRESET_PROVIDER": ai_writer.get("preset_provider"),
        "AI_EXTRA_BODY_JSON": ai_writer.get("extra_body_json"),
        "CLAUDE_BIN": ai_writer.get("claude_bin"),
        "SEARCH_PROVIDER": (body.get("search") or {}).get("provider"),
        "SEARCH_API_KEY": (body.get("search") or {}).get("api_key"),
        "SEARCH_BASE_URL": (body.get("search") or {}).get("base_url"),
        "HOT_SOURCE_PRESETS_JSON": body.get("hot_source_presets_json"),
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


def discover_credentials(config) -> dict:
    env_values = _read_env_file(config.ENV_PATH)
    providers = []
    active_preset = getattr(config, "AI_PRESET_PROVIDER", "") or env_values.get("AI_PRESET_PROVIDER", "")
    for preset in model_presets():
        key_info = _find_provider_key(preset, env_values, active_preset)
        providers.append({
            "key": preset["key"],
            "name": preset["name"],
            "base_url": preset["base_url"],
            "model": preset["recommended_models"][0] if preset["recommended_models"] else "",
            "provider": preset["provider"],
            "key_env_names": preset.get("key_env_names", []),
            "has_key": bool(key_info),
            "key_source": key_info["source"] if key_info else None,
            "key_name": key_info["name"] if key_info else None,
            "key_preview": _mask_secret(key_info["value"]) if key_info else None,
        })
    return {
        "providers": providers,
        "current": settings_payload(config)["ai_writer"],
    }


def setup_wizard(config, body: dict) -> dict:
    preset_key = (body.get("preset_provider") or "").strip()
    preset = find_model_preset(preset_key)
    if not preset:
        raise RuntimeError("请选择有效的模型预设")

    env_values = _read_env_file(config.ENV_PATH)
    explicit_key = (body.get("api_key") or "").strip()
    active_preset = getattr(config, "AI_PRESET_PROVIDER", "") or env_values.get("AI_PRESET_PROVIDER", "")
    discovered = _find_provider_key(preset, env_values, active_preset)
    api_key = explicit_key or (discovered["value"] if discovered else "")
    if not api_key:
        raise RuntimeError("没有发现 API Key，请手动填写后再保存")

    base_url = (body.get("base_url") or preset.get("base_url") or "").strip()
    model = (body.get("model") or (preset.get("recommended_models") or [""])[0]).strip()
    if not base_url or not model:
        raise RuntimeError("Base URL 和 Model 不能为空")

    extra_body_json = body.get("extra_body_json")
    if extra_body_json is None:
        extra_body_json = ""

    updates = {
        "AI_PROVIDER": preset["provider"],
        "AI_PRESET_PROVIDER": preset["key"],
        "AI_BASE_URL": base_url,
        "AI_MODEL": model,
        "AI_API_KEY": api_key,
        "AI_EXTRA_BODY_JSON": str(extra_body_json).strip(),
    }
    update_env_file(config.ENV_PATH, updates)
    for key, value in updates.items():
        setattr(config, key, value)

    return {
        "saved": {
            key: (_mask_secret(value) if key == "AI_API_KEY" else value)
            for key, value in updates.items()
        },
        "used_discovered_key": bool(discovered and not explicit_key),
        "key_source": discovered["source"] if discovered and not explicit_key else "manual",
        "settings": settings_payload(config),
    }


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


def _read_env_file(env_path: str) -> dict[str, str]:
    path = Path(env_path)
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _find_provider_key(preset: dict, env_values: dict[str, str], active_preset: str | None = None) -> dict | None:
    names = list(preset.get("key_env_names") or [])
    if preset.get("key") == "custom":
        names = ["AI_API_KEY"]
    elif preset.get("key") == active_preset and "AI_API_KEY" not in names:
        names.append("AI_API_KEY")

    for name in names:
        if name == "AI_API_KEY" and preset.get("key") not in {"custom", active_preset}:
            continue
        value = os.getenv(name) or env_values.get(name)
        if value:
            source = "environment" if os.getenv(name) else "backend/.env"
            return {"name": name, "value": value, "source": source}
    return None


def _mask_secret(value: str) -> str:
    value = value or ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"
