import logging
import sqlite3

logger = logging.getLogger(__name__)


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
    email_force_send: bool = False,
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
        from .email_deduplication import (
            compute_email_dedup_hash,
            check_and_acquire_dedup_lock,
            update_dedup_lock_outbox_id,
        )

        norm_recipient = email_recipient.strip().lower()
        sub = email_subject or title
        body = email_body or message
        dedup_hash = compute_email_dedup_hash(
            recipient_email=norm_recipient,
            subject=sub,
            body_text=body,
            template_type=email_template_type,
        )

        allowed, status_msg, orig_id = check_and_acquire_dedup_lock(
            db=db,
            recipient_email=norm_recipient,
            dedup_hash=dedup_hash,
            force_send=email_force_send,
        )

        if not allowed:
            logger.warning(
                "DUPLICATE_EMAIL_SUPPRESSED: Skipping outbox queue for notification to '%s' (hash=%s, original_id=%s)",
                norm_recipient, dedup_hash, orig_id
            )
            return notification_id

        try:
            # Check if dedup_hash column is supported in current table schema
            try:
                outbox_cursor = db.execute(
                    """
                    INSERT INTO EMAIL_OUTBOX
                        (recipient_email, subject, body, template_type, reference_type,
                         reference_id, deduplication_key, dedup_hash, status, max_retry)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                    """,
                    (
                        norm_recipient, sub, body, email_template_type,
                        email_reference_type,
                        str(email_reference_id if email_reference_id is not None else notification_id),
                        email_deduplication_key, dedup_hash, min(max(1, email_max_attempts), 4),
                    ),
                )
            except Exception as col_err:
                if "has no column named dedup_hash" in str(col_err) or "Unknown column 'dedup_hash'" in str(col_err):
                    outbox_cursor = db.execute(
                        """
                        INSERT INTO EMAIL_OUTBOX
                            (recipient_email, subject, body, template_type, reference_type,
                             reference_id, deduplication_key, status, max_retry)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                        """,
                        (
                            norm_recipient, sub, body, email_template_type,
                            email_reference_type,
                            str(email_reference_id if email_reference_id is not None else notification_id),
                            email_deduplication_key, min(max(1, email_max_attempts), 4),
                        ),
                    )
                else:
                    raise
            outbox_id = outbox_cursor.lastrowid
            update_dedup_lock_outbox_id(db, norm_recipient, dedup_hash, outbox_id)
        except sqlite3.IntegrityError:
            # The unique constraint is the concurrency-safe deduplication gate.
            duplicate = db.execute(
                "SELECT 1 FROM EMAIL_OUTBOX WHERE deduplication_key = ?",
                (email_deduplication_key,),
            ).fetchone()
            if not duplicate:
                raise
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                pass
            else:
                raise
    return notification_id
