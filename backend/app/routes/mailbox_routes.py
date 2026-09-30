import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..database import get_db
from ..mailbox_content import sanitize_html
from ..mailbox_repository import mark_read, unread_count
from ..mailbox_service import (
    CATEGORIES, get_message_detail, get_thread, list_mailbox_messages,
    recipient_groups, reply_to_message, search_recipients, send_message,
)
from ..schemas import (
    MailboxMessageCreate, MailboxReplyCreate, MailboxTemplateCreate,
    MailboxTemplateUpdate,
)
from ..security import require_role


router = APIRouter(prefix="/api/mailbox", tags=["Internal Mailbox"])


@router.get("/messages")
def list_messages(
    request: Request,
    folder: str = Query(default="inbox", pattern="^(inbox|sent)$"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=50),
    statusFilter: str = Query(default="all", alias="status", pattern="^(all|unread|read)$"),
    category: str | None = None,
    q: str | None = Query(default=None, max_length=120),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request)
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=422, detail="Loại thư không hợp lệ.")
    return list_mailbox_messages(
        db, user["ma_nguoi_dung"], folder, page, pageSize,
        statusFilter, category, q.strip() if q else None,
    )


@router.get("/messages/{message_id}")
def message_detail(message_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    return get_message_detail(db, message_id, user["ma_nguoi_dung"])


@router.post("/messages", status_code=status.HTTP_201_CREATED)
def create_mailbox_message(
    payload: MailboxMessageCreate, request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "Admin", "HR", "Mentor", "ThucTapSinh")
    return send_message(db, user, payload)


@router.post("/messages/{message_id}/reply", status_code=status.HTTP_201_CREATED)
def reply(
    message_id: int, payload: MailboxReplyCreate, request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request)
    return reply_to_message(db, user, message_id, payload)


@router.post("/messages/{message_id}/read")
def mark_message_read(message_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    if not mark_read(db, message_id, user["ma_nguoi_dung"], True):
        raise HTTPException(status_code=404, detail="Không tìm thấy thư trong hộp thư đến.")
    db.commit()
    return {"messageId": message_id, "isRead": True}


@router.post("/messages/{message_id}/unread")
def mark_message_unread(message_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    if not mark_read(db, message_id, user["ma_nguoi_dung"], False):
        raise HTTPException(status_code=404, detail="Không tìm thấy thư trong hộp thư đến.")
    db.commit()
    return {"messageId": message_id, "isRead": False}


@router.get("/threads/{thread_id}")
def thread_detail(thread_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    return {"threadId": thread_id, "messages": get_thread(db, thread_id, user["ma_nguoi_dung"])}


@router.get("/unread-count")
def mailbox_unread_count(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    return {"unreadCount": unread_count(db, user["ma_nguoi_dung"])}


@router.get("/recipients")
def recipients(
    request: Request, q: str = Query(default="", max_length=120),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request)
    return search_recipients(db, user, q)


@router.get("/recipient-groups")
def groups(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    return recipient_groups(db, user)


@router.get("/templates")
def list_templates(request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    rows = db.execute("""
        SELECT id, template_code AS templateCode, title, subject,
               body_html AS bodyHtml, category, is_active AS isActive,
               created_at AS createdAt, updated_at AS updatedAt
        FROM EMAIL_TEMPLATES WHERE deleted_at IS NULL
        ORDER BY is_active DESC, title
    """).fetchall()
    return [{**dict(row), "isActive": bool(row["isActive"])} for row in rows]


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_template(
    payload: MailboxTemplateCreate, request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "Admin", "HR")
    body = sanitize_html(payload.bodyHtml)
    if not body:
        raise HTTPException(status_code=422, detail="Nội dung mẫu thư không hợp lệ.")
    try:
        cursor = db.execute("""
            INSERT INTO EMAIL_TEMPLATES
                (template_code, title, subject, body_html, category, is_active, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.templateCode, payload.title.strip(), payload.subject.strip(), body,
            payload.category, int(payload.isActive), user["ma_nguoi_dung"],
        ))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Mã mẫu thư đã tồn tại.")
    return {"id": cursor.lastrowid, "templateCode": payload.templateCode}


@router.patch("/templates/{template_id}")
def update_template(
    template_id: int, payload: MailboxTemplateUpdate, request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    updates = payload.model_dump(exclude_unset=True)
    mapping = {
        "title": "title", "subject": "subject", "bodyHtml": "body_html",
        "category": "category", "isActive": "is_active",
    }
    values = []
    assignments = []
    for field, value in updates.items():
        if field == "bodyHtml":
            value = sanitize_html(value)
            if not value:
                raise HTTPException(status_code=422, detail="Nội dung mẫu thư không hợp lệ.")
        if isinstance(value, bool):
            value = int(value)
        assignments.append(f"{mapping[field]}=?")
        values.append(value.strip() if isinstance(value, str) and field != "bodyHtml" else value)
    if not assignments:
        return {"id": template_id}
    cursor = db.execute(f"""
        UPDATE EMAIL_TEMPLATES SET {', '.join(assignments)}, updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND deleted_at IS NULL
    """, (*values, template_id))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu thư.")
    db.commit()
    return {"id": template_id}


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    cursor = db.execute("""
        UPDATE EMAIL_TEMPLATES
        SET is_active=0, deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND deleted_at IS NULL
    """, (template_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu thư.")
    db.commit()
    return {"id": template_id, "deleted": True}


@router.post("/email-outbox/{outbox_id}/retry")
def retry_email(outbox_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    cursor = db.execute("""
        UPDATE EMAIL_OUTBOX
        SET status='RETRY', next_retry_at=CURRENT_TIMESTAMP, last_error=NULL,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='FAILED' AND retry_count < max_retry
    """, (outbox_id,))
    if not cursor.rowcount:
        raise HTTPException(status_code=409, detail="Email không ở trạng thái có thể thử lại.")
    db.commit()
    return {"id": outbox_id, "status": "RETRY"}
