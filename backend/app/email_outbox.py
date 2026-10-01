"""SMTP delivery for the transactional email outbox."""
import asyncio
import logging
import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage

from .database import get_db_connection

logger = logging.getLogger(__name__)
_worker_task: asyncio.Task | None = None
_worker_stop: asyncio.Event | None = None
RETRY_DELAYS_SECONDS = (60, 300, 900)
MAX_EMAIL_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1
MAX_SMTP_TIMEOUT_SECONDS = 30


def _header_value(value, limit: int = 998) -> str:
    """Remove header control characters before passing values to the mail library."""
    normalized = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return normalized[:limit]


def _database_now(db) -> datetime:
    """Use the DB clock so due/stale comparisons match its DATETIME defaults."""
    value = db.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()["now"]
    return datetime.fromisoformat(str(value))


def _smtp_config():
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_USERNAME", "").strip()
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": sender,
        "use_ssl": os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"},
        "use_starttls": os.getenv("SMTP_USE_STARTTLS", "true").lower() in {"1", "true", "yes"},
        "timeout": max(1.0, min(float(os.getenv("SMTP_TIMEOUT_SECONDS", "15")), MAX_SMTP_TIMEOUT_SECONDS)),
    }


def _claim_one():
    db = get_db_connection()
    try:
        stale_before = (_database_now(db) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """UPDATE EMAIL_OUTBOX
               SET body=CASE WHEN template_type='temporary_credentials' THEN '' ELSE body END,
                   status='FAILED', last_error=COALESCE(last_error, 'Email retry limit reached.'),
                   next_retry_at=NULL, updated_at=CURRENT_TIMESTAMP
               WHERE status IN ('PENDING','RETRY')
                 AND retry_count >= CASE WHEN max_retry < 4 THEN max_retry ELSE 4 END"""
        )
        db.execute(
            """UPDATE EMAIL_OUTBOX
               SET body=CASE WHEN retry_count + 1 >= CASE WHEN max_retry < 4 THEN max_retry ELSE 4 END
                                AND template_type='temporary_credentials' THEN '' ELSE body END,
                   status=CASE WHEN retry_count + 1 >= CASE WHEN max_retry < 4 THEN max_retry ELSE 4 END
                               THEN 'FAILED' ELSE 'RETRY' END,
                   retry_count=retry_count + 1,
                   last_error='Previous email delivery attempt timed out.',
                   next_retry_at=CASE WHEN retry_count + 1 >= CASE WHEN max_retry < 4 THEN max_retry ELSE 4 END
                                     THEN NULL ELSE CURRENT_TIMESTAMP END,
                   updated_at=CURRENT_TIMESTAMP
               WHERE status='PROCESSING' AND updated_at < ?""",
            (stale_before,),
        )
        row = db.execute(
            """SELECT id, recipient_email, subject, body, retry_count, max_retry
               FROM EMAIL_OUTBOX
               WHERE status IN ('PENDING','RETRY')
                 AND (reference_type IS NULL OR reference_type <> 'internal_message')
                 AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
               ORDER BY created_at, id LIMIT 1"""
        ).fetchone()
        if not row:
            db.commit()
            return None
        claimed = db.execute(
            """UPDATE EMAIL_OUTBOX SET status='PROCESSING', updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status IN ('PENDING','RETRY')""",
            (row["id"],),
        )
        db.commit()
        return dict(row) if claimed.rowcount == 1 else None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _safe_error(exc: Exception) -> str:
    # Keep useful transport diagnostics without returning exception traces or credentials.
    message = " ".join(f"{type(exc).__name__}: {exc}".split())
    for secret in (os.getenv("SMTP_PASSWORD", ""), os.getenv("SMTP_USERNAME", "")):
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[:1000]


def _mark_sent(outbox_id: int):
    db = get_db_connection()
    try:
        db.execute(
            """UPDATE EMAIL_OUTBOX SET status='SENT', sent_at=CURRENT_TIMESTAMP,
                      body=CASE WHEN template_type='temporary_credentials' THEN '' ELSE body END,
                      next_retry_at=NULL, last_error=NULL, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='PROCESSING'""",
            (outbox_id,),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_failed_attempt(item, exc: Exception):
    retry_count = item["retry_count"] + 1
    failed = retry_count >= min(max(1, int(item["max_retry"] or MAX_EMAIL_ATTEMPTS)), MAX_EMAIL_ATTEMPTS)
    delay_seconds = RETRY_DELAYS_SECONDS[min(retry_count - 1, len(RETRY_DELAYS_SECONDS) - 1)]
    db = get_db_connection()
    try:
        next_retry = (_database_now(db) + timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """UPDATE EMAIL_OUTBOX
               SET status=?, retry_count=?, last_error=?, next_retry_at=?,
                   body=CASE WHEN ? AND template_type='temporary_credentials' THEN '' ELSE body END,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status='PROCESSING'""",
            ("FAILED" if failed else "RETRY", retry_count, _safe_error(exc),
             None if failed else next_retry, failed, item["id"]),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def process_one_email() -> bool:
    """Claim and deliver one message. Returns whether an item was claimed."""
    config = _smtp_config()
    if not config:
        return False
    item = _claim_one()
    if not item:
        return False

    try:
        message = EmailMessage()
        message["From"] = _header_value(config["sender"])
        message["To"] = _header_value(item["recipient_email"], 254)
        message["Subject"] = _header_value(item["subject"], 255)
        message.set_content(item["body"])
        if config["use_ssl"]:
            client = smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=config["timeout"],
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"])
        with client as smtp:
            if config["use_starttls"] and not config["use_ssl"]:
                smtp.starttls(context=ssl.create_default_context())
            if config["username"]:
                smtp.login(config["username"], config["password"])
            smtp.send_message(message)
        _mark_sent(item["id"])
        logger.info("Email outbox item %s sent", item["id"])
    except (smtplib.SMTPException, OSError, TimeoutError, ValueError) as exc:
        _mark_failed_attempt(item, exc)
        logger.warning("Email outbox item %s delivery failed (%s)", item["id"], type(exc).__name__)
    except Exception:
        # Database errors are surfaced so the worker logs them; delivery state is not guessed.
        logger.exception("Email outbox item %s processing failed", item["id"])
        raise
    return True


async def _run_worker(stop: asyncio.Event):
    interval = max(1.0, float(os.getenv("EMAIL_WORKER_INTERVAL_SECONDS", "5")))
    while not stop.is_set():
        try:
            processed = await asyncio.to_thread(process_one_email)
            if processed:
                continue
        except Exception:
            logger.exception("Email outbox worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def start_email_worker():
    global _worker_task, _worker_stop
    if _worker_task and not _worker_task.done():
        return
    if not _smtp_config():
        logger.info("SMTP is not configured; email outbox worker is idle")
    _worker_stop = asyncio.Event()
    _worker_task = asyncio.create_task(_run_worker(_worker_stop))


async def stop_email_worker():
    global _worker_task, _worker_stop
    if not _worker_task:
        return
    _worker_stop.set()
    try:
        await asyncio.wait_for(_worker_task, timeout=5)
    except asyncio.TimeoutError:
        _worker_task.cancel()
    _worker_task = None
    _worker_stop = None
