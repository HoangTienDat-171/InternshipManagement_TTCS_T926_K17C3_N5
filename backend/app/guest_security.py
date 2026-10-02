"""Rate limiting, file inspection, and lightweight anti-bot protection for guest endpoints."""
import io
import os
import secrets
import time
import zipfile
import hmac
import hashlib
from collections import defaultdict
from fastapi import HTTPException, Request, status

# Configure CAPTCHA_SECRET for deployments with multiple worker processes.
CAPTCHA_SECRET = os.getenv("CAPTCHA_SECRET") or secrets.token_urlsafe(32)
RATE_LIMIT_BUCKETS: dict[str, list[float]] = defaultdict(list)


def check_guest_rate_limit(request: Request, limit: int = 5, window_seconds: int = 600):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    RATE_LIMIT_BUCKETS[client_ip] = [ts for ts in RATE_LIMIT_BUCKETS[client_ip] if now - ts < window_seconds]
    if len(RATE_LIMIT_BUCKETS[client_ip]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn đã gửi đơn quá số lần cho phép. Vui lòng thử lại sau 10 phút."
        )
    RATE_LIMIT_BUCKETS[client_ip].append(now)


def generate_captcha() -> tuple[str, str]:
    num1 = secrets.randbelow(15) + 1
    num2 = secrets.randbelow(15) + 1
    answer = str(num1 + num2)
    timestamp = str(int(time.time()))
    payload = f"{answer}:{timestamp}"
    signature = hmac.new(CAPTCHA_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    return token, f"{num1} + {num2} = ?"


def verify_captcha(token: str, user_answer: str, max_age_seconds: int = 300) -> bool:
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        expected_ans, ts_str, signature = parts
        now = int(time.time())
        if now - int(ts_str) > max_age_seconds:
            return False
        payload = f"{expected_ans}:{ts_str}"
        expected_sig = hmac.new(CAPTCHA_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return False
        return hmac.compare_digest(user_answer.strip(), expected_ans.strip())
    except Exception:
        return False


def validate_guest_cv_file(filename: str, content: bytes, max_size: int = 5 * 1024 * 1024) -> str:
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="Dung lượng tệp CV không được vượt quá 5MB.")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Tệp tin tải lên rỗng.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Hệ thống chỉ chấp nhận tệp định dạng PDF hoặc DOCX.")

    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Tệp PDF không hợp lệ hoặc bị hỏng.")
        return "application/pdf"

    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise HTTPException(status_code=400, detail="Tệp DOCX không đúng cấu trúc tài liệu Word.")
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except (zipfile.BadZipFile, OSError):
            raise HTTPException(status_code=400, detail="Tệp DOCX bị hỏng hoặc không đúng chuẩn.")

    raise HTTPException(status_code=400, detail="Định dạng tệp không được hỗ trợ.")
