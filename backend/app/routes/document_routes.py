import io
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from ..database import DB_FILE, get_db
from ..notifications import create_notification
from ..schemas import DocumentDetail, DocumentReview
from ..security import require_role

router = APIRouter(prefix="/api/documents", tags=["Internship Documents"])
MAX_FILE_SIZE = 15 * 1024 * 1024
UPLOAD_ROOT = Path(DB_FILE).parent / "uploads" / "documents"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".png"}


def document_record(row):
    record = dict(row)
    record["ten_file"] = record["ten_file"] or Path(record["duong_dan_file"]).name
    return record


def valid_file_content(extension: str, content: bytes) -> bool:
    if extension == ".pdf":
        return content.startswith(b"%PDF-")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                return "[Content_Types].xml" in names and "word/document.xml" in names
        except (OSError, zipfile.BadZipFile):
            return False
    return False


@router.get("")
def list_documents(
    request: Request,
    page: int | None = Query(None, ge=1),
    page_size: int | None = Query(None, alias="pageSize", ge=1, le=100),
    db: sqlite3.Connection = Depends(get_db),
):
    require_role(request, "Admin", "HR")
    base_query = """
        FROM TAI_LIEU_HO_SO d
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE u.vai_tro = 'ThucTapSinh'
    """
    if page is not None or page_size is not None:
        effective_size = page_size or 10
        total_items = db.execute("SELECT COUNT(*) AS total_items " + base_query).fetchone()["total_items"]
        total_pages = (total_items + effective_size - 1) // effective_size if total_items else 0
        effective_page = min(page or 1, total_pages) if total_pages else 1
        paging_clause = " LIMIT ? OFFSET ?"
        paging_params = (effective_size, (effective_page - 1) * effective_size)
    else:
        total_items = total_pages = effective_page = None
        paging_clause = ""
        paging_params = ()
    rows = db.execute("""
        SELECT d.ma_tai_lieu, d.ma_ho_so, d.ten_file, d.duong_dan_file,
               d.kich_thuoc, d.loai_tai_lieu, d.ngay_tai_len,
               d.trang_thai_duyet, u.ho_ten AS thuc_tap_sinh
    """ + base_query + """
        ORDER BY d.ngay_tai_len DESC, d.ma_tai_lieu DESC
    """ + paging_clause, paging_params).fetchall()
    items = [document_record(row) for row in rows]
    if page is None and page_size is None:
        return items
    return {
        "items": items,
        "page": effective_page,
        "pageSize": page_size or 10,
        "totalItems": total_items,
        "totalPages": total_pages,
    }


@router.post("", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    ma_ho_so: int | None = Form(None),
    loai_tai_lieu: str = Form(...),
    file: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
):
    user = require_role(request, "Admin", "HR", "ThucTapSinh")
    if loai_tai_lieu not in {"CV", "DonXinThucTap", "GiayGioiThieu"}:
        raise HTTPException(status_code=400, detail="Loại tài liệu không hợp lệ.")
    if user["vai_tro"] == "ThucTapSinh":
        if loai_tai_lieu not in {"CV", "DonXinThucTap"}:
            raise HTTPException(status_code=403, detail="Thực tập sinh chỉ được tự nộp CV hoặc đơn xin thực tập.")
        own_profile = db.execute(
            "SELECT ma_ho_so FROM HO_SO_THUC_TAP WHERE ma_nguoi_dung = ?",
            (user["ma_nguoi_dung"],),
        ).fetchone()
        if not own_profile:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")
        ma_ho_so = own_profile["ma_ho_so"]
    elif ma_ho_so is None:
        raise HTTPException(status_code=400, detail="Vui lòng chọn hồ sơ thực tập sinh.")
    intern = db.execute("""
        SELECT h.ma_ho_so FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh'
    """, (ma_ho_so,)).fetchone()
    if not intern:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")

    original_name = PurePosixPath((file.filename or "").replace("\\", "/")).name
    extension = Path(original_name).suffix.lower()
    if not original_name or len(original_name) > 255 or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp PDF, DOCX hoặc PNG có tên hợp lệ.")

    content = await file.read(MAX_FILE_SIZE + 1)
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Tệp phải có dung lượng từ 1 byte đến 15 MB.")
    if not valid_file_content(extension, content):
        raise HTTPException(status_code=400, detail="Nội dung tệp không khớp định dạng đã chọn.")

    storage_name = f"{uuid4().hex}{extension}"
    absolute_path = UPLOAD_ROOT / storage_name
    relative_path = PurePosixPath("documents", storage_name).as_posix()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with absolute_path.open("xb") as stored_file:
            stored_file.write(content)
        cursor = db.execute("""
            INSERT INTO TAI_LIEU_HO_SO
                (ma_ho_so, loai_tai_lieu, duong_dan_file, ten_file, kich_thuoc)
            VALUES (?, ?, ?, ?, ?)
        """, (ma_ho_so, loai_tai_lieu, relative_path, original_name, len(content)))
        db.commit()
    except Exception:
        db.rollback()
        absolute_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    row = db.execute("""
        SELECT d.ma_tai_lieu, d.ma_ho_so, d.ten_file, d.duong_dan_file,
               d.kich_thuoc, d.loai_tai_lieu, d.ngay_tai_len,
               d.trang_thai_duyet, u.ho_ten AS thuc_tap_sinh
        FROM TAI_LIEU_HO_SO d JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE d.ma_tai_lieu = ?
    """, (cursor.lastrowid,)).fetchone()
    return document_record(row)


@router.put("/{document_id}/review", response_model=DocumentDetail)
def review_document(document_id: int, data: DocumentReview, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    document = db.execute("""
        SELECT d.trang_thai_duyet, u.ma_nguoi_dung, u.ho_ten
        FROM TAI_LIEU_HO_SO d
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE d.ma_tai_lieu = ? AND u.vai_tro = 'ThucTapSinh'
    """, (document_id,)).fetchone()
    if not document:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    cursor = db.execute("""
        UPDATE TAI_LIEU_HO_SO SET trang_thai_duyet = ? WHERE ma_tai_lieu = ?
    """, (data.trang_thai_duyet, document_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    if document["trang_thai_duyet"] != data.trang_thai_duyet:
        title, message = {
            "DaDuyet": ("Tài liệu đã được duyệt", f"Tài liệu {document['ho_ten']} gửi lên đã được duyệt."),
            "TuChoi": ("Tài liệu bị từ chối", f"Tài liệu {document['ho_ten']} gửi lên đã bị từ chối."),
        }[data.trang_thai_duyet]
        create_notification(db, document["ma_nguoi_dung"], title, message)
    db.commit()
    row = db.execute("""
        SELECT d.ma_tai_lieu, d.ma_ho_so, d.ten_file, d.duong_dan_file,
               d.kich_thuoc, d.loai_tai_lieu, d.ngay_tai_len,
               d.trang_thai_duyet, u.ho_ten AS thuc_tap_sinh
        FROM TAI_LIEU_HO_SO d JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE d.ma_tai_lieu = ?
    """, (document_id,)).fetchone()
    return document_record(row)


@router.get("/{document_id}/file")
def download_document(document_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    user = require_role(request, "Admin", "HR", "Mentor", "ThucTapSinh")
    row = db.execute("""
        SELECT d.ten_file, d.duong_dan_file, h.ma_ho_so, h.ma_nguoi_dung
        FROM TAI_LIEU_HO_SO d
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = d.ma_ho_so
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE d.ma_tai_lieu = ? AND u.vai_tro = 'ThucTapSinh'
    """, (document_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    if user["vai_tro"] == "ThucTapSinh" and row["ma_nguoi_dung"] != user["ma_nguoi_dung"]:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    if user["vai_tro"] == "Mentor" and not db.execute("""
        SELECT 1 FROM PHAN_CONG_MENTOR_TTS
        WHERE ma_nguoi_dung_mentor=? AND ma_ho_so=?
    """, (user["ma_nguoi_dung"], row["ma_ho_so"])).fetchone():
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")

    stored_path = PurePosixPath(row["duong_dan_file"])
    if stored_path.is_absolute() or ".." in stored_path.parts or stored_path.parts[:1] != ("documents",):
        raise HTTPException(status_code=404, detail="Đường dẫn tệp không hợp lệ.")
    absolute_path = UPLOAD_ROOT / stored_path.name
    if not absolute_path.is_file():
        raise HTTPException(status_code=404, detail="Tệp không còn tồn tại trên máy chủ.")
    filename = row["ten_file"] or absolute_path.name
    return FileResponse(absolute_path, filename=filename, content_disposition_type="inline")
