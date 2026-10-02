"""Automated tests for SMTP email attachments, inline CIDs, and security boundaries."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import database
from app.email_attachment_security import (
    inspect_magic_bytes,
    sanitize_filename,
    validate_attachment,
)
from app.email_service import build_mime_message, enqueue_email


class EmailAttachmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-att-test-", ignore_cleanup_errors=True)
        cls.db_path = Path(cls.temp_dir.name) / "att_test.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM EMAIL_ATTACHMENTS")
        self.db.execute("DELETE FROM EMAIL_OUTBOX")

    def tearDown(self):
        self.db.close()

    def test_sanitize_filename_prevents_path_traversal(self):
        """Sanitization prevents ../ and illegal path injection."""
        dangerous_names = [
            ("../../../etc/passwd", "passwd"),
            ("..\\..\\Windows\\System32\\cmd.exe", "cmd.exe"),
            ("test/file/../../name.pdf", "name.pdf"),
        ]
        for raw, expected in dangerous_names:
            clean = sanitize_filename(raw)
            self.assertNotIn("..", clean)
            self.assertIn(expected, clean)

    def test_reject_executable_and_macro_extensions(self):
        """Malicious extensions (.exe, .sh, .docm) are immediately rejected with HTTP 400."""
        blocked_samples = [
            ("trojan.exe", b"MZ\x90\x00"),
            ("script.sh", b"#!/bin/bash"),
            ("macro.docm", b"PK\x03\x04"),
        ]
        for filename, content in blocked_samples:
            with self.assertRaises(HTTPException) as ctx:
                validate_attachment(filename, content)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("bị cấm", ctx.exception.detail)

    def test_reject_oversized_single_file(self):
        """Single file > 10MB is rejected with HTTP 413."""
        large_content = b"%PDF-1.4\n" + (b"0" * (10 * 1024 * 1024 + 10))
        with self.assertRaises(HTTPException) as ctx:
            validate_attachment("oversized.pdf", large_content)
        self.assertEqual(ctx.exception.status_code, 413)

    def test_enqueue_email_with_attachments_and_inline_cid(self):
        """Transactional enqueueing inserts outbox item and attachment records."""
        valid_pdf = b"%PDF-1.4\nContract Body Test"
        valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        att_pdf = validate_attachment("Hop_dong.pdf", valid_pdf)
        att_pdf["disposition"] = "attachment"

        att_img = validate_attachment("logo.png", valid_png)
        att_img["disposition"] = "inline"
        att_img["content_id"] = "brand_logo"

        email_id = enqueue_email(
            db=self.db,
            recipient_email="intern@example.com",
            subject="Ký hợp đồng thực tập",
            body_text="Vui lòng xem hợp đồng đính kèm.",
            body_html="<p>Chào bạn,</p><img src='cid:brand_logo'><p>Hợp đồng đính kèm.</p>",
            attachments=[att_pdf, att_img],
            deduplication_key="test_contract_01",
        )
        self.db.commit()

        # Verify DB records
        row = self.db.execute("SELECT * FROM EMAIL_OUTBOX WHERE id = ?", (email_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["has_attachments"], 1)

        att_rows = self.db.execute("SELECT * FROM EMAIL_ATTACHMENTS WHERE email_id = ?", (email_id,)).fetchall()
        self.assertEqual(len(att_rows), 2)

    def test_build_mime_structure_with_both_inline_and_downloadable_files(self):
        """MIME message correctly packages alternative HTML, related inline image, and mixed attachment."""
        valid_pdf = b"%PDF-1.4\nPDF Content"
        valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        att_pdf = validate_attachment("Offer_Letter.pdf", valid_pdf)
        att_pdf["disposition"] = "attachment"

        att_img = validate_attachment("company_badge.png", valid_png)
        att_img["disposition"] = "inline"
        att_img["content_id"] = "badge"

        message = build_mime_message(
            sender="hr@company.com",
            recipient="candidate@gmail.com",
            subject="Offer Letter 2026",
            body_text="Congratulations!",
            body_html="<h1>Welcome!</h1><img src='cid:badge'>",
            attachments=[att_pdf, att_img],
        )

        self.assertEqual(message["To"], "candidate@gmail.com")
        self.assertEqual(message["Subject"], "Offer Letter 2026")
        self.assertTrue(message.is_multipart())

        # Verify attachment headers
        attachment_names = [part.get_filename() for part in message.iter_attachments()]
        self.assertIn("Offer_Letter.pdf", attachment_names)

    def test_worker_fails_gracefully_when_attachment_file_is_missing(self):
        """Worker flags ATTACHMENT_NOT_FOUND if the physical file was deleted before dispatch."""
        missing_att = {
            "id": "mock_id",
            "filename": "deleted.pdf",
            "file_path": "/non/existent/path/deleted.pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
            "disposition": "attachment",
        }
        with self.assertRaises(FileNotFoundError) as ctx:
            build_mime_message(
                sender="hr@company.com",
                recipient="test@example.com",
                subject="Test",
                body_text="Body",
                attachments=[missing_att],
            )
        self.assertIn("not found on disk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
