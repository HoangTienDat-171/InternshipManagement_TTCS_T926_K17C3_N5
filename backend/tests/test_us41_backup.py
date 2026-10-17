import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import audit_service, backup_service, database


class BackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ims-us41-test-")
        cls.root = Path(cls.temp.name)
        cls.db_path = cls.root / "backup-test.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        cls.backup_dir = cls.root / "private-backups"
        cls.backup_env_previous = os.environ.get("IMS_BACKUP_DIRECTORY")
        os.environ["IMS_BACKUP_DIRECTORY"] = str(cls.backup_dir)
        database.init_db()
        db = database.get_db_connection()
        audit_service.create_sqlite_schema(db)
        db.commit()
        cls.admin = dict(db.execute(
            "SELECT ma_nguoi_dung, ho_ten, vai_tro FROM NGUOI_DUNG WHERE vai_tro='Admin' ORDER BY ma_nguoi_dung LIMIT 1"
        ).fetchone())
        db.close()
        cls.upload_root = cls.db_path.parent / "uploads"
        cls.upload_root.mkdir()
        cls.upload = cls.upload_root / "test-document.txt"
        cls.upload.write_text("US41 test upload", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        if cls.backup_env_previous is None:
            os.environ.pop("IMS_BACKUP_DIRECTORY", None)
        else:
            os.environ["IMS_BACKUP_DIRECTORY"] = cls.backup_env_previous
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp.cleanup()

    def test_backup_archive_checksum_uploads_and_isolated_restore_counts(self):
        result = backup_service.create_backup(actor=self.admin)
        archive_path = self.backup_dir / result["file_name"]
        self.assertTrue(archive_path.is_file())
        self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), result["checksum_sha256"])
        self.assertEqual(backup_service.verify_backup(result["id"], actor=self.admin)["checksum_status"], "VALID")

        restore_dir = self.root / "restore-drill"
        restore_dir.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            archive.extract("database.sqlite3", restore_dir)
            archive.extract("uploads/test-document.txt", restore_dir)
        restored = database.sqlite3.connect(restore_dir / "database.sqlite3")
        try:
            for table, expected in manifest["table_row_counts"].items():
                quoted = table.replace('"', '""')
                actual = restored.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
                self.assertEqual(actual, expected, table)
        finally:
            restored.close()
        restored_upload = restore_dir / "uploads" / "test-document.txt"
        self.assertEqual(hashlib.sha256(restored_upload.read_bytes()).hexdigest(), manifest["upload_files"][0]["sha256"])
        self.assertEqual(result["manifest"]["upload_file_count"], 1)

    def test_low_disk_failure_is_persisted_and_audited(self):
        with patch.object(backup_service.shutil, "disk_usage", return_value=SimpleNamespace(free=0)):
            with self.assertRaises(backup_service.BackupError) as context:
                backup_service.create_backup(actor=self.admin)
        self.assertEqual(context.exception.code, "INSUFFICIENT_DISK_SPACE")
        db = database.get_db_connection()
        try:
            job = db.execute("SELECT status, error_code FROM IMS_BACKUP_JOBS ORDER BY id DESC LIMIT 1").fetchone()
            event = db.execute("SELECT outcome, action FROM IMS_AUDIT_LOG ORDER BY event_id DESC LIMIT 1").fetchone()
            self.assertEqual((job["status"], job["error_code"]), ("FAILED", "INSUFFICIENT_DISK_SPACE"))
            self.assertEqual((event["outcome"], event["action"]), ("FAILURE", "BACKUP_FAILED"))
        finally:
            db.close()

    def test_retention_marks_artifact_expired_before_file_removal(self):
        first = backup_service.create_backup(actor=self.admin)
        second = backup_service.create_backup(actor=self.admin)
        first_path = self.backup_dir / first["file_name"]
        self.assertTrue(first_path.exists())

        db = database.get_db_connection()
        try:
            # Simulate a Windows file lock: the failed unlink must leave a private
            # extra artifact but must not report it as a live successful backup.
            original_unlink = Path.unlink

            def fail_first_archive_unlink(path, *args, **kwargs):
                if path == first_path:
                    raise PermissionError("locked for test")
                return original_unlink(path, *args, **kwargs)

            with self.assertLogs(backup_service.logger, level="ERROR"):
                with patch.object(Path, "unlink", fail_first_archive_unlink):
                    backup_service._apply_retention(db, 1)
            rows = db.execute(
                "SELECT id, status FROM IMS_BACKUP_JOBS WHERE id IN (?, ?) ORDER BY id",
                (first["id"], second["id"]),
            ).fetchall()
            self.assertEqual([row["status"] for row in rows], ["EXPIRED", "SUCCESS"])
            self.assertTrue(first_path.exists())
        finally:
            db.close()
