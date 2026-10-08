"""US25/26 share one profile/month allowance ledger. Amounts are integer minor units."""
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from fastapi import HTTPException


SELECT_RECORD = """
    SELECT p.*, a.ma_chuong_trinh, c.ma_ct, c.ten_ct,
           h.ma_nguoi_dung, u.ho_ten, u.email,
           creator.ho_ten AS nguoi_tao, updater.ho_ten AS nguoi_cap_nhat
    FROM PHU_CAP_THUC_TAP p
    JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
    JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
    JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ung_tuyen = p.ma_ung_tuyen
    JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
    JOIN NGUOI_DUNG creator ON creator.ma_nguoi_dung = p.created_by
    JOIN NGUOI_DUNG updater ON updater.ma_nguoi_dung = p.updated_by
"""


def serialize_record(row):
    result = dict(row)
    result["so_tien"] = format(Decimal(result.pop("so_tien_minor")) / 100, ".2f")
    return result


class AllowanceService:
    def __init__(self, db):
        self.db = db

    def options(self, search="", program_id=None, page=1, page_size=25):
        """Approved participation, including history, for HR entry; never invent profiles."""
        where = ["a.trang_thai = 'DaDuyet'", "h.trang_thai_xet_duyet = 'DaDuyet'",
                 "u.vai_tro = 'ThucTapSinh'"]
        params = []
        if search:
            where.append("(u.ho_ten LIKE ? OR u.email LIKE ?)")
            params.extend([f"%{search}%"] * 2)
        if program_id is not None:
            where.append("a.ma_chuong_trinh = ?")
            params.append(program_id)
        source = """FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE """ + " AND ".join(where)
        total = self.db.execute("SELECT COUNT(*) AS total " + source, params).fetchone()["total"]
        rows = self.db.execute("""SELECT a.ma_ung_tuyen, h.ma_ho_so, u.ho_ten, u.email,
            a.ma_chuong_trinh, c.ten_ct, c.ma_ct, c.ngay_bat_dau, c.ngay_ket_thuc
            """ + source + " ORDER BY u.ho_ten, a.ma_ung_tuyen LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}

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

    def list_records(self, *, owner_id=None, search="", program_id=None, ky=None,
                     year=None, page=1, page_size=25):
        where, params = [], []
        if owner_id is not None:
            where.append("h.ma_nguoi_dung = ?")
            params.append(owner_id)
        if search:
            where.append("(u.ho_ten LIKE ? OR u.email LIKE ?)")
            params.extend([f"%{search}%"] * 2)
        if program_id is not None:
            where.append("a.ma_chuong_trinh = ?")
            params.append(program_id)
        if ky:
            where.append("p.ky = ?")
            params.append(ky)
        if year is not None:
            where.append("p.ky LIKE ?")
            params.append(f"{year:04d}-%")
        suffix = " WHERE " + " AND ".join(where) if where else ""
        # Count and items share the identical scope and filters.
        source = SELECT_RECORD[SELECT_RECORD.index("FROM PHU_CAP_THUC_TAP"):]
        total = self.db.execute("SELECT COUNT(*) AS total " + source + suffix, params).fetchone()["total"]
        rows = self.db.execute(SELECT_RECORD + suffix + " ORDER BY p.ky DESC, p.id DESC LIMIT ? OFFSET ?",
                               [*params, page_size, (page - 1) * page_size]).fetchall()
        return {"items": [serialize_record(r) for r in rows], "total": total,
                "page": page, "page_size": page_size}

    def detail(self, record_id, owner_id=None):
        row = self.db.execute(SELECT_RECORD + " WHERE p.id = ?", (record_id,)).fetchone()
        # Identical response for missing and another intern's record avoids disclosing its existence.
        if not row or (owner_id is not None and row["ma_nguoi_dung"] != owner_id):
            raise HTTPException(404, "Không tìm thấy thông tin phụ cấp.")
        return serialize_record(row)

    def save(self, data, actor_id, record_id=None):
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
        else:
            existing = self.detail(record_id)
            profile_id = existing["ma_ho_so"]
        duplicate = self.db.execute(
            "SELECT id FROM PHU_CAP_THUC_TAP WHERE ma_ho_so = ? AND ky = ? AND id <> ?",
            (profile_id, data["ky"], record_id or 0)).fetchone()
        if duplicate:
            raise HTTPException(409, "Hồ sơ này đã có phụ cấp trong kỳ đã chọn.")
        amount = int(data["so_tien"] * 100)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        try:
            if record_id is None:
                cursor = self.db.execute("""INSERT INTO PHU_CAP_THUC_TAP
                    (ma_ho_so, ma_ung_tuyen, ky, so_tien_minor, ghi_chu,
                     created_by, updated_by, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (profile_id, application["ma_ung_tuyen"], data["ky"], amount,
                     data["ghi_chu"], actor_id, actor_id, now, now))
                record_id = cursor.lastrowid
            else:
                self.db.execute("""UPDATE PHU_CAP_THUC_TAP
                    SET ky = ?, so_tien_minor = ?, ghi_chu = ?, updated_by = ?, updated_at = ?
                    WHERE id = ?""", (data["ky"], amount, data["ghi_chu"], actor_id, now, record_id))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            # MySQL compatibility wrapper also maps duplicate/FK/check errors to IntegrityError.
            if self.db.execute("SELECT id FROM PHU_CAP_THUC_TAP WHERE ma_ho_so = ? AND ky = ? AND id <> ?",
                               (profile_id, data["ky"], record_id or 0)).fetchone():
                raise HTTPException(409, "Hồ sơ này đã có phụ cấp trong kỳ đã chọn.") from exc
            raise HTTPException(409, "Không thể lưu phụ cấp do dữ liệu liên kết đã thay đổi.") from exc
        except Exception:
            self.db.rollback()
            raise
        return self.detail(record_id)
