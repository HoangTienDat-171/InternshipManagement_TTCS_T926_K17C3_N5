import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..audit_service import audit_schema_ready, filter_safe_metadata
from ..database import get_db
from ..security import require_role


router = APIRouter(prefix="/api/audit-logs", tags=["Activity Audit - US42"])


def _require_audit_admin(request: Request) -> dict:
    return require_role(request, "Admin")


def _require_schema(db) -> None:
    if not audit_schema_ready(db):
        raise HTTPException(status_code=503, detail="Audit Log chưa sẵn sàng. Hãy áp dụng migration 20261017_us38_us41_us42.sql cho database UAT rồi khởi động lại backend.")


def _public_event(row) -> dict:
    item = dict(row)
    try:
        metadata = json.loads(item.pop("metadata") or "{}")
    except (TypeError, ValueError):
        metadata = {}
    item["metadata"] = filter_safe_metadata(metadata)
    item["created_at"] = str(item["created_at"])
    return item


@router.get("")
def list_audit_events(
    request: Request,
    actor_id: int | None = Query(None, ge=1),
    action: str | None = Query(None, min_length=1, max_length=120),
    resource: str | None = Query(None, min_length=1, max_length=100),
    outcome: str | None = Query(None, pattern="^(SUCCESS|FAILURE)$"),
    date_from: str | None = Query(None, max_length=40),
    date_to: str | None = Query(None, max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_audit_admin(request)
    _require_schema(db)
    conditions: list[str] = []
    values: list = []
    if actor_id is not None:
        conditions.append("actor_user_id = ?")
        values.append(actor_id)
    if action:
        conditions.append("action LIKE ?")
        values.append(f"%{action.strip().upper()}%")
    if resource:
        conditions.append("resource = ?")
        values.append(resource.strip().upper())
    if outcome:
        conditions.append("outcome = ?")
        values.append(outcome)
    for name, value, operator in (("date_from", date_from, ">="), ("date_to", date_to, "<=")):
        if value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=422, detail=f"{name} phải là ngày giờ ISO hợp lệ.") from None
            conditions.append(f"created_at {operator} ?")
            values.append(parsed.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"))
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = int(db.execute(f"SELECT COUNT(*) AS total FROM IMS_AUDIT_LOG{where}", values).fetchone()["total"])
    rows = db.execute(
        f"""SELECT event_id, actor_user_id, actor_name, action, resource, resource_id,
                   outcome, metadata, created_at
            FROM IMS_AUDIT_LOG{where}
            ORDER BY event_id DESC LIMIT ? OFFSET ?""",
        [*values, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [_public_event(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/{event_id}")
def get_audit_event(event_id: int, request: Request, db=Depends(get_db)):
    _require_audit_admin(request)
    _require_schema(db)
    row = db.execute(
        """SELECT event_id, actor_user_id, actor_name, action, resource, resource_id,
                  outcome, metadata, created_at
           FROM IMS_AUDIT_LOG WHERE event_id = ?""",
        (event_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự kiện nhật ký.")
    return _public_event(row)
