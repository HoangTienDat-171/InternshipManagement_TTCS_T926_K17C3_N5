import sqlite3
from datetime import timedelta

from fastapi import HTTPException, status

from . import database
from .notifications import create_notification


class WeeklyReportService:
    """US17 weekly-report rules scoped to the authenticated intern."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _select() -> str:
        return """
            SELECT r.ma_bao_cao AS id,
                   r.ma_ho_so AS internship_profile_id,
                   r.ma_chuong_trinh AS program_id,
                   p.ten_ct AS program_name,
                   r.week_start, r.week_end,
                   r.work_content, r.results, r.difficulties,
                   r.trang_thai AS status, r.submitted_at,
                   r.attachment_original_name,
                   r.attachment_mime_type,
                   r.attachment_file_size,
                   CASE WHEN r.attachment_storage_key IS NULL THEN 0 ELSE 1 END AS has_attachment,
                   r.created_at, r.updated_at,
                   h.ma_nguoi_dung AS intern_user_id
            FROM BAO_CAO_TUAN r
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = r.ma_chuong_trinh
        """

    def _profile(self, user_id: int) -> dict:
        row = self.db.execute("""
            SELECT ma_ho_so, ma_nguoi_dung, trang_thai_xet_duyet
            FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?
        """, (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")
        if row["trang_thai_xet_duyet"] != "DaDuyet":
            raise HTTPException(status_code=409, detail="Hồ sơ phải được duyệt trước khi tạo báo cáo tuần.")
        return dict(row)

    def list_programs(self, user_id: int) -> list[dict]:
        profile = self._profile(user_id)
        rows = self.db.execute("""
            SELECT p.ma_chuong_trinh AS id, p.ten_ct AS name,
                   p.ngay_bat_dau AS start_date, p.ngay_ket_thuc AS end_date
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
            ORDER BY a.ngay_xet_duyet DESC, a.ma_ung_tuyen DESC
        """, (profile["ma_ho_so"],)).fetchall()
        return [dict(row) for row in rows]

    def _approved_program(self, profile_id: int, program_id: int) -> dict:
        row = self.db.execute("""
            SELECT p.ma_chuong_trinh, p.ten_ct, p.ngay_bat_dau, p.ngay_ket_thuc
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE a.ma_ho_so = ? AND a.ma_chuong_trinh = ? AND a.trang_thai = 'DaDuyet'
        """, (profile_id, program_id)).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="Chương trình không thuộc hồ sơ thực tập đã được duyệt của bạn.")
        return dict(row)

    def _fetch(self, report_id: int, *, for_update: bool = False) -> dict:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        row = self.db.execute(self._select() + " WHERE r.ma_bao_cao = ?" + lock, (report_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy báo cáo tuần.")
        return dict(row)

    @staticmethod
    def _ensure_owner(report: dict, user_id: int) -> None:
        if report["intern_user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập báo cáo tuần này.")

    @staticmethod
    def _public(report: dict) -> dict:
        result = dict(report)
        result.pop("intern_user_id", None)
        result["has_attachment"] = bool(result["has_attachment"])
        return result

    def create(self, intern: dict, data) -> dict:
        profile = self._profile(intern["ma_nguoi_dung"])
        self._approved_program(profile["ma_ho_so"], data.program_id)
        week_end = data.week_start + timedelta(days=6)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            cursor = self.db.execute("""
                INSERT INTO BAO_CAO_TUAN
                    (ma_ho_so, ma_chuong_trinh, week_start, week_end,
                     work_content, results, difficulties, trang_thai)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'DRAFT')
            """, (
                profile["ma_ho_so"], data.program_id,
                data.week_start.isoformat(), week_end.isoformat(),
                data.work_content, data.results, data.difficulties,
            ))
            report_id = cursor.lastrowid
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Báo cáo cho chương trình và tuần này đã tồn tại.") from exc
        except Exception:
            self.db.rollback()
            raise
        return self.get(report_id, intern["ma_nguoi_dung"])

    def list(self, user_id: int, report_status: str | None = None, program_id: int | None = None) -> list[dict]:
        clauses = ["h.ma_nguoi_dung = ?"]
        params: list = [user_id]
        if report_status:
            clauses.append("r.trang_thai = ?")
            params.append(report_status)
        if program_id:
            clauses.append("r.ma_chuong_trinh = ?")
            params.append(program_id)
        rows = self.db.execute(
            self._select() + " WHERE " + " AND ".join(clauses)
            + " ORDER BY r.week_start DESC, r.ma_bao_cao DESC",
            tuple(params),
        ).fetchall()
        return [self._public(dict(row)) for row in rows]

    def get(self, report_id: int, user_id: int) -> dict:
        report = self._fetch(report_id)
        self._ensure_owner(report, user_id)
        return self._public(report)

    def update(self, report_id: int, intern: dict, data) -> dict:
        changes = data.model_dump(exclude_unset=True)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            report = self._fetch(report_id, for_update=True)
            self._ensure_owner(report, intern["ma_nguoi_dung"])
            if report["status"] != "DRAFT":
                raise HTTPException(status_code=409, detail="Báo cáo đã nộp và không thể chỉnh sửa.")
            columns = {"work_content": "work_content", "results": "results", "difficulties": "difficulties"}
            assignments = [f"{columns[field]} = ?" for field in changes]
            params = list(changes.values())
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            params.append(report_id)
            self.db.execute(
                f"UPDATE BAO_CAO_TUAN SET {', '.join(assignments)} WHERE ma_bao_cao = ? AND trang_thai = 'DRAFT'",
                tuple(params),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get(report_id, intern["ma_nguoi_dung"])

    def submit(self, report_id: int, intern: dict) -> dict:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            report = self._fetch(report_id, for_update=True)
            self._ensure_owner(report, intern["ma_nguoi_dung"])
            if report["status"] != "DRAFT":
                raise HTTPException(status_code=409, detail="Báo cáo tuần đã được nộp trước đó.")
            if not report["work_content"].strip() or not report["results"].strip():
                raise HTTPException(status_code=422, detail="Vui lòng nhập nội dung công việc và kết quả đạt được trước khi nộp.")
            cursor = self.db.execute("""
                UPDATE BAO_CAO_TUAN
                SET trang_thai = 'SUBMITTED', submitted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ma_bao_cao = ? AND trang_thai = 'DRAFT'
            """, (report_id,))
            if cursor.rowcount != 1:
                raise HTTPException(status_code=409, detail="Báo cáo tuần đã được nộp trước đó.")
            mentors = self.db.execute("""
                SELECT ma_nguoi_dung_mentor FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so = ?
            """, (report["internship_profile_id"],)).fetchall()
            for mentor in mentors:
                create_notification(
                    self.db,
                    mentor["ma_nguoi_dung_mentor"],
                    "Báo cáo tuần mới",
                    f"{intern['ho_ten']} đã nộp báo cáo tuần {report['week_start']} – {report['week_end']}.",
                    notification_type="WEEKLY_REPORT_SUBMITTED",
                    reference_type="weekly_report",
                    reference_id=report_id,
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get(report_id, intern["ma_nguoi_dung"])

    def attachment_record(self, report_id: int, user_id: int, *, for_update: bool = False) -> dict:
        report = self._fetch(report_id, for_update=for_update)
        self._ensure_owner(report, user_id)
        return report
