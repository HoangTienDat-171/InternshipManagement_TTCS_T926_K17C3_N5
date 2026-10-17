"""US21 self-service attendance using the US23 work-shift resolver."""
import logging
import sqlite3
import hashlib
import secrets
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Protocol

from fastapi import HTTPException

from . import database
from .audit_service import write_audit_event
from .work_shift_service import resolve_applicable_shifts


logger = logging.getLogger(__name__)
NO_SHIFT_MESSAGE = "Không có ca làm việc áp dụng cho hôm nay."
NO_CHECK_IN_MESSAGE = "Bạn chưa Check-in cho ca làm hôm nay."


@contextmanager
def _write_transaction(db):
    try:
        # MySQL has no BEGIN IMMEDIATE syntax; use its transaction start while
        # keeping SQLite's write reservation for the existing concurrency tests.
        db.execute("BEGIN IMMEDIATE" if database.DATABASE_BACKEND == "sqlite" else "START TRANSACTION")
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
                   a.status, a.note, COALESCE(src.source, 'MANUAL') AS source,
                   s.id AS shift_id, s.name AS shift_name,
                   s.start_time AS shift_start_time, s.end_time AS shift_end_time,
                   s.scope_type AS shift_scope_type
            FROM CHAM_CONG a
            JOIN CA_LAM_VIEC s ON s.id = a.ca_lam_viec_id
            LEFT JOIN IMS_ATTENDANCE_SOURCES src ON src.attendance_id = a.id
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

    def _check_in_in_transaction(
        self,
        user_id: int,
        *,
        note: str | None = None,
        source: str = "MANUAL",
        audit_actor: dict | None = None,
    ) -> tuple[dict, bool]:
        profile = self._profile(user_id, for_update=True)
        day, server_now = self._server_clock()
        existing = self._today_records(profile["ma_ho_so"], day, for_update=True)
        if len(existing) > 1:
            logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
            raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
        if existing:
            return existing[0], False

        program_id = self._current_program_id(profile["ma_ho_so"])
        shift = self._applicable_shift(program_id, day)
        try:
            cursor = self.db.execute("""
                INSERT INTO CHAM_CONG
                    (ma_ho_so, ca_lam_viec_id, attendance_date, check_in_at, status, note)
                VALUES (?, ?, ?, ?, 'CHECKED_IN', ?)
            """, (profile["ma_ho_so"], shift["id"], day.isoformat(), server_now, note))
        except sqlite3.IntegrityError:
            # The existing profile lock and unique key remain the concurrency guards.
            existing = self._today_records(profile["ma_ho_so"], day, for_update=True)
            if len(existing) > 1:
                logger.error("US21 multiple attendance rows for profile_id=%s attendance_date=%s", profile["ma_ho_so"], day)
                raise HTTPException(status_code=409, detail="Có nhiều bản ghi chấm công trong hôm nay. Vui lòng liên hệ quản trị viên.")
            if existing:
                return existing[0], False
            raise
        attendance_id = int(cursor.lastrowid)
        self.db.execute(
            "INSERT INTO IMS_ATTENDANCE_SOURCES(attendance_id, source) VALUES (?, ?)",
            (attendance_id, source),
        )
        row = self.db.execute(self._record_query() + " WHERE a.id = ?", (attendance_id,)).fetchone()
        record = self._public_record(row)
        write_audit_event(
            self.db,
            actor=audit_actor or {"ma_nguoi_dung": user_id},
            action="ATTENDANCE_CHECK_IN",
            resource="ATTENDANCE",
            resource_id=attendance_id,
            outcome="SUCCESS",
            metadata={"source": source, "shift_id": shift["id"]},
        )
        return record, True

    def check_in(self, user_id: int, note: str | None = None, *, audit_actor: dict | None = None) -> dict:
        with _write_transaction(self.db):
            record, _created = self._check_in_in_transaction(
                user_id, note=note, source="MANUAL", audit_actor=audit_actor,
            )
            return record

    def issue_qr_credential(self, user_id: int, *, lifetime_seconds: int = 120) -> dict:
        if not 30 <= lifetime_seconds <= 300:
            raise ValueError("QR lifetime must be between 30 and 300 seconds")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with _write_transaction(self.db):
            self._profile(user_id, for_update=True)
            row = self.db.execute("SELECT CURRENT_TIMESTAMP AS server_now").fetchone()
            raw_now = row["server_now"]
            now = raw_now if isinstance(raw_now, datetime) else datetime.fromisoformat(str(raw_now))
            expires_at = (now.replace(tzinfo=None) + timedelta(seconds=lifetime_seconds)).isoformat(sep=" ", timespec="seconds")
            # A TTS can keep only one pending short-lived code at a time.
            self.db.execute(
                "UPDATE IMS_ATTENDANCE_QR_CREDENTIALS SET expires_at=CURRENT_TIMESTAMP "
                "WHERE ma_nguoi_dung=? AND used_at IS NULL AND expires_at>CURRENT_TIMESTAMP",
                (user_id,),
            )
            self.db.execute(
                """INSERT INTO IMS_ATTENDANCE_QR_CREDENTIALS
                   (token_hash, ma_nguoi_dung, issued_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (token_hash, user_id, now.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"), expires_at),
            )
            write_audit_event(
                self.db,
                actor={"ma_nguoi_dung": user_id},
                action="ATTENDANCE_QR_ISSUED",
                resource="ATTENDANCE",
                outcome="SUCCESS",
                metadata={"expires_in_seconds": lifetime_seconds},
            )
        return {"token": token, "expires_at": expires_at, "expires_in_seconds": lifetime_seconds}

    def check_in_with_qr(self, token: str, *, scanner: dict) -> dict:
        if not token or len(token) > 128:
            raise HTTPException(status_code=422, detail="Mã QR không hợp lệ hoặc đã hết hạn.")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with _write_transaction(self.db):
            lock = " FOR UPDATE" if database.DATABASE_BACKEND == "mysql" else ""
            credential = self.db.execute(
                """SELECT id, ma_nguoi_dung, expires_at, used_at,
                          CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS is_unexpired
                   FROM IMS_ATTENDANCE_QR_CREDENTIALS WHERE token_hash = ?""" + lock,
                (token_hash,),
            ).fetchone()
            if not credential or credential["used_at"] is not None:
                raise HTTPException(status_code=409, detail="Mã QR không tồn tại, đã được dùng hoặc đã bị thay thế.")
            if not credential["is_unexpired"]:
                raise HTTPException(status_code=410, detail="Mã QR đã hết hạn. TTS cần tạo mã mới.")
            record, created = self._check_in_in_transaction(
                int(credential["ma_nguoi_dung"]), source="QR", audit_actor=scanner,
            )
            if not created:
                raise HTTPException(status_code=409, detail="TTS đã có lượt check-in trong ca hiện tại; mã QR chưa được ghi nhận.")
            updated = self.db.execute(
                """UPDATE IMS_ATTENDANCE_QR_CREDENTIALS
                   SET used_at=CURRENT_TIMESTAMP, attendance_id=? WHERE id=? AND used_at IS NULL""",
                (record["id"], credential["id"]),
            )
            if updated.rowcount != 1:
                raise HTTPException(status_code=409, detail="Mã QR vừa được sử dụng bởi một yêu cầu khác.")
            return record

    def check_out(self, user_id: int, *, audit_actor: dict | None = None) -> dict:
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
                write_audit_event(
                    self.db,
                    actor=audit_actor or {"ma_nguoi_dung": user_id},
                    action="ATTENDANCE_CHECK_OUT",
                    resource="ATTENDANCE",
                    resource_id=attendance["id"],
                    outcome="SUCCESS",
                    metadata={"source": attendance.get("source", "MANUAL")},
                )
            return attendance


class CardCredentialResolver(Protocol):
    """Adapter contract only; connect a real reader/UID provider before using CARD."""

    def resolve_user_id(self, credential: str) -> int | None:
        """Resolve a trusted reader credential to an IMS account, or return None."""


def check_in_with_card(db, credential: str, adapter: CardCredentialResolver, *, scanner: dict) -> dict:
    """Device-neutral CARD extension point; no physical reader is claimed as connected."""
    if not credential or len(credential) > 256:
        raise HTTPException(status_code=422, detail="Thẻ không hợp lệ.")
    user_id = adapter.resolve_user_id(credential)
    if not user_id:
        raise HTTPException(status_code=403, detail="Thẻ chưa được ánh xạ hoặc đầu đọc chưa được cấu hình.")
    with _write_transaction(db):
        record, created = InternAttendanceService(db)._check_in_in_transaction(
            int(user_id), source="CARD", audit_actor=scanner,
        )
        if not created:
            raise HTTPException(status_code=409, detail="TTS đã có lượt check-in trong ca hiện tại.")
        return record
