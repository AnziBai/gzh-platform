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

    return success_response(settings_payload(Config))
