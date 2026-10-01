"""Security, sanitization, and MIME-type validation for email attachments."""
import hashlib
import io
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException, status

MAX_SINGLE_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_TOTAL_EMAIL_ATTACHMENTS = 25 * 1024 * 1024  # 25 MB

ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    # Images
    "image/png": [".png"],
    "image/jpeg": [".jpg", ".jpeg"],
}

BLOCKED_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".cmd", ".vbs", ".js", ".msi", ".jar",
    ".com", ".pif", ".scr", ".hta", ".cpl", ".msc",
    ".docm", ".xlsm", ".pptm"  # Macro-enabled Office files
}

ATTACHMENT_ROOT = Path(__file__).resolve().parents[1] / "uploads" / "email_attachments"
ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Strip directory traversal sequences and illegal filesystem characters."""
    base = os.path.basename(filename.strip().replace("\\", "/"))
    clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', base)
    return clean[:200] or f"attachment_{uuid4().hex[:8]}"


def inspect_magic_bytes(content: bytes, ext: str) -> bool:
    """Deep inspection of file headers to prevent spoofing."""
    if ext == ".pdf":
        return content.startswith(b"%PDF-")
    if ext == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                return "[Content_Types].xml" in names and "word/document.xml" in names
        except Exception:
            return False
    return False


def validate_attachment(filename: str, content: bytes, mime_type: str | None = None) -> dict:
    """Enforce strict whitelist, payload limits, and path security."""
    if len(content) > MAX_SINGLE_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Tệp {filename} vượt quá giới hạn tối đa 10MB."
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail=f"Tệp {filename} rỗng (0 bytes).")

    safe_name = sanitize_filename(filename)
    ext = os.path.splitext(safe_name)[1].lower()

    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng tệp {ext} bị cấm vì lý do an toàn bảo mật."
        )

    resolved_mime = mime_type or mimetypes.guess_type(safe_name)[0] or ""
    valid_mime = False
    for allowed_mime, allowed_exts in ALLOWED_MIME_TYPES.items():
        if ext in allowed_exts:
            resolved_mime = allowed_mime
            valid_mime = True
            break

    if not valid_mime or not inspect_magic_bytes(content, ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nội dung tệp {safe_name} không hợp lệ hoặc giả mạo định dạng."
        )

    # Persist file securely
    att_id = str(uuid4())
    storage_filename = f"{att_id}_{safe_name}"
    storage_path = (ATTACHMENT_ROOT / storage_filename).resolve()

    # Path traversal check
    if not str(storage_path).startswith(str(ATTACHMENT_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Phát hiện đường dẫn tệp không an toàn.")

    storage_path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()

    return {
        "id": att_id,
        "filename": safe_name,
        "file_path": str(storage_path),
        "mime_type": resolved_mime,
        "file_size": len(content),
        "checksum_sha256": checksum,
    }
