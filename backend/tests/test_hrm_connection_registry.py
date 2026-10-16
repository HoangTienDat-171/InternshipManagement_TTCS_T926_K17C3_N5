from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import database, hrm_connection_service as service
from app.hrm_provider import HRMSandboxConfig, HRMSandboxProvider
from app.hrm_storage import ensure_hrm_sqlite_schema, load_sync_context, list_directory, persist_preview
from app.routes.hrm_connection_routes import get_connections


def request_as(role):
    return SimpleNamespace(state=SimpleNamespace(current_user={"ma_nguoi_dung": 1, "vai_tro": role}))


class HRMConnectionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ims-hrm-connections-")
        self.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        self.path_patch = patch.object(database, "DB_FILE", str(Path(self.temp_dir.name) / "ims.sqlite3"))
        self.backend_patch.start()
        self.path_patch.start()
        database.init_db()
        self.db = database.get_db_connection()
        ensure_hrm_sqlite_schema(self.db)
        service.ensure_sqlite_schema(self.db)
        self.admin_id = int(self.db.execute("SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE vai_tro='Admin' LIMIT 1").fetchone()[0])
        self.department_id = int(self.db.execute("SELECT ma_phong_ban FROM PHONG_BAN LIMIT 1").fetchone()[0])

    def tearDown(self):
        self.db.close()
        self.path_patch.stop()
        self.backend_patch.stop()
        self.temp_dir.cleanup()

    def _add(self, name, port):
        return service.add_connection(
            self.db, name, f"http://127.0.0.1:{port}", "local-test-key-value-long-enough-123456789", self.admin_id,
        )

    def test_mysql_connection_schema_check_ignores_table_name_case(self):
        class MetadataResult:
            def fetchall(self):
                return [{"TABLE_NAME": name} for name in (
                    "hrm_connections", "hrm_active_connection", "hrm_connection_audit",
                )]

        class MetadataDatabase:
            def execute(self, statement):
                self.statement = statement
                return MetadataResult()

        db = MetadataDatabase()
        with patch.object(database, "DATABASE_BACKEND", "mysql"):
            self.assertTrue(service._tables_ready(db))

        self.assertIn("information_schema.TABLES", db.statement)

    def test_endpoint_allowlist_rejects_external_urls_and_other_ports(self):
        self.assertEqual(service.validate_endpoint("http://localhost:8100/"), "http://127.0.0.1:8100")
        for endpoint in ("https://127.0.0.1:8100", "http://example.test:8100", "http://127.0.0.1:8000", "http://127.0.0.1:8100/path"):
            with self.subTest(endpoint=endpoint), self.assertRaises(HTTPException):
                service.validate_endpoint(endpoint)

    def test_admin_only_connection_list(self):
        with self.assertRaises(HTTPException) as denied:
            get_connections(request_as("HR"), self.db)
        self.assertEqual(denied.exception.status_code, 403)

    def test_sources_have_isolated_external_ids_and_history_on_switch(self):
        with patch.object(service.secret_vault, "put", side_effect=lambda connection_id, key: f"dpapi:{connection_id}"), \
             patch.object(service.secret_vault, "get", return_value="local-test-key-value-long-enough-123456789"):
            source_a = self._add("Sandbox A", 8100)
            source_b = self._add("Sandbox B", 8101)
            provider_a, _ = service.make_provider(self.db, source_a["connection_id"])
            provider_b, _ = service.make_provider(self.db, source_b["connection_id"])
            self.assertNotEqual(provider_a.provider_id, provider_b.provider_id)

            for source, full_name in ((provider_a.provider_id, "Nguyễn An A"), (provider_b.provider_id, "Trần Bình B")):
                self.db.execute(
                    "INSERT INTO HRM_EMPLOYEE_DIRECTORY (provider_id, external_employee_key, external_employee_id, full_name, employment_status, ma_phong_ban) VALUES (?, 'nv001', 'NV001', ?, 'active', ?)",
                    (source, full_name, self.department_id),
                )
                self.db.execute(
                    "INSERT INTO HRM_DEPARTMENT_MAPPINGS (provider_id, external_department_key, external_department_code, ma_phong_ban) VALUES (?, 'data', 'DATA', ?)",
                    (source, self.department_id),
                )
            self.db.commit()
            self.assertEqual(list_directory(self.db, 1, 20, provider_a.provider_id)["items"][0]["full_name"], "Nguyễn An A")
            self.assertEqual(list_directory(self.db, 1, 20, provider_b.provider_id)["items"][0]["full_name"], "Trần Bình B")
            context_a = load_sync_context(self.db, provider_a.provider_id)
            context_b = load_sync_context(self.db, provider_b.provider_id)
            self.assertEqual(context_a["existing"]["nv001"]["full_name"], "Nguyễn An A")
            self.assertEqual(context_b["existing"]["nv001"]["full_name"], "Trần Bình B")

            persist_preview(self.db, self.admin_id, "a" * 64, provider_a.provider_id)
            persist_preview(self.db, self.admin_id, "b" * 64, provider_b.provider_id)
            check = AsyncMock(side_effect=lambda db, connection_id, require_connected=False: (None, {"state": "CONNECTED"}))
            with patch.object(service, "test_connection_id", check):
                await_result = __import__("asyncio").run(service.activate_connection(self.db, source_a["connection_id"], None, True, self.admin_id))
                self.assertEqual(await_result["active_connection_id"], source_a["connection_id"])
                switched = __import__("asyncio").run(service.activate_connection(self.db, source_b["connection_id"], source_a["connection_id"], True, self.admin_id))
            self.assertEqual(switched["previous_connection_id"], source_a["connection_id"])
            statuses = {row["provider_id"]: row["status"] for row in self.db.execute("SELECT provider_id, status FROM HRM_SYNC_PREVIEWS").fetchall()}
            self.assertEqual(statuses, {provider_a.provider_id: "STALE", provider_b.provider_id: "STALE"})
            items = service.list_connections(self.db)["items"]
            self.assertNotIn("local-test-key-value-long-enough-123456789", str(items))
            self.assertTrue(next(item for item in items if item["connection_id"] == source_b["connection_id"])["is_active"])


if __name__ == "__main__":
    unittest.main()
