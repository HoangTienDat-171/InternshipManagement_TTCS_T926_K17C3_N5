"""Write persistent in-app notifications as part of the caller's DB transaction."""


def create_notification(db, user_id: int, title: str, message: str) -> None:
    db.execute(
        "INSERT INTO THONG_BAO (ma_nguoi_dung, tieu_de, noi_dung, kenh) VALUES (?, ?, ?, 'App')",
        (user_id, title, message),
    )
