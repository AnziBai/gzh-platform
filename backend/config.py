import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

    GZHPUBLISHER_ROOT = os.getenv("GZHPUBLISHER_ROOT", "C:/Users/anzib/gzhpublisher")
    ARTICLES_DIR = os.getenv("ARTICLES_DIR", os.path.join(GZHPUBLISHER_ROOT, "articles/published"))
    BENCHMARKS_DIR = os.getenv("BENCHMARKS_DIR", os.path.join(GZHPUBLISHER_ROOT, "skills/fuwei-geo/references/benchmark-articles"))
    ASSETS_DIR = os.getenv("ASSETS_DIR", os.path.join(GZHPUBLISHER_ROOT, "assets"))

    WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
    WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")
    WECHAT_STATS_DAYS_BACK = int(os.getenv("WECHAT_STATS_DAYS_BACK", "365"))
    WECHAT_STATS_MAX_WORKERS = int(os.getenv("WECHAT_STATS_MAX_WORKERS", "1"))

    AI_PROVIDER = os.getenv("AI_PROVIDER", "claude_cli")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "")
    CLAUDE_BIN = os.getenv("CLAUDE_BIN", "")

    FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "gzh_platform.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

    HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")
