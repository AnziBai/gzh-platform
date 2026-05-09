from flask import Blueprint, request

from utils import success_response, error_response

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
def get_settings():
    from config import Config
    from services.settings_service import settings_payload

    return success_response(settings_payload(Config))


@settings_bp.route("/settings", methods=["PUT"])
def update_settings():
    from config import Config
    from services.settings_service import flatten_settings, settings_payload, update_env_file

    body = request.get_json(silent=True) or {}
    updates = flatten_settings(body)
    if not updates:
        return error_response("没有可保存的配置项", 400)

    update_env_file(Config.ENV_PATH, updates)

    for key, value in updates.items():
        setattr(Config, key, value)

    if "WECHAT_APP_ID" in updates or "WECHAT_APP_SECRET" in updates:
        from services.wechat_service import reset_access_token_cache
        reset_access_token_cache()

    return success_response(settings_payload(Config))


@settings_bp.route("/settings/test-ai", methods=["POST"])
def test_ai_settings():
    from config import Config
    from services.ai_client import AIClientError, test_ai_connection

    try:
        return success_response(test_ai_connection(Config))
    except AIClientError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"AI 连接测试失败: {e}", 500)


@settings_bp.route("/settings/test-wechat", methods=["POST"])
def test_wechat_settings():
    from config import Config
    from services.wechat_service import get_access_token

    if not Config.WECHAT_APP_ID or not Config.WECHAT_APP_SECRET:
        return error_response("WECHAT_APP_ID 或 WECHAT_APP_SECRET 未配置。", 400)

    try:
        token = get_access_token()
        return success_response({
            "ok": True,
            "app_id": Config.WECHAT_APP_ID,
            "message": f"access_token 获取成功，长度 {len(token)}。",
        })
    except RuntimeError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"微信公众号连接测试失败: {e}", 500)


@settings_bp.route("/settings/diagnostics")
def settings_diagnostics():
    from config import Config
    from services.environment_check_service import deployment_diagnostics

    try:
        return success_response(deployment_diagnostics(Config))
    except Exception as e:
        return error_response(f"环境诊断失败: {e}", 500)
