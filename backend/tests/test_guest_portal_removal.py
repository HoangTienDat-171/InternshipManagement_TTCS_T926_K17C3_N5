"""Regression checks for removing the out-of-scope public guest portal."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.main import app


class GuestPortalRemovalTests(unittest.TestCase):
    def test_guest_api_routes_are_not_registered(self):
        route_paths = {getattr(route, "path", "") for route in app.routes}
        self.assertFalse(any(path.startswith("/api/guest") for path in route_paths))

    def test_fresh_schema_does_not_create_guest_application_table(self):
        with tempfile.TemporaryDirectory(prefix="ims-no-guest-") as temp_dir:
            db_path = Path(temp_dir) / "no_guest.sqlite3"
            with (
                patch.object(database, "DATABASE_BACKEND", "sqlite"),
                patch.object(database, "DB_FILE", str(db_path)),
            ):
                database.init_db()
                connection = database.get_db_connection()
                try:
                    table = connection.execute("""
                        SELECT name FROM sqlite_master
                        WHERE type = 'table' AND name = 'HO_SO_UNG_TUYEN_GUEST'
                    """).fetchone()
                finally:
                    connection.close()
            self.assertIsNone(table)


if __name__ == "__main__":
    unittest.main()
