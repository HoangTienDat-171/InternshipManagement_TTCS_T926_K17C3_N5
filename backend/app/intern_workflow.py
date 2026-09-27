"""Shared account and internship application state transitions."""

APPROVAL_TO_ACCOUNT_STATUS = {
    "ChoDuyet": "ChoDuyet",
    "DaDuyet": "HoatDong",
    "TuChoi": "Khoa",
}


def sync_intern_approval(cursor, user_id: int, approval_status: str) -> bool:
    """Keep an intern's account state aligned when their application is reviewed."""
    account_status = APPROVAL_TO_ACCOUNT_STATUS[approval_status]
    cursor.execute(
        "UPDATE NGUOI_DUNG SET trang_thai = ? WHERE ma_nguoi_dung = ? AND vai_tro = 'ThucTapSinh'",
        (account_status, user_id),
    )
    if cursor.rowcount == 0:
        return False
    if account_status != "HoatDong":
        cursor.execute("DELETE FROM ACTIVE_SESSIONS WHERE ma_nguoi_dung = ?", (user_id,))
    return True
