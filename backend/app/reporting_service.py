"""Read-only reporting queries shared by the dashboard and file exports."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil


MISSING = "Chưa cập nhật"
KNOWN_MAJOR_SQL = "NULLIF(NULLIF(TRIM(h.chuyen_nganh), ''), 'Chưa cập nhật')"
MAJOR_SQL = f"COALESCE({KNOWN_MAJOR_SQL}, 'Chưa cập nhật')"
PROFILE_FROM = """
    FROM HO_SO_THUC_TAP h
    JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = h.ma_nguoi_dung
    LEFT JOIN TRUONG_DAI_HOC t ON t.ma_truong = h.ma_truong
    LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban
"""


@dataclass(frozen=True)
class InternStatisticsFilters:
    program_id: int | None = None
    department_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    school_id: int | None = None  # 0 selects profiles without a university.
    major: str | None = None
    search: str | None = None


class InternStatisticsService:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _where(filters: InternStatisticsFilters):
        clauses = ["u.vai_tro = 'ThucTapSinh'"]
        params = []
        if filters.program_id is not None:
            clauses.append("""EXISTS (
                SELECT 1 FROM UNG_TUYEN_CHUONG_TRINH a
                WHERE a.ma_ho_so = h.ma_ho_so
                  AND a.ma_chuong_trinh = ? AND a.trang_thai = 'DaDuyet'
            )""")
            params.append(filters.program_id)
        if filters.department_id is not None:
            clauses.append("u.ma_phong_ban = ?")
            params.append(filters.department_id)
        if filters.date_from is not None:
            clauses.append("h.ngay_tao >= ?")
            params.append(filters.date_from.isoformat())
        if filters.date_to is not None:
            if filters.date_to == date.max:
                clauses.append("h.ngay_tao <= ?")
                params.append("9999-12-31 23:59:59")
            else:
                clauses.append("h.ngay_tao < ?")
                params.append((filters.date_to + timedelta(days=1)).isoformat())
        if filters.school_id == 0:
            clauses.append("h.ma_truong IS NULL")
        elif filters.school_id is not None:
            clauses.append("h.ma_truong = ?")
            params.append(filters.school_id)
        if filters.major is not None:
            clauses.append(f"{MAJOR_SQL} = ?")
            params.append(filters.major)
        if filters.search:
            clauses.append("(u.ho_ten LIKE ? OR u.email LIKE ? OR h.chuyen_nganh LIKE ?)")
            term = f"%{filters.search}%"
            params.extend((term, term, term))
        return " WHERE " + " AND ".join(clauses), params

    def overview(self, filters: InternStatisticsFilters, page: int, page_size: int):
        where, params = self._where(filters)
        summary = self.db.execute(f"""
            SELECT COUNT(*) AS unique_interns,
                   COUNT(DISTINCT h.ma_truong) AS known_schools,
                   COUNT(DISTINCT {KNOWN_MAJOR_SQL}) AS known_majors,
                   SUM(CASE WHEN h.ma_truong IS NULL THEN 1 ELSE 0 END) AS missing_school,
                   SUM(CASE WHEN {KNOWN_MAJOR_SQL} IS NULL THEN 1 ELSE 0 END) AS missing_major
            {PROFILE_FROM} {where}
        """, params).fetchone()
        schools = self.db.execute(f"""
            SELECT h.ma_truong AS id, COALESCE(t.ten_truong, '{MISSING}') AS name,
                   COUNT(*) AS interns
            {PROFILE_FROM} {where}
            GROUP BY h.ma_truong, t.ten_truong
            ORDER BY interns DESC, name ASC
        """, params).fetchall()
        majors = self.db.execute(f"""
            SELECT {MAJOR_SQL} AS name, COUNT(*) AS interns
            {PROFILE_FROM} {where}
            GROUP BY {MAJOR_SQL}
            ORDER BY interns DESC, name ASC
        """, params).fetchall()
        participations = self.db.execute(f"""
            SELECT COUNT(*) AS total
            {PROFILE_FROM}
            JOIN UNG_TUYEN_CHUONG_TRINH approved
              ON approved.ma_ho_so = h.ma_ho_so AND approved.trang_thai = 'DaDuyet'
              {'AND approved.ma_chuong_trinh = ?' if filters.program_id is not None else ''}
            {where}
        """, ([filters.program_id] if filters.program_id is not None else []) + params).fetchone()
        total = int(summary["unique_interns"] or 0)
        total_pages = ceil(total / page_size) if total else 0
        effective_page = min(page, total_pages) if total_pages else 1
        return {
            "filters": {
                "program_id": filters.program_id,
                "department_id": filters.department_id,
                "date_from": filters.date_from.isoformat() if filters.date_from else None,
                "date_to": filters.date_to.isoformat() if filters.date_to else None,
                "school_id": filters.school_id,
                "major": filters.major,
                "search": filters.search,
                "date_basis": "Ngày tạo hồ sơ TTS",
            },
            "summary": {
                "unique_interns": total,
                "approved_participations": int(participations["total"] or 0),
                "known_schools": int(summary["known_schools"] or 0),
                "known_majors": int(summary["known_majors"] or 0),
                "missing_school": int(summary["missing_school"] or 0),
                "missing_major": int(summary["missing_major"] or 0),
            },
            "schools": [dict(row) for row in schools],
            "majors": [dict(row) for row in majors],
            "items": self.detail_page(filters, effective_page, page_size),
            "page": effective_page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
        }

    def detail_page(self, filters: InternStatisticsFilters, page: int, page_size: int):
        where, params = self._where(filters)
        rows = self.db.execute(f"""
            SELECT h.ma_ho_so, u.ho_ten, u.email, h.ma_truong,
                   COALESCE(t.ten_truong, '{MISSING}') AS ten_truong,
                   {MAJOR_SQL} AS chuyen_nganh,
                   COALESCE(p.ten_phong_ban, '{MISSING}') AS ten_phong_ban,
                   h.trang_thai_xet_duyet, h.ngay_tao
            {PROFILE_FROM} {where}
            ORDER BY h.ma_ho_so DESC
            LIMIT ? OFFSET ?
        """, [*params, page_size, (page - 1) * page_size]).fetchall()
        return [dict(row) for row in rows]

    def iter_details(self, filters: InternStatisticsFilters, total: int, batch_size: int = 500):
        for page in range(1, ceil(total / batch_size) + 1):
            yield from self.detail_page(filters, page, batch_size)

    def options(self):
        programs = self.db.execute("""
            SELECT ma_chuong_trinh AS id, ten_ct AS name
            FROM CHUONG_TRINH_THUC_TAP ORDER BY ten_ct, ma_chuong_trinh
        """).fetchall()
        departments = self.db.execute("""
            SELECT ma_phong_ban AS id, ten_phong_ban AS name
            FROM PHONG_BAN ORDER BY ten_phong_ban, ma_phong_ban
        """).fetchall()
        return {
            "programs": [dict(row) for row in programs],
            "departments": [dict(row) for row in departments],
        }
