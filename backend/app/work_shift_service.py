"""US23 work-shift configuration and future US21 shift resolution."""
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException

from . import database


@contextmanager
def _serialized_write(db):
    """Serialize overlap validation and writes across SQLite/MySQL workers."""
    mysql_lock_acquired = False
    transaction_started = False
    try:
        if database.DATABASE_BACKEND == "mysql":
            acquired = db.execute(
                "SELECT GET_LOCK(?, 10) AS acquired", ("ims-us23-work-shift-write",)
            ).fetchone()
            if not acquired or acquired["acquired"] != 1:
                raise HTTPException(status_code=503, detail="Hệ thống đang bận cập nhật ca làm việc. Vui lòng thử lại.")
            mysql_lock_acquired = True
        db.execute("BEGIN IMMEDIATE")
        transaction_started = True
        yield
        db.commit()
    except Exception:
        if transaction_started:
            db.rollback()
        raise
    finally:
        if mysql_lock_acquired:
            try:
                db.execute("SELECT RELEASE_LOCK(?)", ("ims-us23-work-shift-write",))
                db.commit()
            except Exception:
                db.rollback()


def _time_text(value) -> str:
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    return str(value)


def _date_text(value) -> str:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)[:10]


def _shift_dict(row) -> dict:
    shift = dict(row)
    shift["start_time"] = _time_text(shift["start_time"])
    shift["end_time"] = _time_text(shift["end_time"])
    shift["effective_from"] = _date_text(shift["effective_from"])
    shift["effective_to"] = _date_text(shift["effective_to"]) if shift["effective_to"] else None
    return shift


class WorkShiftService:
    def __init__(self, db):
        self.db = db

    def list_shifts(self, *, status=None, scope_type=None, program_id=None, effective_date=None):
        conditions = []
        params = []
        if status:
            conditions.append("s.status = ?")
            params.append(status)
        if scope_type:
            conditions.append("s.scope_type = ?")
            params.append(scope_type)
        if program_id is not None:
            conditions.append("s.ma_chuong_trinh = ?")
            params.append(program_id)
        if effective_date:
            conditions.extend(("s.effective_from <= ?", "(s.effective_to IS NULL OR s.effective_to >= ?)"))
            day = effective_date.isoformat() if isinstance(effective_date, date) else str(effective_date)
            params.extend((day, day))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.db.execute(f"""
            SELECT s.id, s.name, s.start_time, s.end_time, s.scope_type,
                   s.ma_chuong_trinh AS program_id, p.ten_ct AS program_name,
                   p.ma_ct AS program_code,
                   s.effective_from, s.effective_to, s.status, s.created_by,
                   s.created_at, s.updated_at
            FROM CA_LAM_VIEC s
            LEFT JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = s.ma_chuong_trinh
            {where}
            ORDER BY s.scope_type, p.ten_ct, s.start_time, s.effective_from, s.id
        """, tuple(params)).fetchall()
        return [_shift_dict(row) for row in rows]

    def get_shift(self, shift_id: int):
        row = self.db.execute("""
            SELECT s.id, s.name, s.start_time, s.end_time, s.scope_type,
                   s.ma_chuong_trinh AS program_id, p.ten_ct AS program_name,
                   p.ma_ct AS program_code,
                   s.effective_from, s.effective_to, s.status, s.created_by,
                   s.created_at, s.updated_at
            FROM CA_LAM_VIEC s
            LEFT JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = s.ma_chuong_trinh
            WHERE s.id = ?
        """, (shift_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy ca làm việc.")
        return _shift_dict(row)

    def create_shift(self, values, actor_id: int):
        data = self._normalize_values(values)
        with _serialized_write(self.db):
            self._validate_values(data)
            try:
                cursor = self.db.execute("""
                    INSERT INTO CA_LAM_VIEC
                        (name, start_time, end_time, scope_type, ma_chuong_trinh,
                         effective_from, effective_to, status, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["name"], data["start_time"], data["end_time"], data["scope_type"],
                    data["program_id"], data["effective_from"], data["effective_to"],
                    data["status"], actor_id,
                ))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="Không thể lưu ca làm việc do dữ liệu liên quan đã thay đổi.") from exc
            shift_id = cursor.lastrowid
        return self.get_shift(shift_id)

    def update_shift(self, shift_id: int, changes: dict):
        with _serialized_write(self.db):
            current_row = self.db.execute("SELECT * FROM CA_LAM_VIEC WHERE id = ?", (shift_id,)).fetchone()
            if not current_row:
                raise HTTPException(status_code=404, detail="Không tìm thấy ca làm việc.")
            current = dict(current_row)
            merged = self._normalize_values({**current, **changes})
            self._validate_values(merged, exclude_id=shift_id)
            try:
                self.db.execute("""
                    UPDATE CA_LAM_VIEC
                    SET name = ?, start_time = ?, end_time = ?, scope_type = ?,
                        ma_chuong_trinh = ?, effective_from = ?, effective_to = ?,
                        status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    merged["name"], merged["start_time"], merged["end_time"], merged["scope_type"],
                    merged["program_id"], merged["effective_from"], merged["effective_to"],
                    merged["status"], shift_id,
                ))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="Không thể cập nhật ca do dữ liệu liên quan đã thay đổi.") from exc
        return self.get_shift(shift_id)

    def _normalize_values(self, values: dict) -> dict:
        normalized = dict(values)
        normalized["name"] = str(normalized.get("name") or "").strip()
        normalized["start_time"] = _time_text(normalized.get("start_time"))
        normalized["end_time"] = _time_text(normalized.get("end_time"))
        normalized["effective_from"] = _date_text(normalized.get("effective_from"))
        normalized["effective_to"] = _date_text(normalized["effective_to"]) if normalized.get("effective_to") else None
        normalized["scope_type"] = normalized.get("scope_type")
        normalized["program_id"] = normalized.get("program_id", normalized.get("ma_chuong_trinh"))
        normalized["status"] = normalized.get("status")
        return normalized

    def _validate_values(self, data: dict, *, exclude_id=None):
        if not data["name"] or len(data["name"]) > 120:
            raise HTTPException(status_code=400, detail="Tên ca làm việc là bắt buộc và tối đa 120 ký tự.")
        if data["scope_type"] not in ("GLOBAL", "PROGRAM"):
            raise HTTPException(status_code=400, detail="Phạm vi ca phải là GLOBAL hoặc PROGRAM.")
        if data["status"] not in ("ACTIVE", "INACTIVE"):
            raise HTTPException(status_code=400, detail="Trạng thái ca không hợp lệ.")
        if (data["scope_type"] == "GLOBAL") != (data["program_id"] is None):
            raise HTTPException(status_code=400, detail="Ca GLOBAL không gắn chương trình; ca PROGRAM phải chọn chương trình.")
        if data["program_id"] is not None:
            exists = self.db.execute(
                "SELECT 1 AS present FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh = ?",
                (data["program_id"],),
            ).fetchone()
            if not exists:
                raise HTTPException(status_code=400, detail="Chương trình thực tập không tồn tại.")
        try:
            start = time.fromisoformat(data["start_time"])
            end = time.fromisoformat(data["end_time"])
            start_date = date.fromisoformat(data["effective_from"])
            end_date = date.fromisoformat(data["effective_to"]) if data["effective_to"] else None
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Giờ hoặc ngày hiệu lực không hợp lệ.") from exc
        if start.tzinfo is not None or end.tzinfo is not None:
            raise HTTPException(status_code=400, detail="Giờ ca phải là giờ địa phương, không kèm múi giờ.")
        if start >= end:
            raise HTTPException(status_code=400, detail="Ca qua đêm không được hỗ trợ; giờ bắt đầu phải trước giờ kết thúc.")
        if end_date is not None and end_date < start_date:
            raise HTTPException(status_code=400, detail="Ngày kết thúc hiệu lực phải sau hoặc bằng ngày bắt đầu.")
        if data["status"] == "ACTIVE":
            conflict = self.db.execute("""
                SELECT id FROM CA_LAM_VIEC
                WHERE status = 'ACTIVE'
                  AND scope_type = ?
                  AND ((? = 'GLOBAL' AND ma_chuong_trinh IS NULL)
                    OR (? = 'PROGRAM' AND ma_chuong_trinh = ?))
                  AND (effective_to IS NULL OR effective_to >= ?)
                  AND (? IS NULL OR effective_from <= ?)
                  AND start_time < ? AND ? < end_time
                  AND (? IS NULL OR id <> ?)
                LIMIT 1
            """, (
                data["scope_type"], data["scope_type"], data["scope_type"], data["program_id"],
                data["effective_from"], data["effective_to"], data["effective_to"],
                data["end_time"], data["start_time"], exclude_id, exclude_id,
            )).fetchone()
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ca bị chồng lấn với ca #{conflict['id']} trong cùng phạm vi và thời gian hiệu lực.",
                )


def resolve_applicable_shifts(db, program_id: int | None, on_date: date) -> list[dict]:
    """Return applicable active shifts; a program-specific schedule overrides global."""
    day = on_date.isoformat() if isinstance(on_date, date) else str(on_date)
    if program_id is not None:
        specific = db.execute("""
            SELECT id, name, start_time, end_time, scope_type, ma_chuong_trinh AS program_id,
                   effective_from, effective_to, status
            FROM CA_LAM_VIEC
            WHERE status = 'ACTIVE' AND scope_type = 'PROGRAM' AND ma_chuong_trinh = ?
              AND effective_from <= ? AND (effective_to IS NULL OR effective_to >= ?)
            ORDER BY start_time, id
        """, (program_id, day, day)).fetchall()
        if specific:
            return [_shift_dict(row) for row in specific]
    global_rows = db.execute("""
        SELECT id, name, start_time, end_time, scope_type, ma_chuong_trinh AS program_id,
               effective_from, effective_to, status
        FROM CA_LAM_VIEC
        WHERE status = 'ACTIVE' AND scope_type = 'GLOBAL' AND ma_chuong_trinh IS NULL
          AND effective_from <= ? AND (effective_to IS NULL OR effective_to >= ?)
        ORDER BY start_time, id
    """, (day, day)).fetchall()
    return [_shift_dict(row) for row in global_rows]
