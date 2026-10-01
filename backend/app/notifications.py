"""Write persistent in-app notifications as part of the caller's DB transaction."""
import sqlite3


def create_notification(
    db,
    user_id: int,
    title: str,
    message: str,
    *,
    notification_type: str = "general",
    reference_type: str | None = None,
    reference_id: str | int | None = None,
    email_recipient: str | None = None,
    email_deduplication_key: str | None = None,
    email_subject: str | None = None,
    email_template_type: str = "approval_result",
    email_reference_type: str = "notification",
    email_reference_id: str | int | None = None,
    email_body: str | None = None,
    email_max_attempts: int = 4,
) -> int:
    cursor = db.execute(
        """
        INSERT INTO THONG_BAO
            (ma_nguoi_dung, tieu_de, noi_dung, kenh, loai, reference_type, reference_id)
        VALUES (?, ?, ?, 'App', ?, ?, ?)
        """,
        (user_id, title, message, notification_type, reference_type,
         str(reference_id) if reference_id is not None else None),
    )
    notification_id = cursor.lastrowid
    if email_recipient and email_deduplication_key:
        try:
            db.execute(
                """
                INSERT INTO EMAIL_OUTBOX
                    (recipient_email, subject, body, template_type, reference_type,
                     reference_id, deduplication_key, status, max_retry)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    email_recipient, email_subject or title, email_body or message, email_template_type,
                    email_reference_type,
                    str(email_reference_id if email_reference_id is not None else notification_id),
                    email_deduplication_key, min(max(1, email_max_attempts), 4),
                ),
            )
        except sqlite3.IntegrityError:
            # The unique constraint is the concurrency-safe deduplication gate.
            # Suppress only a duplicate event key; other integrity errors must
            # abort the caller's transaction with its notification.
            duplicate = db.execute(
                "SELECT 1 FROM EMAIL_OUTBOX WHERE deduplication_key = ?",
                (email_deduplication_key,),
            ).fetchone()
            if not duplicate:
                raise
    return notification_id
