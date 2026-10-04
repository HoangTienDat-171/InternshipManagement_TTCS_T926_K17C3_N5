"""US21 self-service attendance using the US23 work-shift resolver."""
import logging
import sqlite3
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException

from . import database
from .work_shift_service import resolve_applicable_shifts


logger = logging.getLogger(__name__)
NO_SHIFT_MESSAGE = "Không có ca làm việc áp dụng cho hôm nay."
NO_CHECK_IN_MESSAGE = "Bạn chưa Check-in cho ca làm hôm nay."


@contextmanager
def _write_transaction(db):
    try:
        db.execute("BEGIN IMMEDIATE")
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_time(value) -> str:
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    return str(value)


class InternAttendanceService:
    def __init__(self, db):
        self.db = db

    def _profile(self, user_id: int, *, for_update: bool = False) -> dict:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        row = self.db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung,
                   h.trang_thai_xet_duyet, h.trang_thai_thuc_tap
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh'
        """ + lock, (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")
        if row["trang_thai_xet_duyet"] != "DaDuyet":
            raise HTTPException(status_code=409, detail="Hồ sơ thực tập sinh chưa được duyệt.")
        if row["trang_thai_thuc_tap"] != "DangThucTap":
            raise HTTPException(status_code=409, detail="Hồ sơ thực tập sinh hiện không trong trạng thái thực tập.")
        return dict(row)

    def _server_clock(self) -> tuple[date, str]:
        row = self.db.execute("""
            SELECT CURRENT_DATE AS server_date, CURRENT_TIMESTAMP AS server_now
        """).fetchone()
        now = row["server_now"]
        return _as_date(row["server_date"]), now.isoformat(sep=" ") if isinstance(now, datetime) else str(now)

    def _current_program_id(self, profile_id: int) -> int | None:
        row = self.db.execute("""
            SELECT a.ma_chuong_trinh
            FROM UNG_TUYEN_CHUONG_TRINH a
            WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
            ORDER BY a.ngay_ung_tuyen DESC, a.ma_ung_tuyen DESC
            LIMIT 1
        """, (profile_id,)).fetchone()
        # Match the existing intern workspace's current-program rule: most recently applied approved program.
        return row["ma_chuong_trinh"] if row else None

    def _applicable_shift(self, program_id: int | None, day: date, *, required: bool = True) -> dict | None:
        shifts = resolve_applicable_shifts(self.db, program_id, day)
        if not shifts:
            if required:
                raise HTTPException(status_code=409, detail=NO_SHIFT_MESSAGE)
            return None
        if len(shifts) > 1:
            logger.error(
                "US21 shift configuration is ambiguous for program_id=%s attendance_date=%s count=%s",
                program_id, day.isoformat(), len(shifts),
            )
            raise HTTPException(status_code=409, detail="Có nhiều ca làm việc áp dụng cho hôm nay. Vui lòng liên hệ quản trị viên.")
        return shifts[0]

    @staticmethod
    def _record_query() -> str:
        return """
            SELECT a.id, a.attendance_date, a.check_in_at, a.check_out_at,
                   a.status, a.note,
                   s.id AS shift_id, s.name AS shift_name,
                   s.start_time AS shift_start_time, s.end_time AS shift_end_time,
                   s.scope_type AS shift_scope_type
            FROM CHAM_CONG a
            JOIN CA_LAM_VIEC s ON s.id = a.ca_lam_viec_id
        """

    def _today_records(self, profile_id: int, day: date, *, for_update: bool = False) -> list[dict]:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        rows = self.db.execute(
            self._record_query() + " WHERE a.ma_ho_so = ? AND a.attendance_date = ? ORDER BY a.id LIMIT 2" + lock,
            (profile_id, day.isoformat()),
        ).fetchall()
        return [self._public_record(row) for row in rows]

    @staticmethod
    def _public_record(row) -> dict:
        record = dict(row)
        shift = {
            "id": record.pop("shift_id"),
            "name": record.pop("shift_name"),
            "start_time": _as_time(record.pop("shift_start_time")),
            "end_time": _as_time(record.pop("shift_end_time")),
            "scope_type": record.pop("shift_scope_type"),
        }
        record["attendance_date"] = _as_date(record["attendance_date"]).isoformat()
        record["check_in_at"] = str(record["check_in_at"])
        record["check_out_at"] = str(record["check_out_at"]) if record["check_out_at"] is not None else None
        record["shift"] = shift
        return record

    def today(self, user_id: int) -> dict:
        profile = self._profile(user_id)
        day, _ = self._server_clock()
        records = self._today_records(profile["ma_ho_so"], day)
        if len(records) > 1:
            logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
            raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
        if records:
            attendance = records[0]
            return {
                "date": day.isoformat(),
                "applicable_shift": attendance["shift"],
                "attendance": attendance,
                "can_check_in": False,
                "can_check_out": attendance["status"] == "CHECKED_IN",
                "no_shift": False,
            }

        shift = self._applicable_shift(self._current_program_id(profile["ma_ho_so"]), day, required=False)
        return {
            "date": day.isoformat(),
            "applicable_shift": shift,
            "attendance": None,
            "can_check_in": shift is not None,
            "can_check_out": False,
            "no_shift": shift is None,
        }

    def history(
        self,
        user_id: int,
        *,
        month: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        profile = self._profile(user_id)
        if month and (date_from or date_to):
            raise HTTPException(status_code=400, detail="Chỉ được dùng bộ lọc tháng hoặc khoảng ngày.")
        if month:
            try:
                year, month_number = (int(value) for value in month.split("-", 1))
                date_from = date(year, month_number, 1)
                date_to = date(year, month_number, monthrange(year, month_number)[1])
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Tháng không hợp lệ. Dùng định dạng YYYY-MM.") from None
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=422, detail="Ngày bắt đầu không được sau ngày kết thúc.")

        conditions = ["a.ma_ho_so = ?"]
        params: list = [profile["ma_ho_so"]]
        if date_from:
            conditions.append("a.attendance_date >= ?")
            params.append(date_from.isoformat())
        if date_to:
            conditions.append("a.attendance_date <= ?")
            params.append(date_to.isoformat())
        where = " WHERE " + " AND ".join(conditions)
        total = self.db.execute(
            "SELECT COUNT(*) AS total FROM CHAM_CONG a" + where,
            params,
        ).fetchone()["total"]
        rows = self.db.execute(
            self._record_query() + where + " ORDER BY a.attendance_date DESC, a.check_in_at DESC, a.id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
        return {
            "items": [self._public_record(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size,
        }

    def check_in(self, user_id: int, note: str | None = None) -> dict:
        with _write_transaction(self.db):
            profile = self._profile(user_id, for_update=True)
            day, server_now = self._server_clock()
            existing = self._today_records(profile["ma_ho_so"], day, for_update=True)
            if len(existing) > 1:
                logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
                raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
            if existing:
                return existing[0]

            program_id = self._current_program_id(profile["ma_ho_so"])
            shift = self._applicable_shift(program_id, day)
            try:
                cursor = self.db.execute("""
                    INSERT INTO CHAM_CONG
                        (ma_ho_so, ca_lam_viec_id, attendance_date, check_in_at, status, note)
                    VALUES (?, ?, ?, ?, 'CHECKED_IN', ?)
                """, (profile["ma_ho_so"], shift["id"], day.isoformat(), server_now, note))
            except sqlite3.IntegrityError:
                # The unique key remains the final guard if another writer bypasses the profile lock.
                existing = self._today_records(profile["ma_ho_so"], day, for_update=True)
                if len(existing) > 1:
                    logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
                    raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
                if existing:
                    return existing[0]
                raise
            row = self.db.execute(self._record_query() + " WHERE a.id = ?", (cursor.lastrowid,)).fetchone()
            return self._public_record(row)

    def check_out(self, user_id: int) -> dict:
        with _write_transaction(self.db):
            profile = self._profile(user_id, for_update=True)
            day, server_now = self._server_clock()
            records = self._today_records(profile["ma_ho_so"], day, for_update=True)
            if not records:
                raise HTTPException(status_code=409, detail=NO_CHECK_IN_MESSAGE)
            if len(records) > 1:
                logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
                raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
            attendance = records[0]
            if attendance["status"] == "CHECKED_IN":
                self.db.execute("""
                    UPDATE CHAM_CONG
                    SET check_out_at = ?, status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND check_out_at IS NULL
                """, (server_now, attendance["id"]))
                attendance = self._today_records(profile["ma_ho_so"], day, for_update=True)[0]
            return attendance
