import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import database


class DatabaseInitTest(unittest.TestCase):
    def test_init_db_creates_sqlite_parent_directory(self):
        tmp_root = BACKEND_DIR / "tests" / ".tmp"
        tmp_root.mkdir(exist_ok=True)
        db_path = tmp_root / f"db-init-{uuid.uuid4().hex}" / "missing" / "gzh_platform.db"

        with (
            patch("database.Config.DB_PATH", str(db_path)),
            patch("database.Base.metadata.create_all") as create_all,
        ):
            database.init_db()

        self.assertTrue(db_path.parent.is_dir())
        create_all.assert_called_once_with(bind=database.engine)


if __name__ == "__main__":
    unittest.main()
