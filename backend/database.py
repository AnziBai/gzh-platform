import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import Config

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    from models import Article, ArticleStat, Benchmark, MaterialCandidate, Topic, Task, SyncStatus  # noqa: F401
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_article_stats_columns()
    _ensure_benchmark_columns()
    _ensure_topic_workflow_columns()


def _ensure_article_stats_columns():
    inspector = inspect(engine)
    if "article_stats" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("article_stats")}
    missing_columns = {
        "recommend_count": "INTEGER DEFAULT 0",
        "underline_count": "INTEGER DEFAULT 0",
    }
    with engine.begin() as conn:
        for name, definition in missing_columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE article_stats ADD COLUMN {name} {definition}"))


def _ensure_benchmark_columns():
    _ensure_columns(
        "benchmarks",
        {
            "material_type": "VARCHAR DEFAULT 'reference_article' NOT NULL",
            "source_kind": "VARCHAR",
            "source_hash": "VARCHAR",
            "classification_reason": "TEXT",
            "approved_from_candidate_id": "INTEGER",
        },
    )


def _ensure_topic_workflow_columns():
    _ensure_columns(
        "topics",
        {
            "brief_json": "TEXT",
            "material_ids_json": "TEXT",
            "reference_article_slug": "VARCHAR",
            "generated_article_id": "INTEGER",
        },
    )


def _ensure_columns(table_name: str, missing_columns: dict[str, str]):
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as conn:
        for name, definition in missing_columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
