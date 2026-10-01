import os
import re
import sqlite3
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..database import DB_FILE, get_db
from ..notifications import create_notification
from .document_routes import MAX_FILE_SIZE, valid_file_content
from ..security import require_role

router = APIRouter(prefix="/api/contracts", tags=["Internship Contracts - US09"])
CONTRACT_STORAGE_ROOT = Path(DB_FILE).parent / "uploads" / "contracts"
CONTRACT_MIME_TYPE = "application/pdf"
CONTRACT_STATUS = "PENDING_CONFIRMATION"
FRONTEND_URL = os.getenv("IMS_PORTAL_URL", "http://127.0.0.1:3000").strip().rstrip("/")


def _contract_select():
    return """
        SELECT c.ma_hop_dong, c.ma_ho_so, c.original_file_name, c.storage_key, c.mime_type,
               c.file_size, c.trang_thai, c.uploaded_by, c.uploaded_at,
               u.ma_nguoi_dung, u.ho_ten, u.email,
               (SELECT p.ten_ct
                FROM UNG_TUYEN_CHUONG_TRINH a
                JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE a.ma_ho_so = c.ma_ho_so AND a.trang_thai = 'DaDuyet'
                ORDER BY a.ngay_xet_duyet DESC, a.ma_ung_tuyen DESC LIMIT 1) AS ten_chuong_trinh,
               (SELECT p.ngay_bat_dau
                FROM UNG_TUYEN_CHUONG_TRINH a
                JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE a.ma_ho_so = c.ma_ho_so AND a.trang_thai = 'DaDuyet'
                ORDER BY a.ngay_xet_duyet DESC, a.ma_ung_tuyen DESC LIMIT 1) AS ngay_bat_dau,
               (SELECT p.ngay_ket_thuc
                FROM UNG_TUYEN_CHUONG_TRINH a
                JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE a.ma_ho_so = c.ma_ho_so AND a.trang_thai = 'DaDuyet'
                ORDER BY a.ngay_xet_duyet DESC, a.ma_ung_tuyen DESC LIMIT 1) AS ngay_ket_thuc,
               d.ten_phong_ban
        FROM HOP_DONG_THUC_TAP c
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = c.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        LEFT JOIN PHONG_BAN d ON d.ma_phong_ban = u.ma_phong_ban
    """


def _public_contract(row):
    result = dict(row)
    result.pop("storage_key", None)
    return result


def _contract_file_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", storage_key or ""):
        raise HTTPException(status_code=404, detail="Không tìm thấy hợp đồng.")
    root = CONTRACT_STORAGE_ROOT.resolve()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp hợp đồng trên máy chủ.")
    return path


@router.get("")
def list_contracts(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    base_query = _contract_select()
    total = db.execute("SELECT COUNT(*) AS total_items FROM HOP_DONG_THUC_TAP").fetchone()["total_items"]
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, total_pages) if total_pages else 1
    rows = db.execute(
        base_query + " ORDER BY c.uploaded_at DESC, c.ma_hop_dong DESC LIMIT ? OFFSET ?",
        (page_size, (effective_page - 1) * page_size),
    ).fetchall()
    return {
        "items": [_public_contract(row) for row in rows],
        "page": effective_page,
        "pageSize": page_size,
        "totalItems": total,
        "totalPages": total_pages,
    }


@router.get("/mine")
def get_my_contract(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request, "ThucTapSinh")
    row = db.execute(
        _contract_select() + " WHERE h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh' "
        "ORDER BY c.uploaded_at DESC, c.ma_hop_dong DESC LIMIT 1",
        (user["ma_nguoi_dung"],),
    ).fetchone()
    return _public_contract(row) if row else None


@router.get("/mine/all")
def list_my_contracts(request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request, "ThucTapSinh")
    rows = db.execute(
        _contract_select() + " WHERE h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh' "
        "ORDER BY c.uploaded_at DESC, c.ma_hop_dong DESC",
        (user["ma_nguoi_dung"],),
    ).fetchall()
    return [_public_contract(row) for row in rows]


@router.post("/{contract_id}/decision")
def decide_contract(
    contract_id: int,
    request: Request,
    decision: Literal["CONFIRMED", "REJECTED"] = Body(..., embed=True),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "ThucTapSinh")
    row = db.execute(
        _contract_select() + " WHERE c.ma_hop_dong = ? AND h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh'",
        (contract_id, user["ma_nguoi_dung"]),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy hợp đồng.")
    if row["trang_thai"] != CONTRACT_STATUS:
        raise HTTPException(status_code=409, detail="Hợp đồng đã được xác nhận hoặc từ chối.")

    updated = db.execute(
        """
        UPDATE HOP_DONG_THUC_TAP
        SET trang_thai = ?, updated_at = CURRENT_TIMESTAMP
        WHERE ma_hop_dong = ? AND trang_thai = ?
        """,
        (decision, contract_id, CONTRACT_STATUS),
    )
    if updated.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Hợp đồng đã được xác nhận hoặc từ chối.")

    db.commit()
    result = db.execute(
        _contract_select() + " WHERE c.ma_hop_dong = ?", (contract_id,),
    ).fetchone()
    return _public_contract(result)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_contract(
    request: Request,
    ma_ho_so: int = Form(...),
    file: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "Admin", "HR")
    original_name = file.filename or ""
    if (
        not original_name
        or len(original_name) > 255
        or "/" in original_name
        or "\\" in original_name
        or ":" in original_name
        or any(ord(char) < 32 for char in original_name)
        or Path(original_name).suffix.lower() != ".pdf"
    ):
        raise HTTPException(status_code=400, detail="Tên hợp đồng không hợp lệ. Chỉ hỗ trợ tệp PDF.")
    if (file.content_type or "").split(";", 1)[0].strip().lower() != CONTRACT_MIME_TYPE:
        raise HTTPException(status_code=400, detail="Loại nội dung phải là application/pdf.")

    content = await file.read(MAX_FILE_SIZE + 1)
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Tệp hợp đồng phải có dung lượng từ 1 byte đến 15 MB.")
    if not valid_file_content(".pdf", content):
        raise HTTPException(status_code=400, detail="Nội dung tệp không đúng định dạng PDF.")

    storage_key = f"{uuid4().hex}.pdf"
    file_path = CONTRACT_STORAGE_ROOT / storage_key
    file_written = False
    try:
        db.execute("BEGIN IMMEDIATE")
        target = db.execute("""
            SELECT h.ma_ho_so, h.trang_thai_xet_duyet, u.ma_nguoi_dung,
                   u.ho_ten, u.email, u.vai_tro, d.ten_phong_ban
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            LEFT JOIN PHONG_BAN d ON d.ma_phong_ban = u.ma_phong_ban
            WHERE h.ma_ho_so = ?
        """, (ma_ho_so,)).fetchone()
        if not target or target["vai_tro"] != "ThucTapSinh":
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")
        if target["trang_thai_xet_duyet"] != "DaDuyet":
            raise HTTPException(status_code=409, detail="Chỉ có thể tải hợp đồng cho hồ sơ đã được duyệt.")
        CONTRACT_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        with file_path.open("xb") as stored_file:
            file_written = True
            stored_file.write(content)

        cursor = db.execute("""
            INSERT INTO HOP_DONG_THUC_TAP
                (ma_ho_so, original_file_name, storage_key, mime_type, file_size,
                 trang_thai, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ma_ho_so, original_name, storage_key, CONTRACT_MIME_TYPE, len(content),
            CONTRACT_STATUS, user["ma_nguoi_dung"],
        ))
        contract_id = cursor.lastrowid
        program = db.execute("""
            SELECT p.ten_ct, p.ngay_bat_dau, p.ngay_ket_thuc, d.ten_phong_ban
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
            LEFT JOIN PHONG_BAN d ON d.ma_phong_ban = p.ma_phong_ban
            WHERE a.ma_ho_so = ? AND a.trang_thai = 'DaDuyet'
            ORDER BY a.ngay_xet_duyet DESC, a.ma_ung_tuyen DESC LIMIT 1
        """, (ma_ho_so,)).fetchone()
        program_name = program["ten_ct"] if program else "Chưa có chương trình được duyệt"
        period = (
            f"{program['ngay_bat_dau'] or 'chưa xác định'} – {program['ngay_ket_thuc'] or 'chưa xác định'}"
            if program else "Chưa xác định"
        )
        contract_url = f"{FRONTEND_URL}/login?next=%2Fcontracts%2F{contract_id}"
        student_name = " ".join((target["ho_ten"] or "").split())
        subject = f"Hợp đồng thực tập đã sẵn sàng - {student_name}"
        email_body = "\n".join((
            f"Xin chào {student_name},",
            "",
            "Bộ phận Nhân sự đã cập nhật hợp đồng thực tập của bạn trên IMS Portal.",
            f"Chương trình: {program_name}",
            f"Phòng ban: {(program['ten_phong_ban'] if program else None) or target['ten_phong_ban'] or 'Chưa phân phòng'}",
            f"Thời gian dự kiến: {period}",
            "Trạng thái hợp đồng: Chờ xác nhận.",
            "",
            "Vui lòng đăng nhập để xem hợp đồng:",
            contract_url,
            "",
            "Email này không đính kèm hợp đồng. Tệp chỉ có thể xem sau khi đăng nhập bằng tài khoản của bạn.",
            "Trân trọng,",
            "Bộ phận Nhân sự - IMS Portal",
        ))
        create_notification(
            db,
            target["ma_nguoi_dung"],
            "Hợp đồng thực tập đã được cập nhật",
            "HR đã tải lên hợp đồng thực tập của bạn. Vui lòng đăng nhập để xem hợp đồng.",
            notification_type="contract_uploaded",
            reference_type="internship_contract",
            reference_id=contract_id,
            email_recipient=target["email"],
            email_deduplication_key=f"us09:contract:{contract_id}:uploaded",
            email_template_type="contract_uploaded",
            email_reference_type="internship_contract",
            email_reference_id=contract_id,
            email_body=email_body,
        )
        result = db.execute(
            _contract_select() + " WHERE c.ma_hop_dong = ?", (contract_id,),
        ).fetchone()
        db.commit()
        return _public_contract(result)
    except HTTPException:
        db.rollback()
        if file_written:
            file_path.unlink(missing_ok=True)
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        if file_written:
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Hồ sơ này đã có hợp đồng hoặc không còn hợp lệ.") from exc
    except Exception as exc:
        db.rollback()
        if file_written:
            file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Không thể lưu hợp đồng. Vui lòng thử lại.") from exc
    finally:
        await file.close()


def _get_authorized_contract(contract_id: int, request: Request, db):
    user = require_role(request, "Admin", "HR", "ThucTapSinh")
    row = db.execute(
        _contract_select() + " WHERE c.ma_hop_dong = ? AND u.vai_tro = 'ThucTapSinh'",
        (contract_id,),
    ).fetchone()
    if not row or (
        user["vai_tro"] == "ThucTapSinh"
        and row["ma_nguoi_dung"] != user["ma_nguoi_dung"]
    ):
        raise HTTPException(status_code=404, detail="Không tìm thấy hợp đồng.")
    return row


@router.get("/{contract_id}/preview")
def preview_contract(contract_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    row = _get_authorized_contract(contract_id, request, db)
    path = _contract_file_path(row["storage_key"])
    return FileResponse(
        path, media_type=CONTRACT_MIME_TYPE,
        filename=row["original_file_name"], content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/{contract_id}/download")
def download_contract(contract_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    row = _get_authorized_contract(contract_id, request, db)
    path = _contract_file_path(row["storage_key"])
    return FileResponse(
        path, media_type=CONTRACT_MIME_TYPE,
        filename=row["original_file_name"], content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store"},
    )
