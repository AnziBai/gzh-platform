import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database


class DatabaseInitTest(unittest.TestCase):
    def test_init_db_creates_sqlite_parent_directory(self):
        tmp_root = BACKEND_DIR / "tests" / ".tmp"
        tmp_root.mkdir(exist_ok=True)
        db_path = tmp_root / f"db-init-{uuid.uuid4().hex}" / "missing" / "gzh_platform.db"
        test_engine = create_engine("sqlite:///:memory:")

        with (
            patch("database.Config.DB_PATH", str(db_path)),
            patch("database.engine", test_engine),
            patch("database.Base.metadata.create_all") as create_all,
        ):
            database.init_db()

        self.assertTrue(db_path.parent.is_dir())
        create_all.assert_called_once_with(bind=test_engine)

    def test_ensure_columns_backfills_existing_sqlite_tables(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE topics (id INTEGER PRIMARY KEY, title VARCHAR)"))

        with patch("database.engine", engine):
            database._ensure_topic_workflow_columns()

        columns = {column["name"] for column in inspect(engine).get_columns("topics")}
        self.assertIn("brief_json", columns)
        self.assertIn("material_ids_json", columns)
        self.assertIn("knowledge_chunk_ids_json", columns)
        self.assertIn("reference_article_slug", columns)
        self.assertIn("generated_article_id", columns)

    def test_init_db_creates_knowledge_tables_and_topic_column(self):
        tmp_root = BACKEND_DIR / "tests" / ".tmp"
        tmp_root.mkdir(exist_ok=True)
        db_path = tmp_root / f"knowledge-db-init-{uuid.uuid4().hex}" / "gzh_platform.db"
        engine = create_engine("sqlite:///:memory:")

        with (
            patch("database.Config.DB_PATH", str(db_path)),
            patch("database.engine", engine),
        ):
            database.init_db()

        with engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("knowledge_files", tables)
            self.assertIn("knowledge_chunks", tables)

            topic_columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(topics)")
            }
            self.assertIn("knowledge_chunk_ids_json", topic_columns)


if __name__ == "__main__":
    unittest.main()
