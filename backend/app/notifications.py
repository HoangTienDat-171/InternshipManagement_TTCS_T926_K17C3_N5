"""Write persistent in-app notifications as part of the caller's DB transaction."""


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
        db.execute(
            """
            INSERT OR IGNORE INTO EMAIL_OUTBOX
                (recipient_email, subject, body, template_type, reference_type,
                 reference_id, deduplication_key, status, max_retry)
            VALUES (?, ?, ?, 'approval_result', 'notification', ?, ?, 'PENDING', 5)
            """,
            (email_recipient, title, message, str(notification_id), email_deduplication_key),
        )
    return notification_id
