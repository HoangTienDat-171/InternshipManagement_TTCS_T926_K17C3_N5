"""High-level Email Dispatcher supporting Outbox queueing and Direct sending with attachments."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from .email_outbox import _header_value, _smtp_config


def _read_attachment_bytes(file_path: str) -> bytes:
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Attachment file not found on disk: {file_path}")
    return p.read_bytes()


def build_mime_message(
    sender: str,
    recipient: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[dict] | None = None,
) -> EmailMessage:
    """Builds RFC-5322 compliant EmailMessage supporting mixed attachments and inline CIDs."""
    message = EmailMessage()
    message["From"] = _header_value(sender)
    message["To"] = _header_value(recipient, 254)
    message["Subject"] = _header_value(subject, 255)

    # Plain text content baseline
    message.set_content(body_text)

    # Attach alternative HTML and inline images
    if body_html:
        message.add_alternative(body_html, subtype="html")
        html_part = message.get_payload()[-1]

        # Handle inline images (CID)
        if attachments:
            for att in attachments:
                if att.get("disposition") == "inline" and att.get("content_id"):
                    raw_data = _read_attachment_bytes(att["file_path"])
                    mime_parts = att["mime_type"].split("/", 1)
                    maintype = mime_parts[0]
                    subtype = mime_parts[1] if len(mime_parts) > 1 else "octet-stream"
                    cid_val = att["content_id"].strip("<>")
                    html_part.add_related(
                        raw_data,
                        maintype=maintype,
                        subtype=subtype,
                        cid=f"<{cid_val}>"
                    )

    # Handle regular downloadable attachments
    if attachments:
        for att in attachments:
            if att.get("disposition", "attachment") == "attachment":
                raw_data = _read_attachment_bytes(att["file_path"])
                mime_parts = att["mime_type"].split("/", 1)
                maintype = mime_parts[0]
                subtype = mime_parts[1] if len(mime_parts) > 1 else "octet-stream"
                message.add_attachment(
                    raw_data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=att["filename"],
                )

    return message


def enqueue_email(
    db,
    recipient_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[dict] | None = None,
    template_type: str = "general",
    reference_type: str | None = None,
    reference_id: str | int | None = None,
    deduplication_key: str | None = None,
    max_retry: int = 4,
    force_send: bool = False,
) -> int:
    import uuid
    from .email_deduplication import (
        compute_email_dedup_hash,
        check_and_acquire_dedup_lock,
        update_dedup_lock_outbox_id,
        DuplicateEmailSuppressedError,
    )

    norm_recipient = recipient_email.strip().lower()
    dedup_hash = compute_email_dedup_hash(
        recipient_email=norm_recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        template_type=template_type,
        attachments=attachments,
    )

    allowed, status_msg, orig_id = check_and_acquire_dedup_lock(
        db=db,
        recipient_email=norm_recipient,
        dedup_hash=dedup_hash,
        force_send=force_send,
    )
    if not allowed:
        raise DuplicateEmailSuppressedError(
            recipient=norm_recipient,
            dedup_hash=dedup_hash,
            original_id=orig_id,
        )

    dedup_key = deduplication_key or f"outbox:{norm_recipient}:{uuid.uuid4().hex}"
    has_att = 1 if attachments else 0
    cursor = db.execute(
        """
        INSERT INTO EMAIL_OUTBOX (
            recipient_email, subject, body, body_html, has_attachments,
            template_type, reference_type, reference_id, deduplication_key,
            dedup_hash, status, max_retry
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """,
        (
            norm_recipient, subject, body_text, body_html,
            has_att, template_type,
            reference_type, str(reference_id) if reference_id is not None else None,
            dedup_key, dedup_hash, min(max(1, max_retry), 4)
        )
    )
    email_id = cursor.lastrowid
    update_dedup_lock_outbox_id(db, norm_recipient, dedup_hash, email_id)

    if attachments:
        total_size = sum(att["file_size"] for att in attachments)
        if total_size > 25 * 1024 * 1024:
            raise ValueError(f"Tổng dung lượng tệp đính kèm ({total_size} bytes) vượt quá giới hạn 25MB.")

        for att in attachments:
            db.execute(
                """
                INSERT INTO EMAIL_ATTACHMENTS (
                    id, email_id, filename, file_path, mime_type,
                    file_size, disposition, content_id, checksum_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    att["id"], email_id, att["filename"], att["file_path"],
                    att["mime_type"], att["file_size"],
                    att.get("disposition", "attachment"),
                    att.get("content_id"), att.get("checksum_sha256")
                )
            )
    return email_id


def send_email_direct(
    recipient: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[dict] | None = None,
) -> bool:
    """Direct, synchronous delivery bypasses outbox table (for high-priority immediate alerts)."""
    config = _smtp_config()
    if not config:
        raise RuntimeError("SMTP configuration is not set.")

    total_bytes = sum(att.get("file_size", 0) for att in (attachments or []))
    dynamic_timeout = max(config["timeout"], min(60.0, 15.0 + total_bytes / (256 * 1024)))

    message = build_mime_message(
        sender=config["sender"],
        recipient=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )

    if config["use_ssl"]:
        client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=dynamic_timeout, context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(config["host"], config["port"], timeout=dynamic_timeout)

    with client as smtp:
        if config["use_starttls"] and not config["use_ssl"]:
            smtp.starttls(context=ssl.create_default_context())
        if config["username"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)
    return True
