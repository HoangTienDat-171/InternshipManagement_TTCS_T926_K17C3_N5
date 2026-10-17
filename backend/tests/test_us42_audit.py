import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app import audit_service, database
from app.routes import audit_routes


def request_as(user):
    return SimpleNamespace(state=SimpleNamespace(current_user=user), client=None, headers={})


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ims-us42-test-")
        cls.db_path = Path(cls.temp.name) / "audit.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()
        cls.db = database.get_db_connection()
        audit_service.create_sqlite_schema(cls.db)
        cls.db.commit()
        cls.admin = {"ma_nguoi_dung": 17, "ho_ten": "Audit Admin", "vai_tro": "Admin"}
        cls.hr = {"ma_nguoi_dung": 18, "ho_ten": "Audit HR", "vai_tro": "HR"}
        for action, resource, outcome, metadata in (
            ("BACKUP_CREATED", "BACKUP", "SUCCESS", {"file_size_bytes": 20, "api_key": "must-not-appear"}),
            ("ATTENDANCE_CHECK_IN", "ATTENDANCE", "SUCCESS", {"source": "QR", "token": "must-not-appear", "email": "must-not-appear@example.test"}),
            ("AUTH_LOGIN_FAILURE", "AUTHENTICATION", "FAILURE", {"reason": "INVALID_CREDENTIALS"}),
        ):
            audit_service.write_audit_event(
                cls.db, actor=cls.admin, action=action, resource=resource, outcome=outcome, metadata=metadata,
            )
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp.cleanup()

    def test_admin_can_filter_paginate_and_view_sanitized_event_detail(self):
        response = audit_routes.list_audit_events(
            request_as(self.admin), actor_id=17, action="attendance", resource="attendance",
            outcome="SUCCESS", date_from=None, date_to=None, page=1, page_size=1, db=self.db,
        )
        self.assertEqual(response["total"], 1)
        item = response["items"][0]
        self.assertEqual(item["action"], "ATTENDANCE_CHECK_IN")
        self.assertNotIn("ip_address", item)
        self.assertNotIn("session_id", item)
        self.assertNotIn("token", item["metadata"])
        detail = audit_routes.get_audit_event(item["event_id"], request_as(self.admin), db=self.db)
        self.assertEqual(detail["metadata"], {"source": "QR"})

    def test_non_admin_cannot_read_audit(self):
        with self.assertRaises(HTTPException) as context:
            audit_routes.list_audit_events(
                request_as(self.hr), actor_id=None, action=None, resource=None, outcome=None,
                date_from=None, date_to=None, page=1, page_size=20, db=self.db,
            )
        self.assertEqual(context.exception.status_code, 403)

    def test_audit_routes_are_read_only(self):
        routes = [route for route in audit_routes.router.routes if getattr(route, "path", "").startswith("/api/audit-logs")]
        self.assertTrue(routes)
        self.assertTrue(all(route.methods <= {"GET"} for route in routes))
