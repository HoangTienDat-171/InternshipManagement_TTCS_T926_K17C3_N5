from datetime import date, datetime
import logging
from typing import Any, Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def get_approved_leaves_for_profile(db, profile_id: int, start_date: date, end_date: date) -> list[dict]:
    """
    Hàm tiện ích canonical phục vụ US22 sau này:
    Chỉ lấy những đơn nghỉ phép ĐÃ ĐƯỢC DUYỆT (DaDuyet).
    Không lấy ChoDuyet, TuChoi hay DaHuy.
    TUYỆT ĐỐI không thay đổi dữ liệu bảng CHAM_CONG.
    """
    rows = db.execute("""
        SELECT r.id, r.ma_ung_tuyen, r.ma_ho_so, r.ma_chuong_trinh,
               r.start_date, r.end_date, r.ly_do, r.trang_thai,
               r.reviewed_by, r.reviewed_at, r.created_at,
               c.ten_ct, c.ma_ct
        FROM YEU_CAU_NGHI_PHEP r
        JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = r.ma_chuong_trinh
        WHERE r.ma_ho_so = ?
          AND r.trang_thai = 'DaDuyet'
          AND r.start_date <= ?
          AND r.end_date >= ?
        ORDER BY r.start_date ASC
    """, (profile_id, end_date.isoformat(), start_date.isoformat())).fetchall()
    return [dict(row) for row in rows]


class LeaveService:
    def __init__(self, db):
        self.db = db

    def _get_intern_profile(self, intern_user_id: int) -> dict:
        row = self.db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, h.trang_thai_xet_duyet, h.trang_thai_thuc_tap
            FROM HO_SO_THUC_TAP h
            WHERE h.ma_nguoi_dung = ?
        """, (intern_user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ thực tập sinh.")
        if row["trang_thai_xet_duyet"] != "DaDuyet":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hồ sơ thực tập sinh chưa được duyệt.")
        return dict(row)

    def list_eligible_programs(self, intern_user_id: int, today: Optional[date] = None) -> list[dict]:
        """Return approved applications for programs active on the current day."""
        profile = self._get_intern_profile(intern_user_id)
        current_day = (today or date.today()).isoformat()
        rows = self.db.execute("""
            SELECT a.ma_ung_tuyen, a.ma_chuong_trinh, c.ma_ct, c.ten_ct,
                   c.ngay_bat_dau, c.ngay_ket_thuc
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE a.ma_ho_so = ?
              AND a.trang_thai = 'DaDuyet'
              AND c.trang_thai = 'DangMo'
              AND c.ngay_bat_dau IS NOT NULL
              AND c.ngay_ket_thuc IS NOT NULL
              AND c.ngay_bat_dau <= ?
              AND c.ngay_ket_thuc >= ?
            ORDER BY c.ngay_bat_dau DESC, a.ma_ung_tuyen DESC
        """, (profile["ma_ho_so"], current_day, current_day)).fetchall()
        return [dict(row) for row in rows]

    def create_request(
        self,
        intern_user_id: int,
        payload: dict,
        today: Optional[date] = None,
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        profile = self._get_intern_profile(intern_user_id)
        profile_id = profile["ma_ho_so"]

        application_id = payload.get("ma_ung_tuyen")
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")
        reason = (payload.get("ly_do") or "").strip()

        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lý do nghỉ phép không được để trống.")

        # Server derives owner, program, dates from database
        app_row = self.db.execute("""
            SELECT a.ma_ung_tuyen, a.ma_ho_so, a.ma_chuong_trinh, a.trang_thai AS app_status,
                   c.ten_ct, c.ma_ct, c.ngay_bat_dau, c.ngay_ket_thuc, c.trang_thai AS program_status
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE a.ma_ung_tuyen = ?
        """, (application_id,)).fetchone()
        if not app_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đơn ứng tuyển chương trình thực tập.")

        # Ownership / IDOR check: Intern can only request leave for their own application
        if app_row["ma_ho_so"] != profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền đăng ký nghỉ phép cho đơn ứng tuyển này.",
            )

        # Application state check: Only approved application is eligible
        if app_row["app_status"] != "DaDuyet":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chỉ đơn ứng tuyển đã được duyệt mới có thể đăng ký nghỉ phép.",
            )

        current_day = today or date.today()
        if app_row["program_status"] != "DangMo":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chỉ có thể đăng ký nghỉ phép trong chương trình đang mở.",
            )

        prog_start = _as_date(app_row["ngay_bat_dau"])
        prog_end = _as_date(app_row["ngay_ket_thuc"])
        if not prog_start or not prog_end or not (prog_start <= current_day <= prog_end):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chỉ có thể đăng ký nghỉ phép trong thời gian chương trình đang diễn ra.",
            )

        req_start = _as_date(start_date)
        req_end = _as_date(end_date)
        if not req_start or not req_end:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ngày nghỉ không hợp lệ.")
        if req_start > req_end:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ngày bắt đầu không được sau ngày kết thúc.")

        # Requested leave dates must stay inside the active program period.
        if prog_start and req_start < prog_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ngày bắt đầu nghỉ ({req_start.isoformat()}) không được trước ngày bắt đầu chương trình ({prog_start.isoformat()}).",
            )
        if prog_end and req_end > prog_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ngày kết thúc nghỉ ({req_end.isoformat()}) không được sau ngày kết thúc chương trình ({prog_end.isoformat()}).",
            )

        # Duplicate submission check (prevent accidental double submit)
        existing_dup = self.db.execute("""
            SELECT id FROM YEU_CAU_NGHI_PHEP
            WHERE ma_ung_tuyen = ? AND start_date = ? AND end_date = ? AND trang_thai = 'ChoDuyet'
            LIMIT 1
        """, (application_id, req_start.isoformat(), req_end.isoformat())).fetchone()
        if existing_dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Đơn xin nghỉ phép cho khoảng thời gian này đang chờ xét duyệt.",
            )

        cursor = self.db.execute("""
            INSERT INTO YEU_CAU_NGHI_PHEP (
                ma_ung_tuyen, ma_ho_so, ma_chuong_trinh, start_date, end_date, ly_do, trang_thai
            ) VALUES (?, ?, ?, ?, ?, ?, 'ChoDuyet')
        """, (
            application_id,
            profile_id,
            app_row["ma_chuong_trinh"],
            req_start.isoformat(),
            req_end.isoformat(),
            reason,
        ))
        request_id = cursor.lastrowid
        for attachment in attachments or []:
            self.db.execute("""
                INSERT INTO YEU_CAU_NGHI_PHEP_TEP
                    (leave_request_id, storage_key, original_filename, mime_type, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (
                request_id,
                attachment["storage_key"],
                attachment["original_filename"],
                attachment["mime_type"],
                attachment["file_size"],
            ))
        self.db.commit()

        return self.get_intern_request_detail(intern_user_id, request_id)

    def list_intern_requests(self, intern_user_id: int) -> list[dict]:
        profile = self._get_intern_profile(intern_user_id)
        profile_id = profile["ma_ho_so"]

        rows = self.db.execute("""
            SELECT r.id, r.ma_ung_tuyen, r.ma_ho_so, r.ma_chuong_trinh,
                   r.start_date, r.end_date, r.ly_do, r.trang_thai,
                   r.reviewed_by, r.reviewed_at, r.ly_do_tu_choi, r.created_at,
                   c.ten_ct, c.ma_ct, reviewer.ho_ten AS reviewer_name,
                   (SELECT COUNT(*) FROM YEU_CAU_NGHI_PHEP_TEP a WHERE a.leave_request_id = r.id) AS attachment_count
            FROM YEU_CAU_NGHI_PHEP r
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = r.ma_chuong_trinh
            LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung = r.reviewed_by
            WHERE r.ma_ho_so = ?
            ORDER BY r.created_at DESC, r.id DESC
        """, (profile_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_intern_request_detail(self, intern_user_id: int, request_id: int) -> dict:
        profile = self._get_intern_profile(intern_user_id)
        profile_id = profile["ma_ho_so"]

        row = self.db.execute("""
            SELECT r.id, r.ma_ung_tuyen, r.ma_ho_so, r.ma_chuong_trinh,
                   r.start_date, r.end_date, r.ly_do, r.trang_thai,
                   r.reviewed_by, r.reviewed_at, r.ly_do_tu_choi, r.created_at,
                   c.ten_ct, c.ma_ct, reviewer.ho_ten AS reviewer_name,
                   h.ma_nguoi_dung AS intern_user_id,
                   (SELECT COUNT(*) FROM YEU_CAU_NGHI_PHEP_TEP a WHERE a.leave_request_id = r.id) AS attachment_count
            FROM YEU_CAU_NGHI_PHEP r
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = r.ma_chuong_trinh
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung = r.reviewed_by
            WHERE r.id = ?
        """, (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đơn xin nghỉ phép.")
        if row["ma_ho_so"] != profile_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền truy cập đơn nghỉ phép này.")
        result = dict(row)
        result["attachments"] = self._list_attachments(request_id)
        return result

    def cancel_intern_request(self, intern_user_id: int, request_id: int) -> dict:
        profile = self._get_intern_profile(intern_user_id)
        profile_id = profile["ma_ho_so"]

        row = self.db.execute("""
            SELECT id, ma_ho_so, trang_thai
            FROM YEU_CAU_NGHI_PHEP
            WHERE id = ?
        """, (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đơn xin nghỉ phép.")
        if row["ma_ho_so"] != profile_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền hủy đơn nghỉ phép này.")

        current_status = row["trang_thai"]
        if current_status == "DaHuy":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Đơn nghỉ phép này đã được hủy trước đó.")
        if current_status != "ChoDuyet":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Chỉ có thể hủy đơn nghỉ phép đang ở trạng thái Chờ duyệt (hiện tại: {current_status}).",
            )

        # Atomic state transition
        cursor = self.db.execute("""
            UPDATE YEU_CAU_NGHI_PHEP
            SET trang_thai = 'DaHuy', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND ma_ho_so = ? AND trang_thai = 'ChoDuyet'
        """, (request_id, profile_id))
        if cursor.rowcount == 0:
            # Recheck state to return accurate deterministic error
            fresh = self.db.execute("SELECT trang_thai FROM YEU_CAU_NGHI_PHEP WHERE id = ?", (request_id,)).fetchone()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Không thể hủy đơn nghỉ phép; trạng thái đơn đã thay đổi thành {fresh['trang_thai'] if fresh else 'không rõ'}.",
            )
        self.db.commit()
        return self.get_intern_request_detail(intern_user_id, request_id)

    def list_all_requests(
        self,
        status_filter: Optional[str] = None,
        program_id: Optional[int] = None,
    ) -> list[dict]:
        query = """
            SELECT r.id, r.ma_ung_tuyen, r.ma_ho_so, r.ma_chuong_trinh,
                   r.start_date, r.end_date, r.ly_do, r.trang_thai,
                   r.reviewed_by, r.reviewed_at, r.ly_do_tu_choi, r.created_at,
                   c.ten_ct, c.ma_ct, u.ho_ten AS intern_name, u.email AS intern_email,
                   reviewer.ho_ten AS reviewer_name,
                   (SELECT COUNT(*) FROM YEU_CAU_NGHI_PHEP_TEP a WHERE a.leave_request_id = r.id) AS attachment_count
            FROM YEU_CAU_NGHI_PHEP r
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = r.ma_chuong_trinh
            LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung = r.reviewed_by
            WHERE 1=1
        """
        params = []
        if status_filter:
            query += " AND r.trang_thai = ?"
            params.append(status_filter)
        if program_id:
            query += " AND r.ma_chuong_trinh = ?"
            params.append(program_id)

        query += " ORDER BY r.created_at DESC, r.id DESC"
        rows = self.db.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def get_request_for_review(self, request_id: int) -> dict:
        row = self.db.execute("""
            SELECT r.id, r.ma_ung_tuyen, r.ma_ho_so, r.ma_chuong_trinh,
                   r.start_date, r.end_date, r.ly_do, r.trang_thai,
                   r.reviewed_by, r.reviewed_at, r.ly_do_tu_choi, r.created_at,
                   c.ten_ct, c.ma_ct, u.ho_ten AS intern_name, u.email AS intern_email,
                   reviewer.ho_ten AS reviewer_name, h.ma_nguoi_dung AS intern_user_id,
                   (SELECT COUNT(*) FROM YEU_CAU_NGHI_PHEP_TEP a WHERE a.leave_request_id = r.id) AS attachment_count
            FROM YEU_CAU_NGHI_PHEP r
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh = r.ma_chuong_trinh
            LEFT JOIN NGUOI_DUNG reviewer ON reviewer.ma_nguoi_dung = r.reviewed_by
            WHERE r.id = ?
        """, (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đơn xin nghỉ phép.")
        result = dict(row)
        result["attachments"] = self._list_attachments(request_id)
        return result

    def _list_attachments(self, request_id: int) -> list[dict]:
        rows = self.db.execute("""
            SELECT id, original_filename, mime_type, file_size, created_at
            FROM YEU_CAU_NGHI_PHEP_TEP
            WHERE leave_request_id = ?
            ORDER BY id ASC
        """, (request_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_attachment(self, request_id: int, attachment_id: int) -> dict:
        row = self.db.execute("""
            SELECT id, leave_request_id, storage_key, original_filename, mime_type, file_size
            FROM YEU_CAU_NGHI_PHEP_TEP
            WHERE id = ? AND leave_request_id = ?
        """, (attachment_id, request_id)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu minh chứng.")
        return dict(row)

    def review_request(
        self,
        reviewer_user_id: int,
        request_id: int,
        decision: str,
        ly_do_tu_choi: Optional[str] = None,
    ) -> dict:
        if decision not in ("DaDuyet", "TuChoi"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quyết định xét duyệt không hợp lệ.")

        req = self.get_request_for_review(request_id)

        # Self-approval protection: Reviewer cannot approve/reject their own leave request
        if reviewer_user_id == req["intern_user_id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Người xét duyệt không được tự duyệt đơn nghỉ phép của chính mình.",
            )

        if req["trang_thai"] != "ChoDuyet":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Đơn nghỉ phép này đã được xử lý (trạng thái: {req['trang_thai']}). Không thể xét duyệt lại.",
            )

        rejection_reason = (ly_do_tu_choi or "").strip() if decision == "TuChoi" else None
        if decision == "TuChoi" and not rejection_reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cần cung cấp lý do từ chối đơn nghỉ phép.",
            )

        # Atomic CAS state transition: only succeeds if still ChoDuyet
        cursor = self.db.execute("""
            UPDATE YEU_CAU_NGHI_PHEP
            SET trang_thai = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP,
                ly_do_tu_choi = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND trang_thai = 'ChoDuyet'
        """, (decision, reviewer_user_id, rejection_reason, request_id))

        if cursor.rowcount == 0:
            fresh = self.db.execute("SELECT trang_thai FROM YEU_CAU_NGHI_PHEP WHERE id = ?", (request_id,)).fetchone()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Đơn nghỉ phép đã được thay đổi trạng thái trước đó (hiện tại: {fresh['trang_thai'] if fresh else 'không rõ'}).",
            )

        self.db.commit()
        return self.get_request_for_review(request_id)
