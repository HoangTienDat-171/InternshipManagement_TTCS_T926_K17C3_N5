import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    rows = db.execute("""
        SELECT ma_thong_bao, tieu_de, noi_dung, da_doc, thoi_gian_gui
        FROM THONG_BAO WHERE ma_nguoi_dung = ?
        ORDER BY ma_thong_bao DESC LIMIT 50
    """, (user["ma_nguoi_dung"],)).fetchall()
    return [dict(row) for row in rows]


@router.put("/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request)
    cursor = db.execute("""
        UPDATE THONG_BAO SET da_doc = 1
        WHERE ma_thong_bao = ? AND ma_nguoi_dung = ?
    """, (notification_id, user["ma_nguoi_dung"]))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy thông báo.")
    db.commit()
    return {"ma_thong_bao": notification_id, "da_doc": True}
