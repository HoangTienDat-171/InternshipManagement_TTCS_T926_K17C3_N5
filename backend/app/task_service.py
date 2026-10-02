from datetime import date

from fastapi import HTTPException, status

from . import database
from .notifications import create_notification


class InternshipTaskService:
    """US15/US16 task rules backed by the canonical Mentor assignment relation."""

    INTERN_TRANSITIONS = {
        "TODO": {"TODO", "IN_PROGRESS", "COMPLETED"},
        "IN_PROGRESS": {"IN_PROGRESS", "COMPLETED"},
        "COMPLETED": {"COMPLETED"},
        "CANCELLED": {"CANCELLED"},
    }

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
                   n.progress_percent,
                   n.progress_note,
                   n.created_at,
                   n.updated_at
            FROM NHIEM_VU_THUC_TAP n
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = n.ma_ho_so
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung = n.ma_nguoi_dung_mentor
        """

    def _fetch_task(self, task_id: int, *, for_update: bool = False) -> dict:
        lock_clause = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        row = self.db.execute(
            self._task_select() + " WHERE n.ma_nhiem_vu = ?" + lock_clause,
            (task_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy nhiệm vụ.")
        return dict(row)

    def _mentor_has_assignment(self, mentor_id: int, profile_id: int) -> bool:
        return self.db.execute("""
            SELECT 1 FROM PHAN_CONG_MENTOR_TTS
            WHERE ma_nguoi_dung_mentor = ? AND ma_ho_so = ?
        """, (mentor_id, profile_id)).fetchone() is not None

    def _ensure_view_access(self, task: dict, actor: dict) -> None:
        role = actor["vai_tro"]
        allowed = (
            role == "Mentor"
            and self._mentor_has_assignment(actor["ma_nguoi_dung"], task["internship_profile_id"])
        ) or (
            role == "ThucTapSinh" and task["intern_user_id"] == actor["ma_nguoi_dung"]
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền xem nhiệm vụ này.")

    def _ensure_mentor_owner(self, task: dict, mentor: dict) -> None:
        if (
            task["mentor_id"] != mentor["ma_nguoi_dung"]
            or not self._mentor_has_assignment(mentor["ma_nguoi_dung"], task["internship_profile_id"])
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền quản lý nhiệm vụ này.")

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
        clauses = [
            "EXISTS (SELECT 1 FROM PHAN_CONG_MENTOR_TTS a "
            "WHERE a.ma_nguoi_dung_mentor = ? AND a.ma_ho_so = n.ma_ho_so)",
        ]
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
        task = self._fetch_task(task_id)
        self._ensure_view_access(task, actor)
        return task

    def update_task(self, task_id: int, mentor: dict, data) -> dict:
        task = self._fetch_task(task_id)
        self._ensure_mentor_owner(task, mentor)
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

    def _insert_progress_history(
        self,
        task: dict,
        actor_id: int,
        new_progress: int,
        new_status: str,
        note: str | None,
    ) -> None:
        self.db.execute("""
            INSERT INTO LICH_SU_TIEN_DO_CONG_VIEC
                (ma_nhiem_vu, updated_by, old_progress, new_progress,
                 old_status, new_status, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task["id"], actor_id, task["progress_percent"], new_progress,
            task["status"], new_status, note,
        ))

    def update_progress(self, task_id: int, intern: dict, data) -> dict:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            task = self._fetch_task(task_id, for_update=True)
            if task["intern_user_id"] != intern["ma_nguoi_dung"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bạn chỉ có thể cập nhật nhiệm vụ được giao cho chính mình.",
                )

            note = data.note if "note" in data.model_fields_set else task["progress_note"]
            unchanged = (
                task["progress_percent"] == data.progress_percent
                and task["status"] == data.status
                and task["progress_note"] == note
            )
            if unchanged:
                self.db.rollback()
                return task

            if task["status"] in {"COMPLETED", "CANCELLED"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Nhiệm vụ đã ở trạng thái cuối và không thể cập nhật tiến độ.",
                )
            if data.status not in self.INTERN_TRANSITIONS[task["status"]]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Không thể chuyển trạng thái từ {task['status']} sang {data.status}.",
                )

            self.db.execute("""
                UPDATE NHIEM_VU_THUC_TAP
                SET progress_percent = ?, trang_thai = ?, progress_note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ma_nhiem_vu = ?
            """, (data.progress_percent, data.status, note, task_id))
            self._insert_progress_history(
                task,
                intern["ma_nguoi_dung"],
                data.progress_percent,
                data.status,
                note,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_task(task_id, intern)

    def get_progress_history(self, task_id: int, actor: dict) -> list[dict]:
        self.get_task(task_id, actor)
        rows = self.db.execute("""
            SELECT h.ma_lich_su AS id,
                   h.ma_nhiem_vu AS task_id,
                   h.updated_by,
                   u.ho_ten AS updated_by_name,
                   u.vai_tro AS updated_by_role,
                   h.old_progress,
                   h.new_progress,
                   h.old_status,
                   h.new_status,
                   h.note,
                   h.created_at
            FROM LICH_SU_TIEN_DO_CONG_VIEC h
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.updated_by
            WHERE h.ma_nhiem_vu = ?
            ORDER BY h.ma_lich_su
        """, (task_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete_task(self, task_id: int, mentor: dict) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            task = self._fetch_task(task_id, for_update=True)
            self._ensure_mentor_owner(task, mentor)
            has_history = self.db.execute("""
                SELECT 1 FROM LICH_SU_TIEN_DO_CONG_VIEC WHERE ma_nhiem_vu = ? LIMIT 1
            """, (task_id,)).fetchone()
            if has_history:
                if task["status"] != "CANCELLED":
                    self.db.execute("""
                        UPDATE NHIEM_VU_THUC_TAP
                        SET trang_thai = 'CANCELLED', updated_at = CURRENT_TIMESTAMP
                        WHERE ma_nhiem_vu = ?
                    """, (task_id,))
                    self._insert_progress_history(
                        task,
                        mentor["ma_nguoi_dung"],
                        task["progress_percent"],
                        "CANCELLED",
                        "Mentor đã hủy nhiệm vụ.",
                    )
            else:
                self.db.execute("DELETE FROM NHIEM_VU_THUC_TAP WHERE ma_nhiem_vu = ?", (task_id,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
