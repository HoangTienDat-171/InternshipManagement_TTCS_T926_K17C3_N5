import sqlite3

from fastapi import HTTPException

from . import database


SCORE_FIELDS = (
    "professional_skill_score",
    "work_quality_score",
    "initiative_score",
    "communication_teamwork_score",
    "attitude_discipline_score",
)


class InternEvaluationService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _select() -> str:
        return """
            SELECT e.ma_danh_gia AS id,
                   e.ma_ho_so AS internship_profile_id,
                   e.ma_chuong_trinh AS program_id,
                   e.ma_nguoi_dung_mentor AS mentor_id,
                   e.ky_danh_gia AS evaluation_period,
                   e.professional_skill_score,
                   e.work_quality_score,
                   e.initiative_score,
                   e.communication_teamwork_score,
                   e.attitude_discipline_score,
                   e.overall_comment,
                   e.created_at, e.updated_at, e.evaluated_at,
                   h.ma_nguoi_dung AS intern_user_id,
                   intern.ho_ten AS intern_name,
                   p.ten_ct AS program_name,
                   mentor.ho_ten AS mentor_name
            FROM DANH_GIA_THUC_TAP e
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = e.ma_ho_so
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = e.ma_chuong_trinh
            JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung = e.ma_nguoi_dung_mentor
        """

    @staticmethod
    def _public(row) -> dict:
        result = dict(row)
        result["average_score"] = round(sum(result[field] for field in SCORE_FIELDS) / len(SCORE_FIELDS), 1)
        return result

    def _fetch(self, evaluation_id: int, *, for_update: bool = False) -> dict:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        row = self.db.execute(
            self._select() + " WHERE e.ma_danh_gia = ?" + lock,
            (evaluation_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đánh giá thực tập sinh.")
        return self._public(row)

    def _ensure_assignment(self, profile_id: int, mentor_id: int, *, for_update: bool = False) -> None:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        assignment = self.db.execute("""
            SELECT a.ma_phan_cong
            FROM PHAN_CONG_MENTOR_TTS a
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE a.ma_nguoi_dung_mentor = ? AND a.ma_ho_so = ?
              AND intern.vai_tro = 'ThucTapSinh'
        """ + lock, (mentor_id, profile_id)).fetchone()
        if not assignment:
            raise HTTPException(status_code=403, detail="Bạn không được phân công hướng dẫn thực tập sinh này.")

    def _ensure_approved_program(self, profile_id: int, program_id: int, *, for_update: bool = False) -> None:
        lock = " FOR UPDATE" if for_update and database.DATABASE_BACKEND == "mysql" else ""
        application = self.db.execute("""
            SELECT a.ma_ung_tuyen
            FROM UNG_TUYEN_CHUONG_TRINH a
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = a.ma_chuong_trinh
            WHERE a.ma_ho_so = ? AND a.ma_chuong_trinh = ? AND a.trang_thai = 'DaDuyet'
        """ + lock, (profile_id, program_id)).fetchone()
        if not application:
            raise HTTPException(status_code=403, detail="Chương trình chưa được duyệt cho hồ sơ thực tập này.")

    def list_for_mentor(
        self,
        mentor_id: int,
        *,
        profile_id: int | None = None,
        program_id: int | None = None,
        evaluation_period: str | None = None,
    ) -> list[dict]:
        clauses = ["""
            EXISTS (
                SELECT 1 FROM PHAN_CONG_MENTOR_TTS assignment
                WHERE assignment.ma_nguoi_dung_mentor = ?
                  AND assignment.ma_ho_so = e.ma_ho_so
            )
        """]
        params: list = [mentor_id]
        for column, value in (
            ("e.ma_ho_so", profile_id),
            ("e.ma_chuong_trinh", program_id),
            ("e.ky_danh_gia", evaluation_period),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        rows = self.db.execute(
            self._select() + " WHERE " + " AND ".join(clauses) + " ORDER BY e.evaluated_at DESC, e.ma_danh_gia DESC",
            tuple(params),
        ).fetchall()
        return [self._public(row) for row in rows]

    def list_for_hr_admin(
        self,
        *,
        profile_id: int | None = None,
        program_id: int | None = None,
        evaluation_period: str | None = None,
    ) -> list[dict]:
        clauses = []
        params: list = []
        for column, value in (
            ("e.ma_ho_so", profile_id),
            ("e.ma_chuong_trinh", program_id),
            ("e.ky_danh_gia", evaluation_period),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.db.execute(
            self._select() + where + " ORDER BY e.evaluated_at DESC, e.ma_danh_gia DESC",
            tuple(params),
        ).fetchall()
        return [self._public(row) for row in rows]

    def get_for_mentor(self, evaluation_id: int, mentor_id: int) -> dict:
        evaluation = self._fetch(evaluation_id)
        self._ensure_assignment(evaluation["internship_profile_id"], mentor_id)
        return evaluation

    def get_for_hr_admin(self, evaluation_id: int) -> dict:
        return self._fetch(evaluation_id)

    def _profile_for_intern(self, user_id: int) -> int:
        row = self.db.execute("""
            SELECT ma_ho_so FROM HO_SO_THUC_TAP
            WHERE ma_nguoi_dung = ?
        """, (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ thực tập sinh.")
        return row["ma_ho_so"]

    def list_for_intern(self, user_id: int) -> list[dict]:
        profile_id = self._profile_for_intern(user_id)
        rows = self.db.execute(
            self._select() + " WHERE e.ma_ho_so = ? ORDER BY e.evaluated_at DESC, e.ma_danh_gia DESC",
            (profile_id,),
        ).fetchall()
        return [self._public(row) for row in rows]

    def get_for_intern(self, evaluation_id: int, user_id: int) -> dict:
        evaluation = self._fetch(evaluation_id)
        if evaluation["intern_user_id"] != user_id:
            raise HTTPException(status_code=404, detail="Không tìm thấy đánh giá thực tập sinh.")
        return evaluation

    def create(self, mentor_id: int, data) -> dict:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self._ensure_assignment(data.internship_profile_id, mentor_id, for_update=True)
            self._ensure_approved_program(data.internship_profile_id, data.program_id, for_update=True)
            cursor = self.db.execute("""
                INSERT INTO DANH_GIA_THUC_TAP (
                    ma_ho_so, ma_chuong_trinh, ma_nguoi_dung_mentor, ky_danh_gia,
                    professional_skill_score, work_quality_score, initiative_score,
                    communication_teamwork_score, attitude_discipline_score, overall_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.internship_profile_id,
                data.program_id,
                mentor_id,
                data.evaluation_period,
                *(getattr(data, field) for field in SCORE_FIELDS),
                data.overall_comment,
            ))
            evaluation = self._fetch(cursor.lastrowid)
            self.db.commit()
            return evaluation
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Thực tập sinh đã có đánh giá cho chương trình và kỳ này. Hãy mở đánh giá hiện có để chỉnh sửa.",
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    def update(self, evaluation_id: int, mentor_id: int, data) -> dict:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            evaluation = self._fetch(evaluation_id, for_update=True)
            self._ensure_assignment(evaluation["internship_profile_id"], mentor_id, for_update=True)
            changes = data.model_dump(exclude_unset=True)
            assignments = [f"{field} = ?" for field in changes]
            values = list(changes.values())
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            values.append(evaluation_id)
            self.db.execute(
                "UPDATE DANH_GIA_THUC_TAP SET " + ", ".join(assignments) + " WHERE ma_danh_gia = ?",
                tuple(values),
            )
            updated = self._fetch(evaluation_id)
            self.db.commit()
            return updated
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Không thể cập nhật đánh giá do dữ liệu không còn hợp lệ.") from exc
        except Exception:
            self.db.rollback()
            raise
