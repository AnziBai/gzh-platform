import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GZHPUBLISHER_ROOT = os.getenv("GZHPUBLISHER_ROOT", "C:/Users/anzib/gzhpublisher")
    ARTICLES_DIR = os.getenv("ARTICLES_DIR", os.path.join(GZHPUBLISHER_ROOT, "articles/published"))
    BENCHMARKS_DIR = os.getenv("BENCHMARKS_DIR", os.path.join(GZHPUBLISHER_ROOT, "skills/fuwei-geo/references/benchmark-articles"))
    ASSETS_DIR = os.getenv("ASSETS_DIR", os.path.join(GZHPUBLISHER_ROOT, "assets"))

    WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "")
    WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "")

    FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "gzh_platform.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

    HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")
