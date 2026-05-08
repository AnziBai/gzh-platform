from flask import Flask
from flask_cors import CORS
from config import Config
from database import init_db
from utils import success_response, error_response  # noqa: F401 — re-exported for convenience


def create_app():
    app = Flask(__name__)
    CORS(app)

    # 初始化数据库
    init_db()

    # 注册路由蓝图
    from routes.articles import articles_bp
    from routes.topics import topics_bp
    from routes.benchmarks import benchmarks_bp
    from routes.analytics import analytics_bp
    from routes.tasks import tasks_bp
    from routes.settings import settings_bp

    app.register_blueprint(articles_bp, url_prefix="/api")
    app.register_blueprint(topics_bp, url_prefix="/api")
    app.register_blueprint(benchmarks_bp, url_prefix="/api")
    app.register_blueprint(analytics_bp, url_prefix="/api")
    app.register_blueprint(tasks_bp, url_prefix="/api")
    app.register_blueprint(settings_bp, url_prefix="/api")

    @app.route("/api/health")
    def health():
        return success_response({"status": "ok"})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=Config.FLASK_PORT, debug=Config.FLASK_DEBUG)
