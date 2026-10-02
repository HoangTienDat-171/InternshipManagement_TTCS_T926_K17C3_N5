"""Temporary credentials for newly created accounts."""
import secrets

from fastapi import HTTPException

from .database import has_password_change_column
from .notifications import create_notification


def require_password_change_schema(db):
    if not has_password_change_column(db):
        raise HTTPException(
            status_code=503,
            detail="Cần áp dụng migration 20260930_temporary_passwords.sql trước khi tạo tài khoản mới.",
        )


def create_temporary_password(length: int = 8) -> str:
    target_length = max(int(length), 8)
    digits = "23456789"
    lowercase = "abcdefghjkmnpqrstuvwxyz"
    uppercase = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    alphabet = digits + lowercase + uppercase
    chars = [
        secrets.choice(digits),
        secrets.choice(lowercase),
        secrets.choice(uppercase),
    ]
    chars += [secrets.choice(alphabet) for _ in range(target_length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def temporary_password_email_body(
    full_name: str,
    email: str,
    password: str,
    account_message: str = "Tài khoản IMS Portal của bạn đã được tạo.",
) -> str:
    return (
        f"Xin chào {full_name},\n\n"
        f"{account_message}\n"
        f"Tên đăng nhập: {email}\n"
        f"Mật khẩu tạm thời: {password}\n\n"
        "Sau khi đăng nhập, hệ thống sẽ yêu cầu bạn đổi mật khẩu trước khi tiếp tục.\n"
        "Nếu bạn không yêu cầu tạo tài khoản này, hãy liên hệ quản trị viên."
    )


def queue_temporary_password_email(
    db,
    user_id: int,
    full_name: str,
    email: str,
    password: str,
    *,
    email_deduplication_key: str | None = None,
):
    create_notification(
        db,
        user_id,
        "Tài khoản IMS Portal đã được tạo",
        "Thông tin đăng nhập tạm thời đã được gửi tới email của bạn.",
        notification_type="account_credentials",
        reference_type="account",
        reference_id=user_id,
        email_recipient=email,
        email_deduplication_key=email_deduplication_key or f"account:{user_id}:temporary-credentials:v1",
        email_template_type="temporary_credentials",
        email_reference_type="account",
        email_reference_id=user_id,
        email_body=temporary_password_email_body(full_name, email, password),
    )
