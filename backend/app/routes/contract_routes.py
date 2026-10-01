import os
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..database import DB_FILE, get_db
from ..notifications import create_notification
from ..schemas import ContractRejectRequest
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


@router.post("/{contract_id}/confirm")
def confirm_contract(
    contract_id: int,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    return _process_contract_decision(contract_id, request, "CONFIRMED", None, db)


@router.post("/{contract_id}/reject")
def reject_contract(
    contract_id: int,
    request: Request,
    data: ContractRejectRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    reason = data.reason.strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail="Lý do từ chối cần có ít nhất 10 ký tự.")
    return _process_contract_decision(contract_id, request, "REJECTED", reason, db)


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
        db.execute("""
            INSERT INTO HOP_DONG_THUC_TAP_LICH_SU
                (ma_hop_dong, action, old_status, new_status, actor_id, actor_name, actor_role)
            VALUES (?, 'UPLOADED', NULL, ?, ?, ?, ?)
        """, (
            contract_id, CONTRACT_STATUS, user["ma_nguoi_dung"],
            user["ho_ten"], user["vai_tro"],
        ))
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


def _contract_detail_payload(contract_id: int, request: Request, db):
    row = _get_authorized_contract(contract_id, request, db)
    decision = db.execute("""
        SELECT c.confirmed_at, confirmer.ho_ten AS confirmed_by_name,
               c.rejected_at, rejecter.ho_ten AS rejected_by_name, c.rejection_reason
        FROM HOP_DONG_THUC_TAP c
        LEFT JOIN NGUOI_DUNG confirmer ON confirmer.ma_nguoi_dung = c.confirmed_by
        LEFT JOIN NGUOI_DUNG rejecter ON rejecter.ma_nguoi_dung = c.rejected_by
        WHERE c.ma_hop_dong = ?
    """, (contract_id,)).fetchone()
    history = db.execute("""
        SELECT action, old_status, new_status, actor_name, actor_role, reason, created_at
        FROM HOP_DONG_THUC_TAP_LICH_SU
        WHERE ma_hop_dong = ?
        ORDER BY created_at ASC, history_id ASC
    """, (contract_id,)).fetchall()
    return {
        "ma_hop_dong": row["ma_hop_dong"],
        "original_file_name": row["original_file_name"],
        "mime_type": row["mime_type"],
        "file_size": row["file_size"],
        "trang_thai": row["trang_thai"],
        "uploaded_at": row["uploaded_at"],
        "ho_ten": row["ho_ten"],
        "ten_chuong_trinh": row["ten_chuong_trinh"],
        "ngay_bat_dau": row["ngay_bat_dau"],
        "ngay_ket_thuc": row["ngay_ket_thuc"],
        "ten_phong_ban": row["ten_phong_ban"],
        "confirmed_at": decision["confirmed_at"],
        "confirmed_by_name": decision["confirmed_by_name"],
        "rejected_at": decision["rejected_at"],
        "rejected_by_name": decision["rejected_by_name"],
        "rejection_reason": decision["rejection_reason"],
        "history": [dict(entry) for entry in history],
    }


@router.get("/{contract_id}")
def get_contract_detail(contract_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    return _contract_detail_payload(contract_id, request, db)


def _notify_contract_uploader(db, contract, actor, decision, reason):
    if not contract["uploaded_by"]:
        return
    recipient = db.execute(
        "SELECT ma_nguoi_dung, ho_ten, email FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?",
        (contract["uploaded_by"],),
    ).fetchone()
    if not recipient:
        return

    rejected = decision == "REJECTED"
    verb = "từ chối" if rejected else "xác nhận"
    title = f"Thực tập sinh đã {verb} hợp đồng"
    message = f"{actor['ho_ten']} đã {verb} {contract['original_file_name']}."
    email_body = message
    if rejected:
        message += f" Lý do: {reason}"
        email_body += f"\nLý do: {reason}"
    create_notification(
        db,
        recipient["ma_nguoi_dung"],
        title,
        message,
        notification_type="contract_decision",
        reference_type="internship_contract",
        reference_id=contract["ma_hop_dong"],
        email_recipient=recipient["email"],
        email_deduplication_key=f"us10:contract:{contract['ma_hop_dong']}:{decision.lower()}",
        email_subject=title,
        email_template_type="contract_decision",
        email_reference_type="internship_contract",
        email_reference_id=contract["ma_hop_dong"],
        email_body=email_body,
    )


def _process_contract_decision(contract_id: int, request: Request, decision: str, reason: str | None, db):
    user = require_role(request, "ThucTapSinh")
    db.execute("BEGIN IMMEDIATE")
    contract = db.execute(
        _contract_select() + " WHERE c.ma_hop_dong = ? AND h.ma_nguoi_dung = ? AND u.vai_tro = 'ThucTapSinh'",
        (contract_id, user["ma_nguoi_dung"]),
    ).fetchone()
    if not contract:
        raise HTTPException(status_code=404, detail="Không tìm thấy hợp đồng.")
    if contract["trang_thai"] != CONTRACT_STATUS:
        raise HTTPException(status_code=409, detail="Trạng thái hợp đồng đã thay đổi.")

    profile = db.execute(
        "SELECT trang_thai_xet_duyet FROM HO_SO_THUC_TAP WHERE ma_ho_so = ?",
        (contract["ma_ho_so"],),
    ).fetchone()
    if not profile or profile["trang_thai_xet_duyet"] != "DaDuyet":
        raise HTTPException(status_code=409, detail="Hồ sơ thực tập không còn ở trạng thái hợp lệ.")

    try:
        file_path = _contract_file_path(contract["storage_key"])
        if file_path.stat().st_size != contract["file_size"]:
            raise HTTPException(status_code=409, detail="Tệp hợp đồng không còn hợp lệ.")
        with file_path.open("rb") as stored_file:
            if not valid_file_content(".pdf", stored_file.read(5)):
                raise HTTPException(status_code=409, detail="Tệp hợp đồng không còn hợp lệ.")
    except HTTPException:
        db.rollback()
        raise
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail="Không tìm thấy tệp hợp đồng.") from exc

    try:
        if decision == "CONFIRMED":
            updated = db.execute("""
                UPDATE HOP_DONG_THUC_TAP
                SET trang_thai = 'CONFIRMED', confirmed_by = ?, confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ma_hop_dong = ? AND trang_thai = ?
            """, (user["ma_nguoi_dung"], contract_id, CONTRACT_STATUS))
        else:
            updated = db.execute("""
                UPDATE HOP_DONG_THUC_TAP
                SET trang_thai = 'REJECTED', rejected_by = ?, rejected_at = CURRENT_TIMESTAMP,
                    rejection_reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ma_hop_dong = ? AND trang_thai = ?
            """, (user["ma_nguoi_dung"], reason, contract_id, CONTRACT_STATUS))
        if updated.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Trạng thái hợp đồng đã thay đổi.")

        db.execute("""
            INSERT INTO HOP_DONG_THUC_TAP_LICH_SU
                (ma_hop_dong, action, old_status, new_status, actor_id, actor_name, actor_role, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            contract_id, decision, CONTRACT_STATUS, decision,
            user["ma_nguoi_dung"], user["ho_ten"], user["vai_tro"], reason,
        ))
        _notify_contract_uploader(db, contract, user, decision, reason)
        result = _contract_detail_payload(contract_id, request, db)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể cập nhật quyết định hợp đồng.") from exc


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
