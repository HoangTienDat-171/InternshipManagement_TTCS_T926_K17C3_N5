"""Email deduplication, content fingerprinting, and concurrency-safe rate-limiting locks."""
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 600  # 10 minutes


class DuplicateEmailSuppressedError(Exception):
    """Raised when an outgoing email is identified as duplicate within cooldown window."""
    def __init__(self, recipient: str, dedup_hash: str, original_id: int | None = None, message: str | None = None):
        self.recipient = recipient
        self.dedup_hash = dedup_hash
        self.original_id = original_id
        window_minutes = get_dedup_window_seconds() // 60
        self.message = message or (
            f"DUPLICATE_EMAIL_SUPPRESSED: Email tương tự đã được gửi hoặc đang được xử lý trong vòng {window_minutes} phút."
        )
        super().__init__(self.message)


def get_dedup_window_seconds() -> int:
    """Return cooldown period in seconds from environment variable or default 600s."""
    if os.getenv("EMAIL_DEDUP_WINDOW_SECONDS"):
        try:
            return max(1, int(os.environ["EMAIL_DEDUP_WINDOW_SECONDS"]))
        except ValueError:
            pass
    if os.getenv("EMAIL_DEDUP_COOLDOWN_MINUTES"):
        try:
            return max(1, int(os.environ["EMAIL_DEDUP_COOLDOWN_MINUTES"]) * 60)
        except ValueError:
            pass
    return DEFAULT_COOLDOWN_SECONDS


def _normalize_text(text: str | None) -> str:
    """Strip, clean HTML tags, lower, and collapse whitespaces for deterministic comparison."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", str(text))
    return " ".join(clean.strip().lower().split())


def compute_email_dedup_hash(
    recipient_email: str,
    subject: str,
    body_text: str = "",
    body_html: str | None = None,
    template_type: str | None = None,
    attachments: list[dict] | None = None,
) -> str:
    """
    Deterministic Fingerprinting Formula:
    SHA256(recipient_email + "|" + trimmed_subject + "|" + normalized_body_or_template_id + "|" + attachment_hashes)
    """
    norm_recipient = (recipient_email or "").strip().lower()
    norm_subject = (subject or "").strip()

    # Normalize body or template
    norm_body = _normalize_text(body_text)
    if not norm_body and body_html:
        norm_body = _normalize_text(body_html)
    if not norm_body and template_type:
        norm_body = f"template:{template_type.strip().lower()}"

    # Calculate attachment hashes sorted deterministically
    att_hashes = []
    if attachments:
        for att in sorted(attachments, key=lambda x: str(x.get("filename", "")).lower()):
            checksum = att.get("checksum_sha256")
            if not checksum and att.get("file_path") and os.path.isfile(att["file_path"]):
                try:
                    with open(att["file_path"], "rb") as f:
                        checksum = hashlib.sha256(f.read()).hexdigest()
                except Exception:
                    checksum = ""
            if not checksum:
                # Fallback to filename + filesize
                name = str(att.get("filename", "")).strip().lower()
                size = str(att.get("file_size", 0))
                checksum = hashlib.sha256(f"{name}:{size}".encode("utf-8")).hexdigest()
            att_hashes.append(checksum)
    att_str = ",".join(att_hashes)

    fingerprint = f"{norm_recipient}|{norm_subject}|{norm_body}|{att_str}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def _get_db_now(db) -> datetime:
    """Use the DB clock so comparisons match its DATETIME defaults."""
    row = db.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()
    val = row["now"]
    return datetime.fromisoformat(str(val))


def check_and_acquire_dedup_lock(
    db,
    recipient_email: str,
    dedup_hash: str,
    window_seconds: int | None = None,
    force_send: bool = False,
    outbox_id: int | None = None,
) -> tuple[bool, str, int | None]:
    """
    Checks if identical email is within cooldown window.
    Acquires atomic lock if clear.
    Returns: (is_allowed: bool, status_msg: str, original_outbox_id: int | None)
    """
    if force_send:
        logger.info(
            "Email deduplication bypassed for recipient '%s' (force_send=True)",
            recipient_email
        )
        return True, "FORCE_SEND_OVERRIDE", None

    if window_seconds is None:
        window_seconds = get_dedup_window_seconds()

    norm_recipient = recipient_email.strip().lower()

    # Optional Redis check if configured (Option B)
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            r = redis.from_url(redis_url)
            redis_key = f"email:dedup:{norm_recipient}:{dedup_hash}"
            acquired = r.set(redis_key, "1", nx=True, ex=window_seconds)
            if not acquired:
                logger.warning(
                    "DUPLICATE_EMAIL_SUPPRESSED (Redis): Email to '%s' (hash=%s) suppressed within %ss cooldown",
                    norm_recipient, dedup_hash, window_seconds
                )
                return False, "DUPLICATE_EMAIL_SUPPRESSED", None
        except Exception as e:
            logger.warning("Redis check failed (%s); falling back to DB lock", e)

    # Database-level Lock & Verification (Option A)
    # Schema setup and migrations create this table. Avoid runtime DDL here:
    # MySQL implicitly commits around CREATE TABLE, breaking the caller's transaction.
    db_now = _get_db_now(db)
    expires_at = (db_now + timedelta(seconds=window_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    now_str = db_now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Check existing lock in EMAIL_DEDUP_LOCKS
    existing_lock = db.execute(
        """SELECT recipient_email, dedup_hash, expires_at, last_outbox_id
           FROM EMAIL_DEDUP_LOCKS
           WHERE recipient_email = ? AND dedup_hash = ?""",
        (norm_recipient, dedup_hash),
    ).fetchone()

    if existing_lock:
        lock_expires = str(existing_lock["expires_at"])
        if lock_expires > now_str:
            orig_id = existing_lock["last_outbox_id"]
            logger.warning(
                "DUPLICATE_EMAIL_SUPPRESSED: Email to '%s' (hash=%s, original_outbox_id=%s) blocked. Cooldown active until %s",
                norm_recipient, dedup_hash, orig_id, lock_expires
            )
            return False, "DUPLICATE_EMAIL_SUPPRESSED", orig_id
        else:
            # Lock has expired; re-acquire by updating expiration
            refreshed = db.execute(
                """UPDATE EMAIL_DEDUP_LOCKS
                   SET expires_at = ?, created_at = CURRENT_TIMESTAMP, last_outbox_id = ?
                   WHERE recipient_email = ? AND dedup_hash = ? AND expires_at <= ?""",
                (expires_at, outbox_id, norm_recipient, dedup_hash, now_str),
            )
            if refreshed.rowcount != 1:
                # Another request refreshed this expired lock while this one waited.
                return False, "DUPLICATE_EMAIL_SUPPRESSED", existing_lock["last_outbox_id"]
            return True, "ACQUIRED_LOCK", None

    # 2. Check EMAIL_OUTBOX for any recent message within cooldown window
    cutoff = (db_now - timedelta(seconds=window_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    recent_outbox = None
    try:
        recent_outbox = db.execute(
            """SELECT id, status, created_at FROM EMAIL_OUTBOX
               WHERE recipient_email = ? AND dedup_hash = ?
                 AND status IN ('PENDING', 'PROCESSING', 'SENT', 'RETRY')
                 AND created_at >= ?
               ORDER BY id DESC LIMIT 1""",
            (norm_recipient, dedup_hash, cutoff),
        ).fetchone()
    except Exception as e:
        if "no such column: dedup_hash" in str(e).lower() or "unknown column 'dedup_hash'" in str(e).lower():
            recent_outbox = None
        else:
            raise

    if recent_outbox:
        logger.warning(
            "DUPLICATE_EMAIL_SUPPRESSED (Outbox): Email to '%s' (hash=%s, outbox_id=%s, status=%s) blocked.",
            norm_recipient, dedup_hash, recent_outbox["id"], recent_outbox["status"]
        )
        # Store in lock table to cache suppression
        try:
            db.execute(
                """INSERT INTO EMAIL_DEDUP_LOCKS
                   (recipient_email, dedup_hash, expires_at, last_outbox_id)
                   VALUES (?, ?, ?, ?)""",
                (norm_recipient, dedup_hash, expires_at, recent_outbox["id"]),
            )
        except Exception:
            pass
        return False, "DUPLICATE_EMAIL_SUPPRESSED", recent_outbox["id"]

    # 3. Atomic insertion into EMAIL_DEDUP_LOCKS (Guarantees race-condition safety)
    try:
        db.execute(
            """INSERT INTO EMAIL_DEDUP_LOCKS
               (recipient_email, dedup_hash, expires_at, last_outbox_id)
               VALUES (?, ?, ?, ?)""",
            (norm_recipient, dedup_hash, expires_at, outbox_id),
        )
        return True, "ACQUIRED_LOCK", None
    except Exception as exc:
        # Concurrent insert at exact same millisecond hit primary key constraint
        logger.warning(
            "DUPLICATE_EMAIL_SUPPRESSED (Race Condition Blocked): Concurrent send to '%s' (hash=%s): %s",
            norm_recipient, dedup_hash, exc
        )
        return False, "DUPLICATE_EMAIL_SUPPRESSED", None


def update_dedup_lock_outbox_id(db, recipient_email: str, dedup_hash: str, outbox_id: int):
    """Link the created outbox ID with the active deduplication lock for audit trail."""
    try:
        db.execute(
            """UPDATE EMAIL_DEDUP_LOCKS SET last_outbox_id = ?
               WHERE recipient_email = ? AND dedup_hash = ?""",
            (outbox_id, recipient_email.strip().lower(), dedup_hash),
        )
    except Exception as e:
        logger.debug("Failed to link outbox_id to dedup lock: %s", e)
