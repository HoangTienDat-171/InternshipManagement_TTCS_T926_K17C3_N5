"""US25/26 allowance ledger, receipt acknowledgments, and complaint audit trail."""
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from fastapi import HTTPException

from .notifications import create_notification


SELECT_RECORD = """
    SELECT p.*, a.ma_chuong_trinh, c.ma_ct, c.ten_ct,
           h.ma_nguoi_dung, u.ho_ten, u.email,
           creator.ho_ten AS nguoi_tao, updater.ho_ten AS nguoi_cap_nhat,
           confirmer.ho_ten AS nguoi_xac_nhan,
           r.id AS latest_report_id, r.trang_thai_xu_ly AS latest_report_status,
           r.noi_dung AS latest_report_note,
           r.ghi_chu_xu_ly AS latest_resolution_note,
           r.created_at AS latest_reported_at, r.updated_at AS latest_report_updated_at,
           reporter.ho_ten AS latest_reporter_name, handler.ho_ten AS latest_handler_name,
           (SELECT COUNT(*) FROM PHU_CAP_PHAN_ANH rc WHERE rc.allowance_id = p.id) AS report_count
    FROM PHU_CAP_THUC_TAP p
    JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
    JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
    JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ung_tuyen = p.ma_ung_tuyen
    JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
    JOIN NGUOI_DUNG creator ON creator.ma_nguoi_dung = p.created_by
    JOIN NGUOI_DUNG updater ON updater.ma_nguoi_dung = p.updated_by
    LEFT JOIN NGUOI_DUNG confirmer ON confirmer.ma_nguoi_dung = p.xac_nhan_boi
    LEFT JOIN PHU_CAP_PHAN_ANH r ON r.id = (
        SELECT rr.id FROM PHU_CAP_PHAN_ANH rr
        WHERE rr.allowance_id = p.id ORDER BY rr.id DESC LIMIT 1
    )
    LEFT JOIN NGUOI_DUNG reporter ON reporter.ma_nguoi_dung = r.reported_by
    LEFT JOIN NGUOI_DUNG handler ON handler.ma_nguoi_dung = r.updated_by
"""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def serialize_record(row):
    result = dict(row)
    result["so_tien"] = format(Decimal(result.pop("so_tien_minor")) / 100, ".2f")
    receipt = result.get("trang_thai_nhan") or "ChoXacNhan"
    latest_report = result.get("latest_report_id")
    report_state = result.get("latest_report_status")
    if receipt == "DaNhan":
        result["trang_thai_hien_tai"] = "DaNhan"
    elif latest_report and report_state == "DangXuLy":
        result["trang_thai_hien_tai"] = "DangXuLy"
    elif latest_report:
        result["trang_thai_hien_tai"] = "ChuaNhanDuoc"
    else:
        result["trang_thai_hien_tai"] = "ChoXacNhan"
    return result


class AllowanceService:
    def __init__(self, db):
        self.db = db

    def _begin_write(self):
        # SQLite tests need an early write lock; MySQL uses SELECT ... FOR UPDATE.
        if isinstance(self.db, sqlite3.Connection) and not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")

    def _lock_suffix(self):
        return "" if isinstance(self.db, sqlite3.Connection) else " FOR UPDATE"

    def _record_row(self, record_id, owner_id=None, *, lock=False):
        if lock:
            locked = self.db.execute("SELECT id, ma_ho_so, so_tien_minor, ky, trang_thai_nhan "
                "FROM PHU_CAP_THUC_TAP WHERE id = ?" + self._lock_suffix(), (record_id,)).fetchone()
            if not locked:
                raise HTTPException(404, "Không tìm thấy thông tin phụ cấp.")
            if owner_id is not None:
                owned = self.db.execute("""SELECT 1 FROM HO_SO_THUC_TAP
                    WHERE ma_ho_so = ? AND ma_nguoi_dung = ?""",
                    (locked["ma_ho_so"], owner_id)).fetchone()
                if not owned:
                    raise HTTPException(404, "Không tìm thấy thông tin phụ cấp.")
        query = SELECT_RECORD + " WHERE p.id = ?"
        params = [record_id]
        if owner_id is not None:
            query += " AND h.ma_nguoi_dung = ?"
            params.append(owner_id)
        row = self.db.execute(query, params).fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy thông tin phụ cấp.")
        return row

    def _actor(self, actor_id):
        actor = self.db.execute(
            "SELECT ma_nguoi_dung, ho_ten, vai_tro FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
            (actor_id,),
        ).fetchone()
        if not actor:
            raise HTTPException(401, "Phiên đăng nhập không còn hợp lệ.")
        return actor

    def _append_history(self, *, allowance_id, actor_id, event_type, note="",
                        report_id=None, amount_minor=None, period=None, created_at=None):
        actor = self._actor(actor_id)
        self.db.execute("""INSERT INTO PHU_CAP_LICH_SU_XU_LY
            (allowance_id, report_id, event_type, noi_dung, actor_id, actor_name,
             actor_role, so_tien_minor_snapshot, ky_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (allowance_id, report_id, event_type, note, actor["ma_nguoi_dung"],
             actor["ho_ten"], actor["vai_tro"], amount_minor, period, created_at or _now()))

    def options(self, search="", program_id=None, page=1, page_size=25):
        """Approved program participations only; used by the allowance create form."""
        where = ["a.trang_thai = 'DaDuyet'", "h.trang_thai_xet_duyet = 'DaDuyet'",
                 "u.vai_tro = 'ThucTapSinh'"]
        params = []
        if search:
            where.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR CAST(u.ma_nguoi_dung AS CHAR) = ?)")
            params.extend([f"%{search}%", f"%{search}%", search])
        if program_id is not None:
            where.append("a.ma_chuong_trinh = ?")
            params.append(program_id)
        source = """FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE """ + " AND ".join(where)
        total = self.db.execute("SELECT COUNT(*) AS total " + source, params).fetchone()["total"]
        rows = self.db.execute("""SELECT a.ma_ung_tuyen, h.ma_ho_so, u.ma_nguoi_dung,
            u.ho_ten, u.email, a.ma_chuong_trinh, c.ten_ct, c.ma_ct,
            c.ngay_bat_dau, c.ngay_ket_thuc
            """ + source + " ORDER BY u.ho_ten, a.ma_ung_tuyen LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page,
                "page_size": page_size}

    def intern_options(self, search="", program_id=None, page=1, page_size=25):
        """One searchable row per intern, including interns without an eligible profile."""
        where = ["u.vai_tro = 'ThucTapSinh'"]
        params = []
        if search:
            where.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR CAST(u.ma_nguoi_dung AS CHAR) = ?)")
            params.extend([f"%{search}%", f"%{search}%", search])
        if program_id is not None:
            where.append("EXISTS (SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH pa "
                         "JOIN HO_SO_THUC_TAP ph ON ph.ma_ho_so = pa.ma_ho_so "
                         "WHERE ph.ma_nguoi_dung = u.ma_nguoi_dung "
                         "AND pa.ma_chuong_trinh = ? AND pa.trang_thai = 'DaDuyet' "
                         "AND ph.trang_thai_xet_duyet = 'DaDuyet')")
            params.append(program_id)
        source = "FROM NGUOI_DUNG u WHERE " + " AND ".join(where)
        total = self.db.execute("SELECT COUNT(*) AS total " + source, params).fetchone()["total"]
        rows = self.db.execute("""SELECT u.ma_nguoi_dung, u.ho_ten, u.email,
            (SELECT ah.ma_ho_so FROM UNG_TUYEN_CHUONG_TRINH aa
                JOIN HO_SO_THUC_TAP ah ON ah.ma_ho_so = aa.ma_ho_so
                WHERE ah.ma_nguoi_dung = u.ma_nguoi_dung
                  AND ah.trang_thai_xet_duyet = 'DaDuyet' AND aa.trang_thai = 'DaDuyet'
                ORDER BY aa.ma_ung_tuyen DESC LIMIT 1) AS ma_ho_so,
            CASE WHEN EXISTS (SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH ea
                    JOIN HO_SO_THUC_TAP eh ON eh.ma_ho_so = ea.ma_ho_so
                    WHERE eh.ma_nguoi_dung = u.ma_nguoi_dung
                      AND eh.trang_thai_xet_duyet = 'DaDuyet' AND ea.trang_thai = 'DaDuyet')
                THEN 1 ELSE 0 END AS eligible,
            COALESCE((SELECT GROUP_CONCAT(DISTINCT c.ten_ct)
                FROM UNG_TUYEN_CHUONG_TRINH pa
                JOIN HO_SO_THUC_TAP ph ON ph.ma_ho_so = pa.ma_ho_so
                JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = pa.ma_chuong_trinh
                WHERE ph.ma_nguoi_dung = u.ma_nguoi_dung
                  AND ph.trang_thai_xet_duyet = 'DaDuyet' AND pa.trang_thai = 'DaDuyet'), '') AS chuong_trinh
            """ + source + " ORDER BY u.ho_ten, u.ma_nguoi_dung LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page,
                "page_size": page_size}

    def programs(self, owner_id=None):
        scope = " AND h.ma_nguoi_dung = ?" if owner_id is not None else ""
        rows = self.db.execute("""SELECT DISTINCT c.ma_chuong_trinh, c.ten_ct, c.ma_ct
            FROM CHUONG_TRINH_THUC_TAP c
            JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_chuong_trinh = c.ma_chuong_trinh
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            WHERE (a.trang_thai = 'DaDuyet' OR EXISTS
                (SELECT 1 FROM PHU_CAP_THUC_TAP p WHERE p.ma_ung_tuyen = a.ma_ung_tuyen))
            """ + scope + " ORDER BY c.ten_ct", (owner_id,) if owner_id is not None else ()).fetchall()
        return [dict(row) for row in rows]

    def list_records(self, *, owner_id=None, search="", program_id=None, intern_id=None,
                     ky=None, year=None, receipt_status=None, page=1, page_size=25):
        where, params = [], []
        if owner_id is not None:
            where.append("h.ma_nguoi_dung = ?")
            params.append(owner_id)
        if intern_id is not None:
            where.append("h.ma_nguoi_dung = ?")
            params.append(intern_id)
        if search:
            where.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR CAST(u.ma_nguoi_dung AS CHAR) = ?)")
            params.extend([f"%{search}%", f"%{search}%", search])
        if program_id is not None:
            where.append("a.ma_chuong_trinh = ?")
            params.append(program_id)
        if ky:
            where.append("p.ky = ?")
            params.append(ky)
        if year is not None:
            where.append("p.ky LIKE ?")
            params.append(f"{year:04d}-%")
        latest_report = """(SELECT lr.trang_thai_xu_ly FROM PHU_CAP_PHAN_ANH lr
            WHERE lr.allowance_id = p.id ORDER BY lr.id DESC LIMIT 1)"""
        if receipt_status == "ChoXacNhan":
            where.append("p.trang_thai_nhan = 'ChoXacNhan'")
            where.append("NOT EXISTS (SELECT 1 FROM PHU_CAP_PHAN_ANH rr WHERE rr.allowance_id = p.id)")
        elif receipt_status == "DaNhan":
            where.append("p.trang_thai_nhan = 'DaNhan'")
        elif receipt_status == "ChuaNhanDuoc":
            where.append("p.trang_thai_nhan = 'ChuaNhanDuoc'")
            where.append(f"COALESCE({latest_report}, '') <> 'DangXuLy'")
        elif receipt_status == "DangXuLy":
            where.append(f"{latest_report} = 'DangXuLy'")
        suffix = " WHERE " + " AND ".join(where) if where else ""
        source = SELECT_RECORD[SELECT_RECORD.index("FROM PHU_CAP_THUC_TAP"):]
        total = self.db.execute("SELECT COUNT(*) AS total " + source + suffix, params).fetchone()["total"]
        rows = self.db.execute(SELECT_RECORD + suffix + " ORDER BY p.ky DESC, p.id DESC LIMIT ? OFFSET ?",
                               [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [serialize_record(r) for r in rows], "total": total,
                "page": page, "page_size": page_size}

    def detail(self, record_id, owner_id=None):
        row = self._record_row(record_id, owner_id)
        result = serialize_record(row)
        reports = self.db.execute("""SELECT r.id, r.allowance_id, r.noi_dung,
            r.trang_thai_xu_ly, r.ghi_chu_xu_ly, r.created_at, r.updated_at,
            r.reported_by, reporter.ho_ten AS nguoi_phan_anh,
            r.updated_by, updater.ho_ten AS nguoi_xu_ly
            FROM PHU_CAP_PHAN_ANH r
            JOIN NGUOI_DUNG reporter ON reporter.ma_nguoi_dung = r.reported_by
            LEFT JOIN NGUOI_DUNG updater ON updater.ma_nguoi_dung = r.updated_by
            WHERE r.allowance_id = ? ORDER BY r.id DESC""", (record_id,)).fetchall()
        result["reports"] = [dict(r) for r in reports]
        events = self.db.execute("""SELECT id, allowance_id, report_id, event_type, noi_dung,
            actor_id, actor_name, actor_role, so_tien_minor_snapshot, ky_snapshot, created_at
            FROM PHU_CAP_LICH_SU_XU_LY WHERE allowance_id = ? ORDER BY id DESC""",
            (record_id,)).fetchall()
        result["history"] = []
        for event in events:
            item = dict(event)
            if item["so_tien_minor_snapshot"] is not None:
                item["so_tien_snapshot"] = format(Decimal(item.pop("so_tien_minor_snapshot")) / 100, ".2f")
            else:
                item.pop("so_tien_minor_snapshot", None)
            result["history"].append(item)
        return result

    def save(self, data, actor_id, record_id=None):
        self._begin_write()
        try:
            if record_id is None:
                application = self.db.execute("""SELECT a.ma_ung_tuyen, a.ma_ho_so,
                        a.trang_thai, h.trang_thai_xet_duyet, u.vai_tro
                    FROM UNG_TUYEN_CHUONG_TRINH a
                    JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
                    JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
                    WHERE a.ma_ung_tuyen = ?""", (data["ma_ung_tuyen"],)).fetchone()
                if not application:
                    raise HTTPException(404, "Không tìm thấy hồ sơ tham gia chương trình.")
                if (application["trang_thai"] != "DaDuyet"
                        or application["trang_thai_xet_duyet"] != "DaDuyet"
                        or application["vai_tro"] != "ThucTapSinh"):
                    raise HTTPException(409, "Chỉ nhập phụ cấp cho hồ sơ và đơn tham gia đã được duyệt.")
                profile_id = application["ma_ho_so"]
                application_id = application["ma_ung_tuyen"]
                old_row = None
            else:
                old_row = self._record_row(record_id, lock=True)
                if old_row["trang_thai_nhan"] == "DaNhan":
                    raise HTTPException(409, "Khoản phụ cấp đã được TTS xác nhận nhận và đã bị khóa.")
                profile_id = old_row["ma_ho_so"]
                application_id = old_row["ma_ung_tuyen"]

            duplicate = self.db.execute(
                "SELECT id FROM PHU_CAP_THUC_TAP WHERE ma_ho_so = ? AND ky = ? AND id <> ?",
                (profile_id, data["ky"], record_id or 0)).fetchone()
            if duplicate:
                raise HTTPException(409, "Hồ sơ này đã có phụ cấp trong kỳ đã chọn.")
            amount = int(data["so_tien"] * 100)
            now = _now()
            if record_id is None:
                cursor = self.db.execute("""INSERT INTO PHU_CAP_THUC_TAP
                    (ma_ho_so, ma_ung_tuyen, ky, so_tien_minor, ghi_chu,
                     created_by, updated_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (profile_id, application_id, data["ky"], amount, data["ghi_chu"],
                     actor_id, actor_id, now, now))
                record_id = cursor.lastrowid
                self._append_history(allowance_id=record_id, actor_id=actor_id,
                    event_type="TaoPhuCap", note="Tạo khoản phụ cấp.",
                    amount_minor=amount, period=data["ky"], created_at=now)
            else:
                cursor = self.db.execute("""UPDATE PHU_CAP_THUC_TAP
                    SET ky = ?, so_tien_minor = ?, ghi_chu = ?, updated_by = ?, updated_at = ?
                    WHERE id = ? AND trang_thai_nhan <> 'DaNhan'""",
                    (data["ky"], amount, data["ghi_chu"], actor_id, now, record_id))
                if cursor.rowcount != 1:
                    raise HTTPException(409, "Khoản phụ cấp vừa được xác nhận hoặc cập nhật. Tải lại dữ liệu.")
                self._append_history(allowance_id=record_id, actor_id=actor_id,
                    event_type="CapNhatPhuCap", note="HR cập nhật khoản phụ cấp.",
                    amount_minor=amount, period=data["ky"], created_at=now)
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            if record_id is not None and self.db.execute(
                    "SELECT id FROM PHU_CAP_THUC_TAP WHERE ma_ho_so = ? AND ky = ? AND id <> ?",
                    (profile_id, data["ky"], record_id)).fetchone():
                raise HTTPException(409, "Hồ sơ này đã có phụ cấp trong kỳ đã chọn.") from exc
            raise HTTPException(409, "Không thể lưu phụ cấp do dữ liệu liên kết đã thay đổi.") from exc
        except Exception:
            self.db.rollback()
            raise
        return self.detail(record_id)

    def confirm_received(self, record_id, owner_id, actor_id):
        self._begin_write()
        try:
            row = self._record_row(record_id, owner_id, lock=True)
            if row["trang_thai_nhan"] == "DaNhan":
                raise HTTPException(409, "Khoản phụ cấp này đã được xác nhận trước đó.")
            now = _now()
            cursor = self.db.execute("""UPDATE PHU_CAP_THUC_TAP
                SET trang_thai_nhan = 'DaNhan', xac_nhan_boi = ?, xac_nhan_luc = ?
                WHERE id = ? AND trang_thai_nhan <> 'DaNhan'""",
                (actor_id, now, record_id))
            if cursor.rowcount != 1:
                raise HTTPException(409, "Khoản phụ cấp vừa được cập nhật. Tải lại dữ liệu.")
            self._append_history(allowance_id=record_id, actor_id=actor_id,
                event_type="DaNhan", note="Thực tập sinh xác nhận đã nhận phụ cấp.",
                amount_minor=row["so_tien_minor"], period=row["ky"], created_at=now)
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise
        return self.detail(record_id, owner_id=owner_id)

    def report_unreceived(self, record_id, owner_id, actor_id, note):
        self._begin_write()
        try:
            row = self._record_row(record_id, owner_id, lock=True)
            if row["trang_thai_nhan"] == "DaNhan":
                raise HTTPException(409, "Khoản phụ cấp đã xác nhận nhận; không thể tạo phản ánh mới.")
            now = _now()
            cursor = self.db.execute("""INSERT INTO PHU_CAP_PHAN_ANH
                (allowance_id, reported_by, noi_dung, trang_thai_xu_ly, created_at)
                VALUES (?, ?, ?, 'ChoXuLy', ?)""", (record_id, actor_id, note, now))
            report_id = cursor.lastrowid
            updated = self.db.execute("""UPDATE PHU_CAP_THUC_TAP
                SET trang_thai_nhan = 'ChuaNhanDuoc'
                WHERE id = ? AND trang_thai_nhan <> 'DaNhan'""", (record_id,))
            if updated.rowcount != 1:
                raise HTTPException(409, "Khoản phụ cấp vừa được xác nhận. Tải lại dữ liệu.")
            self._append_history(allowance_id=record_id, report_id=report_id,
                actor_id=actor_id, event_type="BaoChuaNhanDuoc", note=note,
                amount_minor=row["so_tien_minor"], period=row["ky"], created_at=now)
            managers = self.db.execute("""SELECT ma_nguoi_dung FROM NGUOI_DUNG
                WHERE vai_tro IN ('Admin', 'HR') AND trang_thai = 'HoatDong'
                ORDER BY ma_nguoi_dung""").fetchall()
            amount_label = format(Decimal(row["so_tien_minor"]) / 100, ".2f")
            message = (f"{row['ho_ten']} báo chưa nhận phụ cấp kỳ {row['ky']} "
                       f"({amount_label} VNĐ), chương trình {row['ten_ct']}, "
                       f"hồ sơ #{row['ma_ho_so']}. Mở Quản lý phụ cấp để xử lý.")
            for manager in managers:
                create_notification(self.db, manager["ma_nguoi_dung"],
                    "Thực tập sinh báo chưa nhận phụ cấp", message,
                    notification_type="allowance_unreceived_report",
                    reference_type="allowance", reference_id=record_id)
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise
        return self.detail(record_id, owner_id=owner_id)

    def list_reports(self, *, status=None, page=1, page_size=25):
        where, params = [], []
        if status:
            where.append("r.trang_thai_xu_ly = ?")
            params.append(status)
        else:
            where.append("r.trang_thai_xu_ly IN ('ChoXuLy', 'DangXuLy')")
        suffix = " WHERE " + " AND ".join(where)
        source = """FROM PHU_CAP_PHAN_ANH r
            JOIN PHU_CAP_THUC_TAP p ON p.id = r.allowance_id
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ung_tuyen = p.ma_ung_tuyen
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
            JOIN NGUOI_DUNG reporter ON reporter.ma_nguoi_dung = r.reported_by
            LEFT JOIN NGUOI_DUNG updater ON updater.ma_nguoi_dung = r.updated_by"""
        total = self.db.execute("SELECT COUNT(*) AS total " + source + suffix, params).fetchone()["total"]
        rows = self.db.execute("""SELECT r.id AS report_id, r.allowance_id, r.noi_dung,
            r.trang_thai_xu_ly, r.ghi_chu_xu_ly, r.created_at AS reported_at,
            r.updated_at, r.reported_by, reporter.ho_ten AS nguoi_phan_anh,
            r.updated_by, updater.ho_ten AS nguoi_xu_ly, p.ky,
            p.so_tien_minor, p.trang_thai_nhan, h.ma_ho_so, h.ma_nguoi_dung,
            u.ho_ten, u.email, c.ten_ct, c.ma_ct
            """ + source + suffix + " ORDER BY r.id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["so_tien"] = format(Decimal(item.pop("so_tien_minor")) / 100, ".2f")
            items.append(item)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update_report(self, report_id, *, status, note, actor_id):
        self._begin_write()
        try:
            report = self.db.execute("SELECT id, allowance_id, trang_thai_xu_ly "
                "FROM PHU_CAP_PHAN_ANH WHERE id = ?" + self._lock_suffix(), (report_id,)).fetchone()
            if not report:
                raise HTTPException(404, "Không tìm thấy phản ánh phụ cấp.")
            allowance = self.db.execute("SELECT ky, so_tien_minor FROM PHU_CAP_THUC_TAP WHERE id = ?",
                                         (report["allowance_id"],)).fetchone()
            if not allowance:
                raise HTTPException(404, "Không tìm thấy thông tin phụ cấp.")
            now = _now()
            cursor = self.db.execute("""UPDATE PHU_CAP_PHAN_ANH
                SET trang_thai_xu_ly = ?, ghi_chu_xu_ly = ?, updated_by = ?, updated_at = ?
                WHERE id = ?""", (status, note, actor_id, now, report_id))
            if cursor.rowcount != 1:
                raise HTTPException(409, "Phản ánh vừa được người khác cập nhật. Tải lại dữ liệu.")
            event_type = "BatDauXuLy" if status == "DangXuLy" else "CapNhatKetQuaXuLy"
            self._append_history(allowance_id=report["allowance_id"], report_id=report_id,
                actor_id=actor_id, event_type=event_type, note=note,
                amount_minor=allowance["so_tien_minor"], period=allowance["ky"], created_at=now)
            self.db.commit()
        except HTTPException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise
        return self.detail(report["allowance_id"])
