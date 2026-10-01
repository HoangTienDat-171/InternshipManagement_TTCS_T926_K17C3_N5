"""Read-only system dashboard aggregations."""
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ..database import get_db
from ..security import require_role

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Metrics"])


@router.get("/metrics", response_model=dict[str, Any])
def get_dashboard_metrics(
    request: Request,
    ma_phong_ban: int | None = Query(None, ge=1),
    ma_truong: int | None = Query(None, ge=1),
    db: sqlite3.Connection = Depends(get_db),
):
    """Aggregate current records for management screens without changing data."""
    require_role(request, "Admin", "HR")

    intern_filters = ["u.vai_tro = 'ThucTapSinh'"]
    intern_params: list[int] = []
    if ma_phong_ban is not None:
        intern_filters.append("u.ma_phong_ban = ?")
        intern_params.append(ma_phong_ban)
    if ma_truong is not None:
        intern_filters.append("h.ma_truong = ?")
        intern_params.append(ma_truong)

    intern_stats = db.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' THEN 1 ELSE 0 END) AS approved,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'ChoDuyet' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'TuChoi' THEN 1 ELSE 0 END) AS rejected,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' AND h.trang_thai_thuc_tap = 'DangThucTap' THEN 1 ELSE 0 END) AS in_progress,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' AND h.trang_thai_thuc_tap = 'HoanThanh' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN h.trang_thai_xet_duyet = 'DaDuyet' AND h.trang_thai_thuc_tap = 'ThoiHoc' THEN 1 ELSE 0 END) AS withdrawn,
               SUM(CASE WHEN EXISTS (
                   SELECT 1
                   FROM PHAN_CONG_MENTOR_TTS a
                   JOIN NGUOI_DUNG m ON m.ma_nguoi_dung = a.ma_nguoi_dung_mentor
                   WHERE a.ma_ho_so = h.ma_ho_so AND m.vai_tro = 'Mentor'
               ) AND h.trang_thai_xet_duyet = 'DaDuyet' THEN 1 ELSE 0 END) AS assigned,
               COUNT(DISTINCT h.ma_truong) AS universities
        FROM HO_SO_THUC_TAP h
        JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
        WHERE {' AND '.join(intern_filters)}
    """, intern_params).fetchone()

    program_filters: list[str] = []
    program_params: list[int] = []
    if ma_phong_ban is not None:
        program_filters.append("c.ma_phong_ban = ?")
        program_params.append(ma_phong_ban)
    if ma_truong is not None:
        program_filters.append(
            "EXISTS (SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH ua "
            "JOIN HO_SO_THUC_TAP uh ON uh.ma_ho_so = ua.ma_ho_so "
            "WHERE ua.ma_chuong_trinh = c.ma_chuong_trinh AND uh.ma_truong = ?)"
        )
        program_params.append(ma_truong)
    program_where = f"WHERE {' AND '.join(program_filters)}" if program_filters else ""
    applicant_params = [*([ma_phong_ban] if ma_phong_ban is not None else []),
                        *([ma_truong] if ma_truong is not None else [])]
    breakdown_filters: list[str] = []
    breakdown_params: list[int] = []
    if ma_phong_ban is not None:
        breakdown_filters.append("c.ma_phong_ban = ?")
        breakdown_params.append(ma_phong_ban)
    if ma_truong is not None:
        breakdown_filters.append("h.ma_truong = ?")
        breakdown_params.append(ma_truong)
    breakdown_where = f"WHERE {' AND '.join(breakdown_filters)}" if breakdown_filters else ""
    program_stats = db.execute(f"""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN c.trang_thai = 'DangMo' THEN 1 ELSE 0 END) AS open,
               COALESCE(SUM(c.chi_tieu), 0) AS quota,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                JOIN CHUONG_TRINH_THUC_TAP ac ON ac.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE (1 = 1)
                  {"AND ac.ma_phong_ban = ?" if ma_phong_ban is not None else ""}
                  {"AND EXISTS (SELECT 1 FROM HO_SO_THUC_TAP ah WHERE ah.ma_ho_so = a.ma_ho_so AND ah.ma_truong = ?)" if ma_truong is not None else ""}
               ) AS applicants,
               (SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH a
                JOIN CHUONG_TRINH_THUC_TAP ac ON ac.ma_chuong_trinh = a.ma_chuong_trinh
                WHERE a.trang_thai = 'ChoDuyet'
                  {"AND ac.ma_phong_ban = ?" if ma_phong_ban is not None else ""}
                  {"AND EXISTS (SELECT 1 FROM HO_SO_THUC_TAP ah WHERE ah.ma_ho_so = a.ma_ho_so AND ah.ma_truong = ?)" if ma_truong is not None else ""}
               ) AS pending_applicants
        FROM CHUONG_TRINH_THUC_TAP c
        {program_where}
    """, [*applicant_params, *applicant_params, *program_params]).fetchone()

    program_breakdown = db.execute(f"""
        SELECT c.ma_ct, c.ten_ct,
               COUNT(a.ma_ung_tuyen) AS applicants,
               SUM(CASE WHEN a.trang_thai = 'ChoDuyet' THEN 1 ELSE 0 END) AS pending_applicants
        FROM CHUONG_TRINH_THUC_TAP c
        LEFT JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_chuong_trinh = c.ma_chuong_trinh
        LEFT JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
        {breakdown_where}
        GROUP BY c.ma_chuong_trinh, c.ma_ct, c.ten_ct
        ORDER BY c.ma_chuong_trinh DESC
    """, breakdown_params).fetchall()

    mentor_stats = db.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN workload.intern_count > 0 THEN 1 ELSE 0 END) AS assigned_mentors,
               COALESCE(SUM(workload.intern_count), 0) AS assigned_interns
        FROM (
            SELECT m.ma_nguoi_dung,
                   COUNT(DISTINCT CASE WHEN i.vai_tro = 'ThucTapSinh' THEN h.ma_ho_so END) AS intern_count
            FROM NGUOI_DUNG m
            LEFT JOIN PHAN_CONG_MENTOR_TTS a ON a.ma_nguoi_dung_mentor = m.ma_nguoi_dung
            LEFT JOIN HO_SO_THUC_TAP h ON h.ma_ho_so = a.ma_ho_so
            LEFT JOIN NGUOI_DUNG i ON i.ma_nguoi_dung = h.ma_nguoi_dung
            WHERE m.vai_tro = 'Mentor'
            GROUP BY m.ma_nguoi_dung
        ) workload
    """).fetchone()
    mentor_departments = db.execute("""
        SELECT COALESCE(p.ten_phong_ban, 'Chưa phân phòng') AS name,
               COUNT(*) AS mentors
        FROM NGUOI_DUNG m
        LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = m.ma_phong_ban
        WHERE m.vai_tro = 'Mentor'
        GROUP BY p.ten_phong_ban
        ORDER BY mentors DESC, name
    """).fetchall()
    mentor_expertise = db.execute("""
        SELECT COALESCE(NULLIF(TRIM(mp.chuyen_mon), ''), 'Chưa cập nhật') AS name,
               COUNT(*) AS mentors
        FROM NGUOI_DUNG m
        LEFT JOIN MENTOR_PROFILE mp ON mp.ma_nguoi_dung = m.ma_nguoi_dung
        WHERE m.vai_tro = 'Mentor'
        GROUP BY COALESCE(NULLIF(TRIM(mp.chuyen_mon), ''), 'Chưa cập nhật')
        ORDER BY mentors DESC, name
    """).fetchall()

    account_stats = db.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN vai_tro IN ('Admin', 'HR') THEN 1 ELSE 0 END) AS managers,
               SUM(CASE WHEN vai_tro = 'Mentor' THEN 1 ELSE 0 END) AS mentors,
               SUM(CASE WHEN vai_tro = 'ThucTapSinh' THEN 1 ELSE 0 END) AS interns,
               SUM(CASE WHEN trang_thai = 'HoatDong' THEN 1 ELSE 0 END) AS active,
               SUM(CASE WHEN trang_thai = 'Khoa' THEN 1 ELSE 0 END) AS locked,
               SUM(CASE WHEN trang_thai = 'ChoDuyet' THEN 1 ELSE 0 END) AS pending
        FROM NGUOI_DUNG
    """).fetchone()

    def count_value(row: Any, key: str) -> int:
        return int(row[key] or 0)

    intern_total = count_value(intern_stats, "total")
    approved_interns = count_value(intern_stats, "approved")
    assigned = count_value(intern_stats, "assigned")
    total_mentors = count_value(mentor_stats, "total")
    assigned_mentors = count_value(mentor_stats, "assigned_mentors")
    mentor_interns = count_value(mentor_stats, "assigned_interns")
    return {
        "filters": {"ma_phong_ban": ma_phong_ban, "ma_truong": ma_truong},
        "interns": {
            "total": intern_total,
            "approved": count_value(intern_stats, "approved"),
            "pending": count_value(intern_stats, "pending"),
            "rejected": count_value(intern_stats, "rejected"),
            "in_progress": count_value(intern_stats, "in_progress"),
            "completed": count_value(intern_stats, "completed"),
            "withdrawn": count_value(intern_stats, "withdrawn"),
            "assigned": assigned,
            "unassigned": max(approved_interns - assigned, 0),
            "universities": count_value(intern_stats, "universities"),
        },
        "programs": {
            "total": count_value(program_stats, "total"),
            "open": count_value(program_stats, "open"),
            "quota": count_value(program_stats, "quota"),
            "applicants": count_value(program_stats, "applicants"),
            "pending_applicants": count_value(program_stats, "pending_applicants"),
            "breakdown": [dict(row) for row in program_breakdown],
        },
        "mentors": {
            "total": total_mentors,
            "assigned_mentors": assigned_mentors,
            "assigned_interns": mentor_interns,
            "average_interns": round(mentor_interns / total_mentors, 1) if total_mentors else 0,
            "departments": [dict(row) for row in mentor_departments],
            "expertise": [dict(row) for row in mentor_expertise],
        },
        "accounts": {
            "total": count_value(account_stats, "total"),
            "managers": count_value(account_stats, "managers"),
            "mentors": count_value(account_stats, "mentors"),
            "interns": count_value(account_stats, "interns"),
            "active": count_value(account_stats, "active"),
            "locked": count_value(account_stats, "locked"),
            "pending": count_value(account_stats, "pending"),
        },
    }
