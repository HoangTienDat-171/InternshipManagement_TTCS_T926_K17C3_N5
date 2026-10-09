from datetime import datetime
import logging
import sqlite3
from typing import Any, Optional

from fastapi import HTTPException, status

from .notifications import create_notification

logger = logging.getLogger(__name__)

VALID_REQUEST_TYPES = {"CERTIFICATE", "DOCUMENT", "OTHER"}
VALID_STATUSES = {"PENDING", "RESOLVED", "REJECTED"}

TYPE_LABELS = {
    "CERTIFICATE": "Giấy chứng nhận",
    "DOCUMENT": "Tài liệu",
    "OTHER": "Khác",
}

STATUS_LABELS = {
    "PENDING": "Chờ xử lý",
    "RESOLVED": "Đã giải quyết",
    "REJECTED": "Đã từ chối",
}


class SupportRequestService:
    def __init__(self, db):
        self.db = db

    def _begin_write(self, intern_user_id: int):
        if isinstance(self.db, sqlite3.Connection):
            if not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
        else:
            try:
                self.db.execute(
                    "SELECT ma_nguoi_dung FROM NGUOI_DUNG WHERE ma_nguoi_dung = ? FOR UPDATE",
                    (intern_user_id,),
                )
            except Exception:
                pass

    def _format_request(self, item: dict, include_attachments: bool = True) -> dict:
        d = dict(item)
        d["loai_label"] = TYPE_LABELS.get(d.get("loai_yeu_cau"), d.get("loai_yeu_cau"))
        d["trang_thai_label"] = STATUS_LABELS.get(d.get("trang_thai"), d.get("trang_thai"))
        d["noi_dung_phan_hoi"] = d.get("phan_hoi_hr")
        d["ngay_tao"] = d.get("created_at")
        d["ngay_xu_ly"] = d.get("thoi_gian_xu_ly")
        if include_attachments:
            att = self._get_attachments(d["id"])
            d["attachments"] = att
            d["tep_dinh_kem"] = att
            d["so_luong_tep"] = len(att)
        else:
            d["attachments"] = []
            d["tep_dinh_kem"] = []
            d["so_luong_tep"] = 0

        d["nguoi_gui"] = {
            "ma_nguoi_dung": d.get("ma_nguoi_dung"),
            "ho_ten": d.get("intern_name"),
            "email": d.get("intern_email"),
            "so_dien_thoai": d.get("intern_phone"),
        }
        if d.get("handler_name") or d.get("nguoi_xu_ly"):
            d["nguoi_xu_ly_info"] = {
                "ma_nguoi_dung": d.get("nguoi_xu_ly"),
                "ho_ten": d.get("handler_name"),
                "email": d.get("handler_email"),
            }
        else:
            d["nguoi_xu_ly_info"] = None
        return d

    def _get_request_row(self, request_id: int) -> dict:
        row = self.db.execute("""
            SELECT r.*,
                   u.ho_ten AS intern_name,
                   u.email AS intern_email,
                   u.so_dien_thoai AS intern_phone,
                   h.chuyen_nganh,
                   hr.ho_ten AS handler_name,
                   hr.email AS handler_email
            FROM YEU_CAU_HO_TRO r
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = r.ma_nguoi_dung
            LEFT JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            LEFT JOIN NGUOI_DUNG hr ON hr.ma_nguoi_dung = r.nguoi_xu_ly
            WHERE r.id = ?
        """, (request_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy yêu cầu hỗ trợ.")
        return self._format_request(dict(row))

    def _get_attachments(self, request_id: int) -> list[dict]:
        rows = self.db.execute("""
            SELECT id, support_request_id, storage_key, original_filename, mime_type, file_size, created_at
            FROM YEU_CAU_HO_TRO_TEP
            WHERE support_request_id = ?
            ORDER BY id ASC
        """, (request_id,)).fetchall()
        return [dict(r) for r in rows]

    def create_request(
        self,
        intern_user_id: int,
        payload: dict,
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        loai = (payload.get("loai_yeu_cau") or "").strip()
        noi_dung = (payload.get("noi_dung") or "").strip()
        profile_id = payload.get("ma_ho_so")

        if not loai or loai not in VALID_REQUEST_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Loại yêu cầu không hợp lệ. Chỉ chấp nhận: {', '.join(VALID_REQUEST_TYPES)}."
            )

        if not noi_dung:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nội dung yêu cầu không được để trống."
            )

        if len(noi_dung) > 2000:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nội dung yêu cầu không được vượt quá 2000 ký tự."
            )

        # Nếu có gửi ma_ho_so, kiểm tra quyền sở hữu của TTS
        if profile_id:
            profile_row = self.db.execute("""
                SELECT ma_ho_so FROM HO_SO_THUC_TAP
                WHERE ma_ho_so = ? AND ma_nguoi_dung = ?
            """, (profile_id, intern_user_id)).fetchone()
            if not profile_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Hồ sơ thực tập không hợp lệ hoặc không thuộc về bạn."
                )
        else:
            # Tự động gán ma_ho_so của TTS nếu có
            profile_row = self.db.execute("""
                SELECT ma_ho_so FROM HO_SO_THUC_TAP
                WHERE ma_nguoi_dung = ?
                LIMIT 1
            """, (intern_user_id,)).fetchone()
            if profile_row:
                profile_id = profile_row[0]

        # Bắt đầu khóa giao dịch để chống tranh chấp đồng thời
        self._begin_write(intern_user_id)

        # Lấy idempotency_key nếu có
        idempotency_key = (payload.get("idempotency_key") or "").strip()
        idempotency_key = idempotency_key[:128] if idempotency_key else None

        # Nếu có idempotency_key, kiểm tra xem thao tác này đã từng được thực hiện chưa
        if idempotency_key:
            existing_same_key = self.db.execute("""
                SELECT id FROM YEU_CAU_HO_TRO
                WHERE ma_nguoi_dung = ? AND idempotency_key = ?
                LIMIT 1
            """, (intern_user_id, idempotency_key)).fetchone()
            if existing_same_key:
                req_id = existing_same_key["id"] if isinstance(existing_same_key, dict) else existing_same_key[0]
                return self._get_request_row(req_id)

        # Kiểm tra chống duplicate submit: nếu đã có yêu cầu PENDING cùng loại và nội dung
        existing_pending = self.db.execute("""
            SELECT id FROM YEU_CAU_HO_TRO
            WHERE ma_nguoi_dung = ? AND loai_yeu_cau = ? AND noi_dung = ? AND trang_thai = 'PENDING'
            LIMIT 1
        """, (intern_user_id, loai, noi_dung)).fetchone()
        if existing_pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bạn đã có một yêu cầu hỗ trợ tương tự đang chờ xử lý. Vui lòng không gửi trùng lặp."
            )

        try:
            cursor = self.db.execute("""
                INSERT INTO YEU_CAU_HO_TRO
                    (ma_nguoi_dung, ma_ho_so, loai_yeu_cau, noi_dung, trang_thai, idempotency_key)
                VALUES (?, ?, ?, ?, 'PENDING', ?)
            """, (intern_user_id, profile_id, loai, noi_dung, idempotency_key))
            request_id = cursor.lastrowid
        except Exception:
            self.db.rollback()
            if idempotency_key:
                existing_same_key = self.db.execute("""
                    SELECT id FROM YEU_CAU_HO_TRO
                    WHERE ma_nguoi_dung = ? AND idempotency_key = ?
                    LIMIT 1
                """, (intern_user_id, idempotency_key)).fetchone()
                if existing_same_key:
                    req_id = existing_same_key["id"] if isinstance(existing_same_key, dict) else existing_same_key[0]
                    return self._get_request_row(req_id)
            raise

        if attachments:
            for att in attachments:
                self.db.execute("""
                    INSERT INTO YEU_CAU_HO_TRO_TEP
                        (support_request_id, storage_key, original_filename, mime_type, file_size)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    request_id,
                    att["storage_key"],
                    att["original_filename"],
                    att["mime_type"],
                    att["file_size"],
                ))

        self.db.commit()
        req = self._get_request_row(request_id)
        req["attachments"] = self._get_attachments(request_id)
        return req

    def list_my_requests(
        self,
        intern_user_id: int,
        status_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        where_clauses = ["r.ma_nguoi_dung = ?"]
        params: list[Any] = [intern_user_id]

        if status_filter:
            if status_filter not in VALID_STATUSES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Trạng thái lọc không hợp lệ.")
            where_clauses.append("r.trang_thai = ?")
            params.append(status_filter)

        if type_filter:
            if type_filter not in VALID_REQUEST_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Loại yêu cầu lọc không hợp lệ.")
            where_clauses.append("r.loai_yeu_cau = ?")
            params.append(type_filter)

        where_sql = " AND ".join(where_clauses)

        count_row = self.db.execute(f"""
            SELECT COUNT(*) FROM YEU_CAU_HO_TRO r WHERE {where_sql}
        """, tuple(params)).fetchone()
        total = count_row[0] if count_row else 0

        offset = max(0, (page - 1) * page_size)
        query_params = list(params) + [page_size, offset]

        rows = self.db.execute(f"""
            SELECT r.*,
                   u.ho_ten AS intern_name,
                   u.email AS intern_email,
                   u.so_dien_thoai AS intern_phone,
                   hr.ho_ten AS handler_name,
                   hr.email AS handler_email
            FROM YEU_CAU_HO_TRO r
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = r.ma_nguoi_dung
            LEFT JOIN NGUOI_DUNG hr ON hr.ma_nguoi_dung = r.nguoi_xu_ly
            WHERE {where_sql}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ? OFFSET ?
        """, tuple(query_params)).fetchall()

        items = [self._format_request(dict(row)) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_my_request_detail(self, intern_user_id: int, request_id: int) -> dict:
        req = self._get_request_row(request_id)
        if req["ma_nguoi_dung"] != intern_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền xem yêu cầu hỗ trợ của người khác."
            )
        return req

    def list_all_requests(
        self,
        status_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        search: Optional[str] = None,
        intern_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        where_clauses = ["1=1"]
        params: list[Any] = []

        if status_filter:
            if status_filter not in VALID_STATUSES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Trạng thái lọc không hợp lệ.")
            where_clauses.append("r.trang_thai = ?")
            params.append(status_filter)

        if type_filter:
            if type_filter not in VALID_REQUEST_TYPES:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Loại yêu cầu lọc không hợp lệ.")
            where_clauses.append("r.loai_yeu_cau = ?")
            params.append(type_filter)

        if intern_id:
            where_clauses.append("r.ma_nguoi_dung = ?")
            params.append(intern_id)

        if search:
            search_pattern = f"%{search.strip()}%"
            where_clauses.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR r.noi_dung LIKE ?)")
            params.extend([search_pattern, search_pattern, search_pattern])

        if date_from:
            where_clauses.append("r.created_at >= ?")
            params.append(f"{date_from} 00:00:00")

        if date_to:
            where_clauses.append("r.created_at <= ?")
            params.append(f"{date_to} 23:59:59")

        where_sql = " AND ".join(where_clauses)

        count_row = self.db.execute(f"""
            SELECT COUNT(*)
            FROM YEU_CAU_HO_TRO r
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = r.ma_nguoi_dung
            WHERE {where_sql}
        """, tuple(params)).fetchone()
        total = count_row[0] if count_row else 0

        offset = max(0, (page - 1) * page_size)
        query_params = list(params) + [page_size, offset]

        rows = self.db.execute(f"""
            SELECT r.*,
                   u.ho_ten AS intern_name,
                   u.email AS intern_email,
                   u.so_dien_thoai AS intern_phone,
                   h.chuyen_nganh,
                   hr.ho_ten AS handler_name
            FROM YEU_CAU_HO_TRO r
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = r.ma_nguoi_dung
            LEFT JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = r.ma_ho_so
            LEFT JOIN NGUOI_DUNG hr ON hr.ma_nguoi_dung = r.nguoi_xu_ly
            WHERE {where_sql}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT ? OFFSET ?
        """, tuple(query_params)).fetchall()

        items = [self._format_request(dict(row)) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_request_detail_hr(self, request_id: int) -> dict:
        return self._get_request_row(request_id)

    def resolve_request(self, actor_id: int, request_id: int, phan_hoi_hr: str) -> dict:
        req = self._get_request_row(request_id)
        if req["trang_thai"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Yêu cầu hỗ trợ đã kết thúc xử lý (trạng thái: {req['trang_thai']}). Không thể xử lý lại."
            )

        trimmed_response = (phan_hoi_hr or "").strip()
        if not trimmed_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vui lòng nhập nội dung phản hồi xử lý."
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Atomic conditional update chống concurrency race
        cursor = self.db.execute("""
            UPDATE YEU_CAU_HO_TRO
            SET trang_thai = 'RESOLVED',
                phan_hoi_hr = ?,
                nguoi_xu_ly = ?,
                thoi_gian_xu_ly = ?
            WHERE id = ? AND trang_thai = 'PENDING'
        """, (trimmed_response, actor_id, now, request_id))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Yêu cầu hỗ trợ đã được xử lý bởi người khác hoặc trạng thái không còn là Chờ xử lý."
            )

        # Hook gửi thông báo nội bộ cho TTS (chuẩn bị cho US36)
        try:
            create_notification(
                db=self.db,
                user_id=req["ma_nguoi_dung"],
                title="Yêu cầu hỗ trợ đã được giải quyết",
                message=f"Yêu cầu #{request_id} ({TYPE_LABELS.get(req['loai_yeu_cau'], req['loai_yeu_cau'])}) đã được HR xử lý: {trimmed_response[:100]}",
                notification_type="support_request",
                reference_type="support_request",
                reference_id=request_id,
            )
        except Exception as e:
            logger.warning("Không tạo được notification cho support request %s: %s", request_id, e)

        self.db.commit()
        return self._get_request_row(request_id)

    def reject_request(self, actor_id: int, request_id: int, ly_do_tu_choi: str) -> dict:
        req = self._get_request_row(request_id)
        if req["trang_thai"] != "PENDING":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Yêu cầu hỗ trợ đã kết thúc xử lý (trạng thái: {req['trang_thai']}). Không thể xử lý lại."
            )

        trimmed_reason = (ly_do_tu_choi or "").strip()
        if not trimmed_reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vui lòng nhập lý do từ chối yêu cầu."
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Atomic conditional update chống concurrency race
        cursor = self.db.execute("""
            UPDATE YEU_CAU_HO_TRO
            SET trang_thai = 'REJECTED',
                phan_hoi_hr = ?,
                nguoi_xu_ly = ?,
                thoi_gian_xu_ly = ?
            WHERE id = ? AND trang_thai = 'PENDING'
        """, (trimmed_reason, actor_id, now, request_id))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Yêu cầu hỗ trợ đã được xử lý bởi người khác hoặc trạng thái không còn là Chờ xử lý."
            )

        # Hook gửi thông báo nội bộ cho TTS (chuẩn bị cho US36)
        try:
            create_notification(
                db=self.db,
                user_id=req["ma_nguoi_dung"],
                title="Yêu cầu hỗ trợ đã bị từ chối",
                message=f"Yêu cầu #{request_id} ({TYPE_LABELS.get(req['loai_yeu_cau'], req['loai_yeu_cau'])}) bị từ chối với lý do: {trimmed_reason[:100]}",
                notification_type="support_request",
                reference_type="support_request",
                reference_id=request_id,
            )
        except Exception as e:
            logger.warning("Không tạo được notification cho support request %s: %s", request_id, e)

        self.db.commit()
        return self._get_request_row(request_id)

    def get_attachment(self, request_id: int, file_id: int, user: dict) -> dict:
        req = self._get_request_row(request_id)
        role = user.get("vai_tro")
        user_id = user.get("ma_nguoi_dung")

        # Phân quyền: TTS chỉ được tải file của chính mình; HR/Admin được tải tất cả; Mentor không có quyền
        if role == "ThucTapSinh":
            if req["ma_nguoi_dung"] != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập tệp đính kèm này.")
        elif role in ("HR", "Admin"):
            pass
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập tệp đính kèm.")

        file_row = self.db.execute("""
            SELECT * FROM YEU_CAU_HO_TRO_TEP
            WHERE id = ? AND support_request_id = ?
        """, (file_id, request_id)).fetchone()

        if not file_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tệp đính kèm.")

        return dict(file_row)
