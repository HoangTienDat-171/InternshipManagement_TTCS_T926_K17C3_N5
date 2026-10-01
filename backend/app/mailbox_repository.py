"""Database access for internal mailbox messages."""


def get_user(db, user_id: int):
    return db.execute("""
        SELECT ma_nguoi_dung, ho_ten, email, vai_tro, trang_thai, ma_phong_ban
        FROM NGUOI_DUNG WHERE ma_nguoi_dung = ?
    """, (user_id,)).fetchone()


def get_users(db, user_ids: list[int]):
    if not user_ids:
        return []
    placeholders = ",".join("?" for _ in user_ids)
    return db.execute(f"""
        SELECT ma_nguoi_dung, ho_ten, email, vai_tro, trang_thai, ma_phong_ban
        FROM NGUOI_DUNG WHERE ma_nguoi_dung IN ({placeholders})
    """, tuple(user_ids)).fetchall()


def mentor_is_assigned_to(db, mentor_id: int, intern_id: int) -> bool:
    return bool(db.execute("""
        SELECT 1 FROM PHAN_CONG_MENTOR_TTS p
        JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = p.ma_ho_so
        WHERE p.ma_nguoi_dung_mentor = ? AND h.ma_nguoi_dung = ?
    """, (mentor_id, intern_id)).fetchone())


def create_thread(db, subject: str, creator_id: int) -> int:
    return db.execute(
        "INSERT INTO INTERNAL_MESSAGE_THREADS (subject, created_by) VALUES (?, ?)",
        (subject, creator_id),
    ).lastrowid


def create_message(db, thread_id: int, sender_id: int, category: str, subject: str,
                   content_html: str, parent_id: int | None = None) -> int:
    cursor = db.execute("""
        INSERT INTO INTERNAL_MESSAGES
            (thread_id, sender_id, category, subject, content_html, parent_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (thread_id, sender_id, category, subject, content_html, parent_id))
    db.execute(
        "UPDATE INTERNAL_MESSAGE_THREADS SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (thread_id,),
    )
    return cursor.lastrowid


def add_recipients(db, message_id: int, receiver_ids: list[int]):
    db.executemany("""
        INSERT INTO INTERNAL_MESSAGE_RECIPIENTS (message_id, receiver_id)
        VALUES (?, ?)
    """, [(message_id, receiver_id) for receiver_id in receiver_ids])


def message_access(db, message_id: int, user_id: int):
    return db.execute("""
        SELECT m.id, m.thread_id, m.sender_id, m.category, m.subject,
               m.content_html, m.parent_id, m.created_at,
               s.ho_ten AS sender_name, s.email AS sender_email, s.vai_tro AS sender_role,
               CASE WHEN m.sender_id = ? THEN 1 ELSE 0 END AS is_sender,
               r.is_read, r.read_at
        FROM INTERNAL_MESSAGES m
        LEFT JOIN NGUOI_DUNG s ON s.ma_nguoi_dung = m.sender_id
        LEFT JOIN INTERNAL_MESSAGE_RECIPIENTS r
          ON r.message_id = m.id AND r.receiver_id = ?
        WHERE m.id = ? AND m.deleted_at IS NULL
          AND (m.sender_id = ? OR r.receiver_id = ?)
    """, (user_id, user_id, message_id, user_id, user_id)).fetchone()


def thread_accessible(db, thread_id: int, user_id: int) -> bool:
    return bool(db.execute("""
        SELECT 1 FROM INTERNAL_MESSAGES m
        LEFT JOIN INTERNAL_MESSAGE_RECIPIENTS r ON r.message_id = m.id
        WHERE m.thread_id = ? AND m.deleted_at IS NULL
          AND (m.sender_id = ? OR r.receiver_id = ?)
        LIMIT 1
    """, (thread_id, user_id, user_id)).fetchone())


def message_recipients(db, message_id: int):
    return db.execute("""
        SELECT r.receiver_id, r.is_read, r.read_at,
               u.ho_ten, u.email, u.vai_tro,
               (SELECT e.status FROM EMAIL_OUTBOX e
                WHERE e.reference_type='internal_message'
                  AND e.reference_id=CAST(r.message_id AS CHAR)
                  AND e.recipient_email=u.email
                ORDER BY e.id DESC LIMIT 1) AS email_status
        FROM INTERNAL_MESSAGE_RECIPIENTS r
        LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = r.receiver_id
        WHERE r.message_id = ? ORDER BY r.id
    """, (message_id,)).fetchall()


def thread_messages(db, thread_id: int):
    return db.execute("""
        SELECT m.id, m.thread_id, m.sender_id, m.category, m.subject,
               m.content_html, m.parent_id, m.created_at,
               s.ho_ten AS sender_name, s.email AS sender_email, s.vai_tro AS sender_role
        FROM INTERNAL_MESSAGES m
        LEFT JOIN NGUOI_DUNG s ON s.ma_nguoi_dung = m.sender_id
        WHERE m.thread_id = ? AND m.deleted_at IS NULL
        ORDER BY m.created_at, m.id
    """, (thread_id,)).fetchall()


def mark_read(db, message_id: int, user_id: int, is_read: bool) -> int:
    cursor = db.execute("""
        UPDATE INTERNAL_MESSAGE_RECIPIENTS
        SET is_read=?, read_at=CASE WHEN ?=1 THEN COALESCE(read_at, CURRENT_TIMESTAMP) ELSE NULL END
        WHERE message_id=? AND receiver_id=?
    """, (1 if is_read else 0, 1 if is_read else 0, message_id, user_id))
    return cursor.rowcount


def unread_count(db, user_id: int) -> int:
    return db.execute("""
        SELECT COUNT(*) AS total FROM INTERNAL_MESSAGE_RECIPIENTS r
        JOIN INTERNAL_MESSAGES m ON m.id=r.message_id
        WHERE r.receiver_id=? AND r.is_read=0 AND m.deleted_at IS NULL
    """, (user_id,)).fetchone()["total"]


def list_messages(db, user_id: int, folder: str, page: int, page_size: int,
                  read_status: str, category: str | None, query: str | None):
    conditions = ["m.deleted_at IS NULL"]
    params: list[object] = []
    if folder == "inbox":
        joins = """
            JOIN INTERNAL_MESSAGE_RECIPIENTS r ON r.message_id=m.id
            LEFT JOIN NGUOI_DUNG s ON s.ma_nguoi_dung=m.sender_id
        """
        conditions.append("r.receiver_id=?")
        params.append(user_id)
        if read_status == "unread":
            conditions.append("r.is_read=0")
        elif read_status == "read":
            conditions.append("r.is_read=1")
        recipient_fields = "r.is_read, r.read_at"
        search_clause = "(LOWER(m.subject) LIKE ? OR LOWER(COALESCE(s.ho_ten, '')) LIKE ?)"
    else:
        joins = "LEFT JOIN NGUOI_DUNG s ON s.ma_nguoi_dung=m.sender_id"
        conditions.append("m.sender_id=?")
        params.append(user_id)
        recipient_fields = "1 AS is_read, NULL AS read_at"
        search_clause = """(LOWER(m.subject) LIKE ? OR EXISTS (
            SELECT 1 FROM INTERNAL_MESSAGE_RECIPIENTS sr
            JOIN NGUOI_DUNG su ON su.ma_nguoi_dung=sr.receiver_id
            WHERE sr.message_id=m.id AND LOWER(su.ho_ten) LIKE ?))"""
    if category:
        conditions.append("m.category=?")
        params.append(category)
    if query:
        conditions.append(search_clause)
        like = f"%{query.lower()}%"
        params.extend([like, like])
    where_clause = " AND ".join(conditions)
    total = db.execute(
        f"SELECT COUNT(*) AS total FROM INTERNAL_MESSAGES m {joins} WHERE {where_clause}",
        tuple(params),
    ).fetchone()["total"]
    rows = db.execute(f"""
        SELECT m.id, m.thread_id, m.sender_id, m.category, m.subject,
               m.content_html, m.created_at,
               s.ho_ten AS sender_name, s.email AS sender_email, s.vai_tro AS sender_role,
               {recipient_fields},
               (SELECT COUNT(*) FROM INTERNAL_MESSAGE_RECIPIENTS rc
                WHERE rc.message_id=m.id) AS recipient_count,
               (SELECT GROUP_CONCAT(ru.ho_ten) FROM INTERNAL_MESSAGE_RECIPIENTS rr
                JOIN NGUOI_DUNG ru ON ru.ma_nguoi_dung=rr.receiver_id
                WHERE rr.message_id=m.id) AS recipient_names
        FROM INTERNAL_MESSAGES m {joins}
        WHERE {where_clause}
        ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?
    """, (*params, page_size, (page - 1) * page_size)).fetchall()
    return rows, total
