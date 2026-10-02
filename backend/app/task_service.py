from datetime import date

from fastapi import HTTPException, status

from .notifications import create_notification


class InternshipTaskService:
    """US15 task rules backed by the canonical PHAN_CONG_MENTOR_TTS relation."""

    def __init__(self, db):
        self.db = db

    def list_assigned_interns(self, mentor_id: int) -> list[dict]:
        rows = self.db.execute("""
            SELECT h.ma_ho_so AS internship_profile_id,
                   h.ma_nguoi_dung AS intern_user_id,
                   u.ho_ten AS intern_name, u.email AS intern_email,
                   h.chuyen_nganh AS major, a.ngay_phan_cong AS assigned_at
            FROM PHAN_CONG_MENTOR_TTS a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE a.ma_nguoi_dung_mentor = ?
            ORDER BY u.ho_ten
        """, (mentor_id,)).fetchall()
        return [dict(row) for row in rows]

    def _assigned_profile(self, mentor_id: int, profile_id: int) -> dict:
        profile = self.db.execute("""
            SELECT h.ma_ho_so, h.ma_nguoi_dung, u.ho_ten, u.email
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE h.ma_ho_so = ? AND u.vai_tro = 'ThucTapSinh'
        """, (profile_id,)).fetchone()
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ thực tập.")
        assignment = self.db.execute("""
            SELECT 1 FROM PHAN_CONG_MENTOR_TTS
            WHERE ma_nguoi_dung_mentor = ? AND ma_ho_so = ?
        """, (mentor_id, profile_id)).fetchone()
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn chỉ có thể giao nhiệm vụ cho thực tập sinh được phân công cho mình.",
            )
        return dict(profile)

    @staticmethod
    def _task_select() -> str:
        return """
            SELECT n.ma_nhiem_vu AS id,
                   n.ma_ho_so AS internship_profile_id,
                   h.ma_nguoi_dung AS intern_user_id,
                   intern.ho_ten AS intern_name,
                   intern.email AS intern_email,
                   n.ma_nguoi_dung_mentor AS mentor_id,
                   mentor.ho_ten AS mentor_name,
                   n.tieu_de AS title,
                   n.noi_dung AS description,
                   n.han_hoan_thanh AS due_date,
                   n.do_uu_tien AS priority,
                   n.trang_thai AS status,
                   n.created_at,
                   n.updated_at
            FROM NHIEM_VU_THUC_TAP n
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = n.ma_ho_so
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung = n.ma_nguoi_dung_mentor
        """

    def create_task(self, mentor: dict, data) -> dict:
        profile = self._assigned_profile(mentor["ma_nguoi_dung"], data.internship_profile_id)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            cursor = self.db.execute("""
                INSERT INTO NHIEM_VU_THUC_TAP
                    (ma_ho_so, ma_nguoi_dung_mentor, tieu_de, noi_dung,
                     han_hoan_thanh, do_uu_tien, trang_thai)
                VALUES (?, ?, ?, ?, ?, ?, 'TODO')
            """, (
                data.internship_profile_id,
                mentor["ma_nguoi_dung"],
                data.title,
                data.description,
                data.due_date.isoformat(),
                data.priority,
            ))
            task_id = cursor.lastrowid
            create_notification(
                self.db,
                profile["ma_nguoi_dung"],
                "Nhiệm vụ thực tập mới",
                f"Bạn có nhiệm vụ mới: {data.title}",
                notification_type="TASK_ASSIGNED",
                reference_type="internship_task",
                reference_id=task_id,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_task(task_id, mentor)

    def list_mentor_tasks(
        self,
        mentor_id: int,
        *,
        profile_id: int | None = None,
        task_status: str | None = None,
        priority: str | None = None,
        due_date: date | None = None,
    ) -> list[dict]:
        clauses = ["n.ma_nguoi_dung_mentor = ?"]
        params: list = [mentor_id]
        if profile_id is not None:
            clauses.append("n.ma_ho_so = ?")
            params.append(profile_id)
        if task_status is not None:
            clauses.append("n.trang_thai = ?")
            params.append(task_status)
        if priority is not None:
            clauses.append("n.do_uu_tien = ?")
            params.append(priority)
        if due_date is not None:
            clauses.append("n.han_hoan_thanh = ?")
            params.append(due_date.isoformat())
        rows = self.db.execute(
            self._task_select() + " WHERE " + " AND ".join(clauses)
            + " ORDER BY n.han_hoan_thanh, n.created_at DESC",
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_intern_tasks(self, intern_user_id: int) -> list[dict]:
        rows = self.db.execute(
            self._task_select()
            + " WHERE h.ma_nguoi_dung = ? ORDER BY n.han_hoan_thanh, n.created_at DESC",
            (intern_user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id: int, actor: dict) -> dict:
        row = self.db.execute(
            self._task_select() + " WHERE n.ma_nhiem_vu = ?",
            (task_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhiệm vụ.")
        task = dict(row)
        role = actor["vai_tro"]
        allowed = (
            role == "Mentor" and task["mentor_id"] == actor["ma_nguoi_dung"]
        ) or (
            role == "ThucTapSinh" and task["intern_user_id"] == actor["ma_nguoi_dung"]
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem nhiệm vụ này.")
        return task

    def update_task(self, task_id: int, mentor: dict, data) -> dict:
        self.get_task(task_id, mentor)
        changes = data.model_dump(exclude_unset=True)
        columns = {
            "title": "tieu_de",
            "description": "noi_dung",
            "due_date": "han_hoan_thanh",
            "priority": "do_uu_tien",
        }
        assignments = []
        params = []
        for field, value in changes.items():
            assignments.append(f"{columns[field]} = ?")
            params.append(value.isoformat() if isinstance(value, date) else value)
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        params.extend((task_id, mentor["ma_nguoi_dung"]))
        self.db.execute(
            f"UPDATE NHIEM_VU_THUC_TAP SET {', '.join(assignments)} "
            "WHERE ma_nhiem_vu = ? AND ma_nguoi_dung_mentor = ?",
            tuple(params),
        )
        self.db.commit()
        return self.get_task(task_id, mentor)

    def delete_task(self, task_id: int, mentor: dict) -> None:
        self.get_task(task_id, mentor)
        cursor = self.db.execute("""
            DELETE FROM NHIEM_VU_THUC_TAP
            WHERE ma_nhiem_vu = ? AND ma_nguoi_dung_mentor = ?
        """, (task_id, mentor["ma_nguoi_dung"]))
        if not cursor.rowcount:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhiệm vụ.")
        self.db.commit()
