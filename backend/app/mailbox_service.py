"""Mailbox business rules, RBAC and transactional message delivery."""
import re
from html import unescape
from math import ceil

from fastapi import HTTPException, status

from .mailbox_content import render_template, sanitize_html
from .mailbox_repository import (
    add_recipients, create_message, create_thread, get_user, get_users,
    list_messages as repository_list_messages, mentor_is_assigned_to,
    message_access, message_recipients, thread_accessible, thread_messages,
)
from .notifications import create_notification


CATEGORIES = {
    "XIN_HO_TRO", "XIN_XET_DUYET", "THAC_MAC_LICH_LAM_VIEC",
    "BO_SUNG_HO_SO", "THONG_BAO_CHUNG", "KET_QUA_XET_DUYET",
}
MANAGER_ROLES = {"Admin", "HR"}


def _plain_text(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", value)).split())


def _can_send_to(db, sender, receiver) -> bool:
    if receiver["ma_nguoi_dung"] == sender["ma_nguoi_dung"] or receiver["trang_thai"] != "HoatDong":
        return False
    role = sender["vai_tro"]
    if role in MANAGER_ROLES:
        return True
    if role == "Mentor":
        return receiver["vai_tro"] == "ThucTapSinh" and mentor_is_assigned_to(
            db, sender["ma_nguoi_dung"], receiver["ma_nguoi_dung"],
        )
    if role == "ThucTapSinh":
        if receiver["vai_tro"] in MANAGER_ROLES:
            return True
        return receiver["vai_tro"] == "Mentor" and mentor_is_assigned_to(
            db, receiver["ma_nguoi_dung"], sender["ma_nguoi_dung"],
        )
    return False


def search_recipients(db, sender, query: str, limit: int = 20):
    query = query.strip().lower()
    like = f"%{query}%"
    candidates = db.execute("""
        SELECT ma_nguoi_dung, ho_ten, email, vai_tro, trang_thai, ma_phong_ban
        FROM NGUOI_DUNG
        WHERE trang_thai='HoatDong' AND ma_nguoi_dung<>?
          AND (LOWER(ho_ten) LIKE ? OR LOWER(email) LIKE ?)
        ORDER BY ho_ten LIMIT ?
    """, (sender["ma_nguoi_dung"], like, like, min(limit * 5, 100))).fetchall()
    return [dict(row) for row in candidates if _can_send_to(db, sender, row)][:limit]


def recipient_groups(db, sender):
    groups = []
    if sender["vai_tro"] in MANAGER_ROLES:
        programs = db.execute("""
            SELECT c.ma_chuong_trinh, c.ten_ct,
                   COUNT(DISTINCT h.ma_nguoi_dung) AS member_count
            FROM CHUONG_TRINH_THUC_TAP c
            LEFT JOIN UNG_TUYEN_CHUONG_TRINH a
              ON a.ma_chuong_trinh=c.ma_chuong_trinh AND a.trang_thai='DaDuyet'
            LEFT JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=a.ma_ho_so
            GROUP BY c.ma_chuong_trinh, c.ten_ct ORDER BY c.ten_ct
        """).fetchall()
        groups.extend({
            "key": f"PROGRAM:{row['ma_chuong_trinh']}",
            "label": f"Tất cả TTS - {row['ten_ct']}",
            "memberCount": row["member_count"],
            "type": "program",
        } for row in programs if row["member_count"])
        mentors = db.execute("""
            SELECT u.ma_nguoi_dung, u.ho_ten, COUNT(p.ma_phan_cong) AS member_count
            FROM NGUOI_DUNG u
            JOIN PHAN_CONG_MENTOR_TTS p ON p.ma_nguoi_dung_mentor=u.ma_nguoi_dung
            WHERE u.vai_tro='Mentor' AND u.trang_thai='HoatDong'
            GROUP BY u.ma_nguoi_dung, u.ho_ten ORDER BY u.ho_ten
        """).fetchall()
        groups.extend({
            "key": f"MENTOR_INTERNS:{row['ma_nguoi_dung']}",
            "label": f"TTS của Mentor {row['ho_ten']}",
            "memberCount": row["member_count"],
            "type": "mentor",
        } for row in mentors)
    elif sender["vai_tro"] == "Mentor":
        count = db.execute("""
            SELECT COUNT(*) AS total FROM PHAN_CONG_MENTOR_TTS
            WHERE ma_nguoi_dung_mentor=?
        """, (sender["ma_nguoi_dung"],)).fetchone()["total"]
        if count:
            groups.append({
                "key": f"MENTOR_INTERNS:{sender['ma_nguoi_dung']}",
                "label": "Nhóm thực tập sinh của tôi", "memberCount": count, "type": "mentor",
            })
    return groups


def _expand_group(db, sender, key: str):
    kind, separator, raw_id = key.partition(":")
    if not separator or not raw_id.isdigit():
        raise HTTPException(status_code=422, detail="Nhóm người nhận không hợp lệ.")
    entity_id = int(raw_id)
    if kind == "PROGRAM" and sender["vai_tro"] in MANAGER_ROLES:
        rows = db.execute("""
            SELECT DISTINCT h.ma_nguoi_dung
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=a.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
            WHERE a.ma_chuong_trinh=? AND a.trang_thai='DaDuyet'
              AND u.trang_thai='HoatDong'
        """, (entity_id,)).fetchall()
        return [row["ma_nguoi_dung"] for row in rows], entity_id
    if kind == "MENTOR_INTERNS" and (
        sender["vai_tro"] in MANAGER_ROLES or
        (sender["vai_tro"] == "Mentor" and entity_id == sender["ma_nguoi_dung"])
    ):
        rows = db.execute("""
            SELECT h.ma_nguoi_dung FROM PHAN_CONG_MENTOR_TTS p
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=p.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=h.ma_nguoi_dung
            WHERE p.ma_nguoi_dung_mentor=? AND u.trang_thai='HoatDong'
        """, (entity_id,)).fetchall()
        return [row["ma_nguoi_dung"] for row in rows], None
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không được gửi tới nhóm này.")


def _resolve_recipients(db, sender, receiver_ids: list[int], group_keys: list[str]):
    resolved = set(receiver_ids)
    program_id = None
    for key in group_keys:
        members, group_program_id = _expand_group(db, sender, key)
        resolved.update(members)
        program_id = program_id or group_program_id
    if not resolved:
        raise HTTPException(status_code=422, detail="Vui lòng chọn ít nhất một người nhận.")
    if len(resolved) > 100:
        raise HTTPException(status_code=422, detail="Mỗi lần gửi tối đa 100 người nhận.")
    users = get_users(db, sorted(resolved))
    if len(users) != len(resolved) or any(not _can_send_to(db, sender, user) for user in users):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Danh sách người nhận có tài khoản ngoài phạm vi được phép.")
    return [dict(user) for user in users], program_id


def _template_context(db, recipient, program_id: int | None):
    context = {
        "ten_tts": recipient["ho_ten"] if recipient["vai_tro"] == "ThucTapSinh" else recipient["ho_ten"],
        "email_tts": recipient["email"], "ten_chuong_trinh": "", "ten_mentor": "",
        "ngay_bat_dau": "", "ngay_ket_thuc": "", "ngay_het_han": "",
    }
    if program_id:
        program = db.execute("""
            SELECT ten_ct, ngay_bat_dau, ngay_ket_thuc FROM CHUONG_TRINH_THUC_TAP
            WHERE ma_chuong_trinh=?
        """, (program_id,)).fetchone()
        if program:
            context.update({
                "ten_chuong_trinh": program["ten_ct"],
                "ngay_bat_dau": program["ngay_bat_dau"],
                "ngay_ket_thuc": program["ngay_ket_thuc"],
                "ngay_het_han": program["ngay_ket_thuc"],
            })
    if recipient["vai_tro"] == "ThucTapSinh":
        mentor = db.execute("""
            SELECT u.ho_ten FROM PHAN_CONG_MENTOR_TTS p
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so=p.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung=p.ma_nguoi_dung_mentor
            WHERE h.ma_nguoi_dung=?
        """, (recipient["ma_nguoi_dung"],)).fetchone()
        if mentor:
            context["ten_mentor"] = mentor["ho_ten"]
    return context


def _enqueue_delivery(db, sender, recipients, message_id: int, subject: str,
                      content_html: str, category: str, send_email: bool):
    summary = _plain_text(content_html)[:500]
    for recipient in recipients:
        create_notification(
            db, recipient["ma_nguoi_dung"], subject, summary,
            notification_type="mailbox_message", reference_type="internal_message",
            reference_id=message_id,
            email_recipient=recipient["email"] if send_email else None,
            email_deduplication_key=(
                f"mailbox:{message_id}:{recipient['ma_nguoi_dung']}" if send_email else None
            ),
            email_template_type=category.lower(), email_reference_type="internal_message",
            email_reference_id=message_id, email_body=summary,
        )


def send_message(db, sender, payload):
    recipients, program_id = _resolve_recipients(
        db, sender, payload.receiverIds, payload.groupKeys,
    )
    sanitized = sanitize_html(payload.contentHtml)
    if not _plain_text(sanitized):
        raise HTTPException(status_code=422, detail="Nội dung thư không hợp lệ.")
    template = None
    if payload.templateId is not None:
        if sender["vai_tro"] not in MANAGER_ROLES:
            raise HTTPException(status_code=403, detail="Bạn không được sử dụng mẫu thư quản trị.")
        template = db.execute("""
            SELECT id, subject, body_html, category FROM EMAIL_TEMPLATES
            WHERE id=? AND is_active=1 AND deleted_at IS NULL
        """, (payload.templateId,)).fetchone()
        if not template:
            raise HTTPException(status_code=404, detail="Không tìm thấy mẫu thư.")
    # Deduplication Guard against rapid double-clicks / identical messages to same recipients
    from datetime import timedelta
    from .email_deduplication import get_dedup_window_seconds, _get_db_now
    window = get_dedup_window_seconds()
    db_now = _get_db_now(db)
    cutoff = (db_now - timedelta(seconds=window)).strftime("%Y-%m-%d %H:%M:%S")

    subject_check = payload.subject.strip()
    plain_content = _plain_text(sanitized)

    for recipient in recipients:
        recent_msg = db.execute(
            """SELECT m.id, m.content_html FROM INTERNAL_MESSAGES m
               JOIN INTERNAL_MESSAGE_RECIPIENTS r ON r.message_id = m.id
               WHERE m.sender_id = ? AND r.receiver_id = ?
                 AND LOWER(TRIM(m.subject)) = LOWER(TRIM(?))
                 AND m.created_at >= ?
               ORDER BY m.id DESC LIMIT 1""",
            (sender["ma_nguoi_dung"], recipient["ma_nguoi_dung"], subject_check, cutoff),
        ).fetchone()
        if recent_msg and _plain_text(recent_msg["content_html"]) == plain_content:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"DUPLICATE_EMAIL_SUPPRESSED: Bạn vừa gửi thư có cùng nội dung tới {recipient['ho_ten']} trong vòng 10 phút. Vui lòng không gửi lặp lại.",
            )

    try:
        message_ids = []
        if template and len(recipients) > 1:
            for recipient in recipients:
                context = _template_context(db, recipient, program_id)
                subject = render_template(template["subject"], context).strip()
                content = sanitize_html(render_template(template["body_html"], context))
                thread_id = create_thread(db, subject, sender["ma_nguoi_dung"])
                message_id = create_message(db, thread_id, sender["ma_nguoi_dung"], template["category"], subject, content)
                add_recipients(db, message_id, [recipient["ma_nguoi_dung"]])
                _enqueue_delivery(db, sender, [recipient], message_id, subject, content, template["category"], payload.sendEmail)
                message_ids.append(message_id)
        else:
            subject = payload.subject.strip()
            content = sanitized
            category = payload.category
            if template:
                context = _template_context(db, recipients[0], program_id)
                subject = render_template(template["subject"], context).strip()
                content = sanitize_html(render_template(template["body_html"], context))
                category = template["category"]
            thread_id = create_thread(db, subject, sender["ma_nguoi_dung"])
            message_id = create_message(db, thread_id, sender["ma_nguoi_dung"], category, subject, content)
            add_recipients(db, message_id, [recipient["ma_nguoi_dung"] for recipient in recipients])
            _enqueue_delivery(db, sender, recipients, message_id, subject, content, category, payload.sendEmail)
            message_ids.append(message_id)
        db.commit()
        return {"messageIds": message_ids, "sentCount": len(recipients)}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def reply_to_message(db, sender, message_id: int, payload):
    original = message_access(db, message_id, sender["ma_nguoi_dung"])
    if not original:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư hoặc bạn không có quyền truy cập.")
    content = sanitize_html(payload.contentHtml)
    if not _plain_text(content):
        raise HTTPException(status_code=422, detail="Nội dung trả lời không hợp lệ.")

    # Deduplication guard on thread replies
    from datetime import timedelta
    from .email_deduplication import get_dedup_window_seconds, _get_db_now
    window = get_dedup_window_seconds()
    db_now = _get_db_now(db)
    cutoff = (db_now - timedelta(seconds=window)).strftime("%Y-%m-%d %H:%M:%S")

    recent_reply = db.execute(
        """SELECT id, content_html FROM INTERNAL_MESSAGES
           WHERE thread_id = ? AND sender_id = ? AND created_at >= ?
           ORDER BY id DESC LIMIT 1""",
        (original["thread_id"], sender["ma_nguoi_dung"], cutoff),
    ).fetchone()
    if recent_reply and _plain_text(recent_reply["content_html"]) == _plain_text(content):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="DUPLICATE_EMAIL_SUPPRESSED: Bạn vừa gửi nội dung trả lời tương tự trong cuộc hội thoại này. Vui lòng không gửi lặp lại.",
        )
    participant_rows = db.execute("""
        SELECT DISTINCT participant_id FROM (
            SELECT sender_id AS participant_id FROM INTERNAL_MESSAGES WHERE thread_id=?
            UNION
            SELECT r.receiver_id FROM INTERNAL_MESSAGE_RECIPIENTS r
            JOIN INTERNAL_MESSAGES m ON m.id=r.message_id WHERE m.thread_id=?
        ) participants
        WHERE participant_id IS NOT NULL AND participant_id<>?
    """, (original["thread_id"], original["thread_id"], sender["ma_nguoi_dung"])).fetchall()
    recipient_ids = [row["participant_id"] for row in participant_rows]
    recipients = [dict(row) for row in get_users(db, recipient_ids)]
    if not recipients:
        raise HTTPException(status_code=422, detail="Hội thoại không còn người nhận hợp lệ.")
    subject = original["subject"] if original["subject"].lower().startswith("re:") else f"Re: {original['subject']}"
    try:
        reply_id = create_message(
            db, original["thread_id"], sender["ma_nguoi_dung"], original["category"],
            subject[:255], content, message_id,
        )
        add_recipients(db, reply_id, recipient_ids)
        _enqueue_delivery(db, sender, recipients, reply_id, subject, content, original["category"], payload.sendEmail)
        db.commit()
        return {"messageId": reply_id, "threadId": original["thread_id"]}
    except Exception:
        db.rollback()
        raise


def list_mailbox_messages(db, user_id: int, folder: str, page: int, page_size: int,
                          read_status: str, category: str | None, query: str | None):
    rows, total = repository_list_messages(
        db, user_id, folder, page, page_size, read_status, category, query,
    )
    items = []
    for row in rows:
        item = dict(row)
        item["preview"] = _plain_text(item.pop("content_html"))[:180]
        item["is_read"] = bool(item["is_read"])
        items.append(item)
    return {
        "items": items, "page": page, "pageSize": page_size,
        "totalItems": total, "totalPages": ceil(total / page_size) if total else 0,
    }


def get_thread(db, thread_id: int, user_id: int):
    if not thread_accessible(db, thread_id, user_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại.")
    result = []
    for row in thread_messages(db, thread_id):
        item = dict(row)
        item["recipients"] = [dict(recipient) for recipient in message_recipients(db, item["id"])]
        result.append(item)
    return result


def get_message_detail(db, message_id: int, user_id: int):
    row = message_access(db, message_id, user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy thư hoặc bạn không có quyền truy cập.")
    if not row["is_sender"] and not row["is_read"]:
        db.execute("""
            UPDATE INTERNAL_MESSAGE_RECIPIENTS
            SET is_read=1, read_at=CURRENT_TIMESTAMP
            WHERE message_id=? AND receiver_id=?
        """, (message_id, user_id))
        db.execute("""
            UPDATE THONG_BAO SET da_doc=1,
                thoi_gian_doc=COALESCE(thoi_gian_doc, CURRENT_TIMESTAMP)
            WHERE ma_nguoi_dung=? AND reference_type='internal_message' AND reference_id=?
        """, (user_id, str(message_id)))
        db.commit()
    item = dict(row)
    item["is_read"] = True if not item["is_sender"] else bool(item["is_read"])
    item["recipients"] = [dict(recipient) for recipient in message_recipients(db, message_id)]
    item["thread"] = get_thread(db, item["thread_id"], user_id)
    return item
