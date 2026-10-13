import math
from datetime import date, datetime
from fastapi import HTTPException
from . import database

SCORE_FIELDS = (
    "professional_skill_score",
    "work_quality_score",
    "initiative_score",
    "communication_teamwork_score",
    "attitude_discipline_score",
)


def _format_datetime(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return str(val)


class FinalReportService:
    def __init__(self, db):
        self.db = db

    def _base_query(self) -> str:
        return """
            SELECT
                ctx.ma_ho_so AS internship_profile_id,
                ctx.ma_chuong_trinh AS program_id,
                h.ma_nguoi_dung AS intern_user_id,
                intern.ho_ten AS intern_name,
                intern.email AS intern_email,
                intern.so_dien_thoai AS intern_phone,
                u.ten_truong AS university_name,
                h.chuyen_nganh AS major,
                pb.ten_phong_ban AS department_name,
                h.trang_thai_thuc_tap,
                p.ten_ct AS program_name,
                p.ngay_bat_dau AS program_start_date,
                p.ngay_ket_thuc AS program_end_date,
                p.trang_thai AS program_status,
                pc.ma_nguoi_dung_mentor AS assigned_mentor_id,
                pc_mentor.ho_ten AS assigned_mentor_name,
                pc_mentor.email AS assigned_mentor_email,
                pc_mentor.so_dien_thoai AS assigned_mentor_phone,
                ef.ma_danh_gia AS final_eval_id,
                ef.professional_skill_score AS final_professional_skill_score,
                ef.work_quality_score AS final_work_quality_score,
                ef.initiative_score AS final_initiative_score,
                ef.communication_teamwork_score AS final_communication_teamwork_score,
                ef.attitude_discipline_score AS final_attitude_discipline_score,
                ef.overall_comment AS final_overall_comment,
                ef.evaluated_at AS final_evaluated_at,
                ef.ma_nguoi_dung_mentor AS final_evaluator_id,
                ef_mentor.ho_ten AS final_evaluator_name,
                ef_mentor.email AS final_evaluator_email,
                em.ma_danh_gia AS midterm_eval_id,
                em.professional_skill_score AS midterm_professional_skill_score,
                em.work_quality_score AS midterm_work_quality_score,
                em.initiative_score AS midterm_initiative_score,
                em.communication_teamwork_score AS midterm_communication_teamwork_score,
                em.attitude_discipline_score AS midterm_attitude_discipline_score,
                em.overall_comment AS midterm_overall_comment,
                em.evaluated_at AS midterm_evaluated_at,
                em.ma_nguoi_dung_mentor AS midterm_evaluator_id,
                em_mentor.ho_ten AS midterm_evaluator_name,
                em_mentor.email AS midterm_evaluator_email
            FROM (
                SELECT ma_ho_so, ma_chuong_trinh FROM UNG_TUYEN_CHUONG_TRINH WHERE trang_thai = 'DaDuyet'
                UNION
                SELECT ma_ho_so, ma_chuong_trinh FROM DANH_GIA_THUC_TAP
            ) ctx
            JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = ctx.ma_ho_so
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung = h.ma_nguoi_dung
            JOIN CHUONG_TRINH_THUC_TAP p ON p.ma_chuong_trinh = ctx.ma_chuong_trinh
            LEFT JOIN TRUONG_DAI_HOC u ON u.ma_truong = h.ma_truong
            LEFT JOIN PHONG_BAN pb ON pb.ma_phong_ban = COALESCE(intern.ma_phong_ban, p.ma_phong_ban)
            LEFT JOIN PHAN_CONG_MENTOR_TTS pc ON pc.ma_ho_so = h.ma_ho_so AND (pc.ma_chuong_trinh IS NULL OR pc.ma_chuong_trinh = p.ma_chuong_trinh)
            LEFT JOIN NGUOI_DUNG pc_mentor ON pc_mentor.ma_nguoi_dung = pc.ma_nguoi_dung_mentor
            LEFT JOIN DANH_GIA_THUC_TAP ef ON ef.ma_ho_so = ctx.ma_ho_so AND ef.ma_chuong_trinh = ctx.ma_chuong_trinh AND ef.ky_danh_gia = 'FINAL'
            LEFT JOIN NGUOI_DUNG ef_mentor ON ef_mentor.ma_nguoi_dung = ef.ma_nguoi_dung_mentor
            LEFT JOIN DANH_GIA_THUC_TAP em ON em.ma_ho_so = ctx.ma_ho_so AND em.ma_chuong_trinh = ctx.ma_chuong_trinh AND em.ky_danh_gia = 'MIDTERM'
            LEFT JOIN NGUOI_DUNG em_mentor ON em_mentor.ma_nguoi_dung = em.ma_nguoi_dung_mentor
        """

    @staticmethod
    def _row_to_item(row) -> dict:
        row_dict = dict(row)
        final_scores = [row_dict[f"final_{f}"] for f in SCORE_FIELDS if row_dict.get(f"final_{f}") is not None]
        final_avg = round(sum(final_scores) / len(final_scores), 1) if len(final_scores) == len(SCORE_FIELDS) else None

        midterm_scores = [row_dict[f"midterm_{f}"] for f in SCORE_FIELDS if row_dict.get(f"midterm_{f}") is not None]
        midterm_avg = round(sum(midterm_scores) / len(midterm_scores), 1) if len(midterm_scores) == len(SCORE_FIELDS) else None

        has_final = bool(row_dict.get("final_eval_id"))
        has_midterm = bool(row_dict.get("midterm_eval_id"))

        mentor_id = (
            row_dict.get("assigned_mentor_id")
            or row_dict.get("final_evaluator_id")
            or row_dict.get("midterm_evaluator_id")
        )
        mentor_name = (
            row_dict.get("assigned_mentor_name")
            or row_dict.get("final_evaluator_name")
            or row_dict.get("midterm_evaluator_name")
        )
        mentor_email = (
            row_dict.get("assigned_mentor_email")
            or row_dict.get("final_evaluator_email")
            or row_dict.get("midterm_evaluator_email")
        )
        mentor_phone = row_dict.get("assigned_mentor_phone")
        has_mentor = bool(mentor_id)

        missing_requirements = []
        if not has_mentor:
            missing_requirements.append("MENTOR")
        if not has_final:
            missing_requirements.append("FINAL_EVALUATION")

        data_status = "DU_DU_LIEU" if not missing_requirements else "CHUA_DU_LIEU"

        if not missing_requirements:
            status_message = "Đủ dữ liệu đánh giá cuối kỳ"
        elif "MENTOR" in missing_requirements and "FINAL_EVALUATION" in missing_requirements:
            status_message = "Chưa phân công Mentor và chưa có đánh giá cuối kỳ"
        elif "FINAL_EVALUATION" in missing_requirements:
            status_message = "Chưa có đánh giá cuối kỳ"
        else:
            status_message = "Chưa phân công Mentor"

        return {
            "internship_profile_id": row_dict["internship_profile_id"],
            "intern_user_id": row_dict["intern_user_id"],
            "intern_name": row_dict["intern_name"],
            "intern_email": row_dict["intern_email"],
            "intern_phone": row_dict.get("intern_phone"),
            "university_name": row_dict.get("university_name"),
            "major": row_dict.get("major"),
            "department_name": row_dict.get("department_name"),
            "internship_status": row_dict.get("trang_thai_thuc_tap"),
            "program_id": row_dict["program_id"],
            "program_name": row_dict["program_name"],
            "program_start_date": _format_datetime(row_dict.get("program_start_date")),
            "program_end_date": _format_datetime(row_dict.get("program_end_date")),
            "program_status": row_dict.get("program_status"),
            "mentor_id": mentor_id,
            "mentor_name": mentor_name,
            "mentor_email": mentor_email,
            "mentor_phone": mentor_phone,
            "has_mentor": has_mentor,
            "has_final_evaluation": has_final,
            "has_midterm_evaluation": has_midterm,
            "final_average_score": final_avg,
            "midterm_average_score": midterm_avg,
            "final_evaluated_at": _format_datetime(row_dict.get("final_evaluated_at")),
            "data_status": data_status,
            "missing_requirements": missing_requirements,
            "status_message": status_message,
        }

    @classmethod
    def _row_to_detail(cls, row) -> dict:
        item = cls._row_to_item(row)
        row_dict = dict(row)

        final_eval = None
        if row_dict.get("final_eval_id"):
            scores = [row_dict[f"final_{f}"] for f in SCORE_FIELDS]
            avg = round(sum(scores) / len(SCORE_FIELDS), 1)
            final_eval = {
                "id": row_dict["final_eval_id"],
                "evaluation_period": "FINAL",
                "professional_skill_score": row_dict["final_professional_skill_score"],
                "work_quality_score": row_dict["final_work_quality_score"],
                "initiative_score": row_dict["final_initiative_score"],
                "communication_teamwork_score": row_dict["final_communication_teamwork_score"],
                "attitude_discipline_score": row_dict["final_attitude_discipline_score"],
                "average_score": avg,
                "overall_comment": row_dict["final_overall_comment"],
                "evaluated_at": _format_datetime(row_dict["final_evaluated_at"]),
                "evaluator_id": row_dict["final_evaluator_id"],
                "evaluator_name": row_dict["final_evaluator_name"],
                "evaluator_email": row_dict.get("final_evaluator_email"),
            }

        midterm_eval = None
        if row_dict.get("midterm_eval_id"):
            scores = [row_dict[f"midterm_{f}"] for f in SCORE_FIELDS]
            avg = round(sum(scores) / len(SCORE_FIELDS), 1)
            midterm_eval = {
                "id": row_dict["midterm_eval_id"],
                "evaluation_period": "MIDTERM",
                "professional_skill_score": row_dict["midterm_professional_skill_score"],
                "work_quality_score": row_dict["midterm_work_quality_score"],
                "initiative_score": row_dict["midterm_initiative_score"],
                "communication_teamwork_score": row_dict["midterm_communication_teamwork_score"],
                "attitude_discipline_score": row_dict["midterm_attitude_discipline_score"],
                "average_score": avg,
                "overall_comment": row_dict["midterm_overall_comment"],
                "evaluated_at": _format_datetime(row_dict["midterm_evaluated_at"]),
                "evaluator_id": row_dict["midterm_evaluator_id"],
                "evaluator_name": row_dict["midterm_evaluator_name"],
                "evaluator_email": row_dict.get("midterm_evaluator_email"),
            }

        item["final_evaluation"] = final_eval
        item["midterm_evaluation"] = midterm_eval
        return item

    def list_final_reports(
        self,
        *,
        program_id: int | None = None,
        profile_id: int | None = None,
        status: str | None = "ALL",
        search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        base_sql = self._base_query()
        where_clauses = []
        params = []

        if program_id:
            where_clauses.append("ctx.ma_chuong_trinh = ?")
            params.append(program_id)

        if profile_id:
            where_clauses.append("ctx.ma_ho_so = ?")
            params.append(profile_id)

        if search and search.strip():
            term = f"%{search.strip()}%"
            where_clauses.append("""
                (
                    intern.ho_ten LIKE ?
                    OR intern.email LIKE ?
                    OR intern.so_dien_thoai LIKE ?
                    OR u.ten_truong LIKE ?
                    OR h.chuyen_nganh LIKE ?
                )
            """)
            params.extend([term, term, term, term, term])

        where_part = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        order_part = " ORDER BY (CASE WHEN ef.ma_danh_gia IS NOT NULL THEN 0 ELSE 1 END), ef.evaluated_at DESC, intern.ho_ten ASC, ctx.ma_ho_so DESC"

        full_sql = base_sql + where_part + order_part
        rows = self.db.execute(full_sql, tuple(params)).fetchall()

        # Deduplicate rows by (internship_profile_id, program_id) in case of multiple mentor rows
        deduped = {}
        for r in rows:
            key = (r["internship_profile_id"], r["program_id"])
            if key not in deduped:
                deduped[key] = self._row_to_item(r)

        all_items = list(deduped.values())

        total_reports = len(all_items)
        complete_count = sum(1 for it in all_items if it["data_status"] == "DU_DU_LIEU")
        incomplete_count = total_reports - complete_count

        if status == "DU_DU_LIEU":
            filtered_items = [it for it in all_items if it["data_status"] == "DU_DU_LIEU"]
        elif status == "CHUA_DU_LIEU":
            filtered_items = [it for it in all_items if it["data_status"] == "CHUA_DU_LIEU"]
        else:
            filtered_items = all_items

        filtered_total = len(filtered_items)
        total_pages = max(1, math.ceil(filtered_total / page_size)) if filtered_total > 0 else 0
        effective_page = min(page, total_pages) if total_pages > 0 else 1
        offset = (effective_page - 1) * page_size
        paged_items = filtered_items[offset : offset + page_size]

        return {
            "items": paged_items,
            "total_items": filtered_total,
            "page": effective_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "summary": {
                "total_reports": total_reports,
                "complete_count": complete_count,
                "incomplete_count": incomplete_count,
            },
        }

    def get_final_report(self, profile_id: int, program_id: int) -> dict:
        base_sql = self._base_query()
        sql = base_sql + " WHERE ctx.ma_ho_so = ? AND ctx.ma_chuong_trinh = ?"
        row = self.db.execute(sql, (profile_id, program_id)).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy báo cáo cuối kỳ cho hồ sơ và chương trình này.",
            )
        return self._row_to_detail(row)
