from datetime import date, timedelta


class PersonalScheduleService:
    """Build the authenticated intern's calendar DTO from current data sources."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _date_value(value) -> date | None:
        if value is None:
            return None
        date_text = value.isoformat() if isinstance(value, date) else str(value)
        return date.fromisoformat(date_text[:10])

    def get_for_intern(
        self,
        intern_user_id: int,
        week_start: date | None = None,
        program_id: int | None = None,
    ) -> dict:
        """Return approved program periods and their currently assigned Mentor."""
        first_day = week_start or date.today()
        first_day -= timedelta(days=first_day.weekday())
        last_day = first_day + timedelta(days=6)

        # MySQL DATE values are date-only and are never converted through UTC.
        # Timestamp sources should follow the existing local-wall-clock DATETIME convention.
        rows = self.db.execute("""
            SELECT a.ma_ung_tuyen,
                   c.ma_chuong_trinh, c.ma_ct, c.ten_ct,
                   c.ngay_bat_dau, c.ngay_ket_thuc,
                   mentor.ma_nguoi_dung AS mentor_id, mentor.ho_ten AS mentor_name
            FROM HO_SO_THUC_TAP h
            JOIN NGUOI_DUNG intern ON intern.ma_nguoi_dung=h.ma_nguoi_dung
                AND intern.vai_tro='ThucTapSinh'
            JOIN UNG_TUYEN_CHUONG_TRINH a ON a.ma_ho_so=h.ma_ho_so
                AND a.trang_thai='DaDuyet'
            JOIN CHUONG_TRINH_THUC_TAP c ON c.ma_chuong_trinh=a.ma_chuong_trinh
            LEFT JOIN PHAN_CONG_MENTOR_TTS assignment ON assignment.ma_ho_so=h.ma_ho_so
                AND (assignment.ma_chuong_trinh=c.ma_chuong_trinh OR (assignment.ma_chuong_trinh IS NULL AND assignment.ma_ho_so=h.ma_ho_so))
            LEFT JOIN NGUOI_DUNG mentor ON mentor.ma_nguoi_dung=assignment.ma_nguoi_dung_mentor
                AND mentor.vai_tro='Mentor'
            WHERE h.ma_nguoi_dung=? AND h.trang_thai_xet_duyet='DaDuyet'
              AND (? IS NULL OR c.ma_chuong_trinh=?)
            ORDER BY c.ngay_bat_dau, c.ten_ct, a.ma_ung_tuyen
        """, (intern_user_id, program_id, program_id)).fetchall()

        programs = {}
        events = []
        for row in rows:
            start = self._date_value(row["ngay_bat_dau"])
            end = self._date_value(row["ngay_ket_thuc"])
            program = {
                "id": row["ma_chuong_trinh"],
                "code": row["ma_ct"],
                "name": row["ten_ct"],
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
            }
            programs[program["id"]] = program

            if not start or not end or end < start or end < first_day or start > last_day:
                continue

            events.append({
                "id": f"application-{row['ma_ung_tuyen']}",
                "type": "PROGRAM_PERIOD",
                "title": row["ten_ct"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "all_day": True,
                "status": "APPROVED",
                "program": program,
                "mentor": {"name": row["mentor_name"]} if row["mentor_id"] else None,
            })

        missing_mentor = any(row["mentor_id"] is None for row in rows)
        has_program = bool(rows)
        has_mentor = any(row["mentor_id"] is not None for row in rows)
        return {
            "week": {"start_date": first_day.isoformat(), "end_date": last_day.isoformat()},
            "events": events,
            "filters": {"programs": list(programs.values())},
            "has_program": has_program,
            "has_mentor": has_mentor,
            "warning": not has_program or missing_mentor,
        }
