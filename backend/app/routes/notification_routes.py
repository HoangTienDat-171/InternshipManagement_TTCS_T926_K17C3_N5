import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    rows = db.execute("""
        SELECT n.ma_thong_bao, n.tieu_de, n.noi_dung, n.da_doc, n.thoi_gian_gui,
               n.thoi_gian_doc, n.loai
        FROM THONG_BAO n
        WHERE n.ma_nguoi_dung = ? AND (n.loai IS NULL OR n.loai <> 'mailbox_message')
        ORDER BY n.ma_thong_bao DESC LIMIT 50
    """, (user["ma_nguoi_dung"],)).fetchall()
    return [dict(row) for row in rows]


@router.get("/email-outbox")
def list_email_outbox(request: Request, db: sqlite3.Connection = Depends(get_db)):
    """Expose delivery diagnostics only to staff; never return message bodies or credentials."""
    require_role(request, "Admin", "HR")
    rows = db.execute("""
        SELECT id, recipient_email, subject, template_type, reference_type, reference_id,
               status, retry_count, max_retry, last_error, next_retry_at,
               created_at, sent_at, updated_at
        FROM EMAIL_OUTBOX
        WHERE reference_type IS NULL OR reference_type <> 'internal_message'
        ORDER BY id DESC LIMIT 100
    """).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["max_retry"] = min(max(1, int(item["max_retry"] or 4)), 4)
        item["retry_count"] = int(item["retry_count"] or 0)
        item["attempts_made"] = item["retry_count"] + (1 if item["status"] in {"PROCESSING", "SENT"} else 0)
        items.append(item)
    return items


@router.put("/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    cursor = db.execute("""
        UPDATE THONG_BAO SET da_doc = 1, thoi_gian_doc = COALESCE(thoi_gian_doc, CURRENT_TIMESTAMP)
        WHERE ma_thong_bao = ? AND ma_nguoi_dung = ?
    """, (notification_id, user["ma_nguoi_dung"]))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thông báo.")
    db.commit()
    return {"ma_thong_bao": notification_id, "da_doc": True}
