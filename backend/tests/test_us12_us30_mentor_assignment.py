"""US12 + US30: Comprehensive tests for program-scoped Mentor assignment and sequential internship participation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, status
from app import database
from app.mentor_assignment_service import (
    assign_mentor_canonical,
    check_program_overlap,
    count_mentor_active_interns,
    get_intern_active_assignment,
    get_intern_active_program,
    get_intern_approved_programs,
    get_timeline_status,
    unassign_mentor_canonical,
)
from app.routes import auth_routes, intern_routes, mentor_routes, program_routes
from app.schemas import WeeklyReportCreate, WeeklyReportReview
from app.weekly_report_service import WeeklyReportService


def make_request(user=None, ip="127.0.0.1"):
    return SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        client=SimpleNamespace(host=ip),
    )


class US12US30MentorAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-us12-us30-")
        cls.db_path = Path(cls.temp_dir.name) / "us12_us30.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

        cls.http_app = FastAPI()

        @cls.http_app.middleware("http")
        async def add_test_identity(request, call_next):
            request.state.current_user = request.scope.get("state", {}).get("test_user")
            return await call_next(request)

        async def override_db():
            yield cls.active_db

        cls.http_app.dependency_overrides[database.get_db] = override_db
        cls.http_app.include_router(auth_routes.router)
        cls.http_app.include_router(program_routes.router)
        cls.http_app.include_router(mentor_routes.router)
        cls.http_app.include_router(intern_routes.router)
        cls.active_db = None

        db = database.get_db_connection()
        dept = db.execute("SELECT ma_phong_ban FROM PHONG_BAN ORDER BY ma_phong_ban LIMIT 1").fetchone()
        cls.dept_id = dept["ma_phong_ban"] if dept else 1

        db.execute("""
            INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta)
            VALUES ('Phòng R&D', 'Nghiên cứu và phát triển')
        """)
        cls.rnd_dept_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Seed Admin, HR, Mentors
        db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, 'Admin User', 'admin.assignment@example.com', 'hash', 'Admin', 'HoatDong')
        """, (cls.dept_id,))
        cls.admin_user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, 'HR User', 'hr.assignment@example.com', 'hash', 'HR', 'HoatDong')
        """, (cls.dept_id,))
        cls.hr_user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, 'Mentor Alice', 'mentor.alice@example.com', 'hash', 'Mentor', 'HoatDong')
        """, (cls.dept_id,))
        cls.mentor_alice_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da) VALUES (?, 100)", (cls.mentor_alice_id,))

        db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, 'Mentor Bob', 'mentor.bob@example.com', 'hash', 'Mentor', 'HoatDong')
        """, (cls.dept_id,))
        cls.mentor_bob_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da) VALUES (?, 100)", (cls.mentor_bob_id,))

        # Mentor in R&D department
        db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, 'Mentor Carol RND', 'mentor.carol@example.com', 'hash', 'Mentor', 'HoatDong')
        """, (cls.rnd_dept_id,))
        cls.mentor_carol_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("INSERT INTO MENTOR_PROFILE (ma_nguoi_dung, so_tts_toi_da) VALUES (?, 100)", (cls.mentor_carol_id,))

        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.db.execute("DELETE FROM NHAN_XET_BAO_CAO_TUAN")
        self.db.execute("DELETE FROM BAO_CAO_TUAN")
        self.db.execute("DELETE FROM PHAN_CONG_MENTOR_TTS")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    async def _asgi_request_async(self, method, path, user=None, body=b"", content_type=None):
        headers = [(b"host", b"testserver"), (b"content-length", str(len(body)).encode())]
        if content_type:
            headers.append((b"content-type", content_type.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {"test_user": user},
        }
        request_sent = False
        events = []

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(event):
            events.append(event)

        await self.http_app(scope, receive, send)
        response_start = next(event for event in events if event["type"] == "http.response.start")
        response_body = b"".join(
            event.get("body", b"") for event in events if event["type"] == "http.response.body"
        )
        parsed = json.loads(response_body) if response_body else None
        return response_start["status"], parsed

    def _http_request(self, method, path, user=None, body=b"", content_type=None):
        type(self).active_db = self.db
        return asyncio.run(self._asgi_request_async(method, path, user, body, content_type))

    def _create_intern(self, email_suffix: str) -> tuple[int, int]:
        cur = self.db.execute("""
            INSERT INTO NGUOI_DUNG (ma_phong_ban, ho_ten, email, mat_khau, vai_tro, trang_thai)
            VALUES (?, ?, ?, 'hash', 'ThucTapSinh', 'HoatDong')
        """, (self.dept_id, f"Intern {email_suffix}", f"intern.{email_suffix}@example.com"))
        user_id = cur.lastrowid
        cur2 = self.db.execute("""
            INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, trang_thai_xet_duyet, trang_thai_thuc_tap)
            VALUES (?, 'DaDuyet', 'DangThucTap')
        """, (user_id,))
        profile_id = cur2.lastrowid
        self.db.commit()
        return user_id, profile_id

    def _create_program(self, code: str, start: str, end: str, dept_id: int | None = None) -> int:
        cur = self.db.execute("""
            INSERT INTO CHUONG_TRINH_THUC_TAP (ma_ct, ten_ct, ma_phong_ban, ngay_bat_dau, ngay_ket_thuc, chi_tieu, trang_thai)
            VALUES (?, ?, ?, ?, ?, 10, 'DangMo')
        """, (code, f"Chương trình {code}", dept_id or self.dept_id, start, end))
        prog_id = cur.lastrowid
        self.db.commit()
        return prog_id

    def _apply_and_approve(self, profile_id: int, program_id: int) -> int:
        cur = self.db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai, ngay_xet_duyet)
            VALUES (?, ?, 'DaDuyet', CURRENT_TIMESTAMP)
        """, (program_id, profile_id))
        app_id = cur.lastrowid
        self.db.commit()
        return app_id

    def _apply_pending(self, profile_id: int, program_id: int) -> int:
        cur = self.db.execute("""
            INSERT INTO UNG_TUYEN_CHUONG_TRINH (ma_chuong_trinh, ma_ho_so, trang_thai)
            VALUES (?, ?, 'ChoDuyet')
        """, (program_id, profile_id))
        app_id = cur.lastrowid
        self.db.commit()
        return app_id

    # =========================================================================
    # Test 1: Fresh and Migrated Schema
    # =========================================================================
    def test_schema_columns_and_constraints(self):
        """Verifies PHAN_CONG_MENTOR_TTS has ma_chuong_trinh, ma_ung_tuyen, and composite unique."""
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(PHAN_CONG_MENTOR_TTS)").fetchall()}
        self.assertIn("ma_chuong_trinh", columns)
        self.assertIn("ma_ung_tuyen", columns)
        self.assertIn("ma_ho_so", columns)
        self.assertIn("ma_nguoi_dung_mentor", columns)

    # =========================================================================
    # Test 2: Basic Assignment (Section 73)
    # =========================================================================
    def test_basic_assignment(self):
        """HR/Admin assigns valid Mentor to approved application."""
        user_id, profile_id = self._create_intern("basic")
        prog_id = self._create_program("BASIC-P1", "2026-10-01", "2026-12-31")
        app_id = self._apply_and_approve(profile_id, prog_id)

        res = assign_mentor_canonical(
            self.db,
            mentor_id=self.mentor_alice_id,
            profile_id=profile_id,
            program_id=prog_id,
            application_id=app_id,
            assigned_by=self.hr_user_id,
        )
        self.db.commit()

        self.assertIn("ma_phan_cong", res)
        self.assertEqual(res["mentor_id"], self.mentor_alice_id)
        self.assertEqual(res["profile_id"], profile_id)
        self.assertEqual(res["program_id"], prog_id)

        row = self.db.execute("""
            SELECT ma_nguoi_dung_mentor, ma_ho_so, ma_chuong_trinh, ma_ung_tuyen, ma_nguoi_phan_cong
            FROM PHAN_CONG_MENTOR_TTS WHERE ma_phan_cong = ?
        """, (res["ma_phan_cong"],)).fetchone()
        self.assertEqual(row["ma_nguoi_dung_mentor"], self.mentor_alice_id)
        self.assertEqual(row["ma_ho_so"], profile_id)
        self.assertEqual(row["ma_chuong_trinh"], prog_id)
        self.assertEqual(row["ma_ung_tuyen"], app_id)
        self.assertEqual(row["ma_nguoi_phan_cong"], self.hr_user_id)

    # =========================================================================
    # Test 3: Same TTS Sequential Programs (Section 74)
    # =========================================================================
    def test_same_tts_sequential_programs(self):
        """Sequential non-overlapping programs can both be approved and assigned different mentors."""
        user_id, profile_id = self._create_intern("sequential")
        p1 = self._create_program("SEQ-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("SEQ-P2", "2027-01-01", "2027-03-31")

        app1 = self._apply_and_approve(profile_id, p1)
        app2 = self._apply_and_approve(profile_id, p2)

        assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)
        assign_mentor_canonical(self.db, self.mentor_bob_id, profile_id, program_id=p2, application_id=app2)
        self.db.commit()

        assignments = self.db.execute("""
            SELECT ma_chuong_trinh, ma_nguoi_dung_mentor
            FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so = ? ORDER BY ma_chuong_trinh
        """, (profile_id,)).fetchall()
        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0]["ma_nguoi_dung_mentor"], self.mentor_alice_id)
        self.assertEqual(assignments[1]["ma_nguoi_dung_mentor"], self.mentor_bob_id)

    # =========================================================================
    # Test 4: Current + Upcoming (Section 75)
    # =========================================================================
    def test_current_and_upcoming_status(self):
        """During Program A: A is CURRENT, B is UPCOMING. Exactly 1 active program and 1 active mentor."""
        user_id, profile_id = self._create_intern("cur_up")
        p1 = self._create_program("TIMELINE-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("TIMELINE-P2", "2027-01-01", "2027-03-31")

        app1 = self._apply_and_approve(profile_id, p1)
        app2 = self._apply_and_approve(profile_id, p2)
        assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1)
        assign_mentor_canonical(self.db, self.mentor_bob_id, profile_id, program_id=p2)
        self.db.commit()

        ref_date = date(2026, 11, 15)  # Inside P1
        approved = get_intern_approved_programs(self.db, profile_id, as_of=ref_date)
        self.assertEqual(len(approved), 2)
        p1_info = next(p for p in approved if p["ma_chuong_trinh"] == p1)
        p2_info = next(p for p in approved if p["ma_chuong_trinh"] == p2)
        self.assertEqual(p1_info["timeline_status"], "CURRENT")
        self.assertEqual(p2_info["timeline_status"], "UPCOMING")

        active_prog = get_intern_active_program(self.db, profile_id, as_of=ref_date)
        self.assertIsNotNone(active_prog)
        self.assertEqual(active_prog["ma_chuong_trinh"], p1)

        active_mentor = get_intern_active_assignment(self.db, profile_id, as_of=ref_date)
        self.assertIsNotNone(active_mentor)
        self.assertEqual(active_mentor["ma_nguoi_dung"], self.mentor_alice_id)

    # =========================================================================
    # Test 5: Historical + Current (Section 76)
    # =========================================================================
    def test_historical_and_current_status(self):
        """During Program B: A is HISTORICAL, B is CURRENT. Mentor history is preserved."""
        user_id, profile_id = self._create_intern("hist_cur")
        p1 = self._create_program("HIST-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("HIST-P2", "2027-01-01", "2027-03-31")

        self._apply_and_approve(profile_id, p1)
        self._apply_and_approve(profile_id, p2)
        assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1)
        assign_mentor_canonical(self.db, self.mentor_bob_id, profile_id, program_id=p2)
        self.db.commit()

        ref_date = date(2027, 2, 1)  # Inside P2
        approved = get_intern_approved_programs(self.db, profile_id, as_of=ref_date)
        p1_info = next(p for p in approved if p["ma_chuong_trinh"] == p1)
        p2_info = next(p for p in approved if p["ma_chuong_trinh"] == p2)
        self.assertEqual(p1_info["timeline_status"], "HISTORICAL")
        self.assertEqual(p2_info["timeline_status"], "CURRENT")

        active_mentor = get_intern_active_assignment(self.db, profile_id, as_of=ref_date)
        self.assertEqual(active_mentor["ma_nguoi_dung"], self.mentor_bob_id)

    # =========================================================================
    # Test 6: Overlapping Approval Blocked (Section 77)
    # =========================================================================
    def test_overlapping_approval_blocked(self):
        """Approving a second overlapping program is blocked with 409 Conflict."""
        user_id, profile_id = self._create_intern("overlap_block")
        p1 = self._create_program("OVERLAP-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("OVERLAP-P2", "2026-11-01", "2027-01-31")

        app1 = self._apply_and_approve(profile_id, p1)
        app2 = self._apply_pending(profile_id, p2)

        # Attempt to approve app2 via HTTP
        hr_actor = {"ma_nguoi_dung": self.hr_user_id, "vai_tro": "HR", "ho_ten": "HR User"}
        status_code, body = self._http_request(
            "PUT",
            f"/api/programs/{p2}/applications/{app2}",
            user=hr_actor,
            body=json.dumps({"trang_thai": "DaDuyet"}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(status_code, status.HTTP_409_CONFLICT)
        self.assertIn("trùng lặp", body.get("detail", ""))

        # Check states remained intact
        app1_state = self.db.execute("SELECT trang_thai FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen = ?", (app1,)).fetchone()[0]
        app2_state = self.db.execute("SELECT trang_thai FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen = ?", (app2,)).fetchone()[0]
        self.assertEqual(app1_state, "DaDuyet")
        self.assertEqual(app2_state, "ChoDuyet")

    # =========================================================================
    # Test 7: Reverse Approval Order - First Approved Wins (Section 78)
    # =========================================================================
    def test_reverse_approval_order_first_approved_wins(self):
        """If P2 is approved first, P1 approval is blocked. First successful approval wins."""
        user_id, profile_id = self._create_intern("first_wins")
        p1 = self._create_program("WIN-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("WIN-P2", "2026-11-01", "2027-01-31")

        app1 = self._apply_pending(profile_id, p1)
        app2 = self._apply_pending(profile_id, p2)

        hr_actor = {"ma_nguoi_dung": self.hr_user_id, "vai_tro": "HR", "ho_ten": "HR User"}

        # Approve P2 first
        st2, _ = self._http_request(
            "PUT",
            f"/api/programs/{p2}/applications/{app2}",
            user=hr_actor,
            body=json.dumps({"trang_thai": "DaDuyet"}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(st2, status.HTTP_200_OK)

        # Attempt to approve P1
        st1, body1 = self._http_request(
            "PUT",
            f"/api/programs/{p1}/applications/{app1}",
            user=hr_actor,
            body=json.dumps({"trang_thai": "DaDuyet"}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(st1, status.HTTP_409_CONFLICT)
        self.assertIn("trùng lặp", body1.get("detail", ""))

    # =========================================================================
    # Test 8: Date Boundary Rules (Section 79)
    # =========================================================================
    def test_date_boundary_rules(self):
        """Program A ends 31/12, Program B starts 01/01 -> NO overlap. Program C starts 31/12 -> OVERLAP."""
        user_id, profile_id = self._create_intern("boundary")
        pa = self._create_program("BOUND-A", "2026-10-01", "2026-12-31")
        pb = self._create_program("BOUND-B", "2027-01-01", "2027-03-31")
        pc = self._create_program("BOUND-C", "2026-12-31", "2027-03-31")

        self._apply_and_approve(profile_id, pa)

        # B starts 01/01: no overlap
        conflict_b = check_program_overlap(self.db, profile_id, pb)
        self.assertIsNone(conflict_b)

        # C starts 31/12: overlap on 31/12 inclusive boundary
        conflict_c = check_program_overlap(self.db, profile_id, pc)
        self.assertIsNotNone(conflict_c)
        self.assertEqual(conflict_c["ma_chuong_trinh"], pa)

    # =========================================================================
    # Test 9: Concurrent Overlapping Approval (Section 80)
    # =========================================================================
    def test_concurrent_overlapping_approval(self):
        """Concurrent approval of two overlapping programs for the same intern allows only one winner."""
        user_id, profile_id = self._create_intern("concurrent_appr")
        p1 = self._create_program("CONC-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("CONC-P2", "2026-11-01", "2027-01-31")

        app1 = self._apply_pending(profile_id, p1)
        app2 = self._apply_pending(profile_id, p2)

        def approve_candidate(prog_id, app_id):
            conn = database.get_db_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conflict = check_program_overlap(conn, profile_id, prog_id)
                if conflict:
                    conn.rollback()
                    return 409
                cur = conn.execute("""
                    UPDATE UNG_TUYEN_CHUONG_TRINH
                    SET trang_thai = 'DaDuyet', ngay_xet_duyet = CURRENT_TIMESTAMP
                    WHERE ma_ung_tuyen = ? AND trang_thai = 'ChoDuyet'
                """, (app_id,))
                if cur.rowcount == 1:
                    conn.commit()
                    return 200
                conn.rollback()
                return 409
            except Exception:
                conn.rollback()
                return 500
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(approve_candidate, p1, app1)
            f2 = executor.submit(approve_candidate, p2, app2)
            results = [f1.result(), f2.result()]

        self.assertIn(200, results)
        self.assertIn(409, results)

        approved_count = self.db.execute("""
            SELECT COUNT(*) FROM UNG_TUYEN_CHUONG_TRINH
            WHERE ma_ho_so = ? AND trang_thai = 'DaDuyet'
        """, (profile_id,)).fetchone()[0]
        self.assertEqual(approved_count, 1)

    # =========================================================================
    # Test 10: Duplicate & Concurrent Assignment (Section 81, 82)
    # =========================================================================
    def test_duplicate_and_idempotent_assignment(self):
        """Assigning same mentor twice to same application is idempotent and creates one canonical row."""
        user_id, profile_id = self._create_intern("dup_assign")
        p1 = self._create_program("DUP-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id, p1)

        r1 = assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)
        self.db.commit()
        r2 = assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)
        self.db.commit()

        self.assertEqual(r1["ma_phan_cong"], r2["ma_phan_cong"])
        count = self.db.execute("""
            SELECT COUNT(*) FROM PHAN_CONG_MENTOR_TTS WHERE ma_ho_so = ? AND ma_chuong_trinh = ?
        """, (profile_id, p1)).fetchone()[0]
        self.assertEqual(count, 1)

    # =========================================================================
    # Test 11: Reassign Mentor (Section 83)
    # =========================================================================
    def test_reassign_mentor(self):
        """Reassigning mentor replaces the current mentor for that application context without duplicate active rows."""
        user_id, profile_id = self._create_intern("reassign")
        p1 = self._create_program("REASSIGN-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id, p1)

        r1 = assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)
        self.db.commit()

        # Reassign to Bob
        r2 = assign_mentor_canonical(self.db, self.mentor_bob_id, profile_id, program_id=p1, application_id=app1)
        self.db.commit()

        self.assertEqual(r1["ma_phan_cong"], r2["ma_phan_cong"])
        row = self.db.execute("SELECT ma_nguoi_dung_mentor FROM PHAN_CONG_MENTOR_TTS WHERE ma_phan_cong = ?", (r1["ma_phan_cong"],)).fetchone()
        self.assertEqual(row["ma_nguoi_dung_mentor"], self.mentor_bob_id)

    # =========================================================================
    # Test 12: Role RBAC (Section 84)
    # =========================================================================
    def test_role_rbac_assignment_endpoints(self):
        """Admin/HR allowed, Mentor/TTS blocked (403), Anonymous 401."""
        user_id, profile_id = self._create_intern("rbac")
        p1 = self._create_program("RBAC-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id, p1)

        url = f"/api/programs/{p1}/applications/{app1}/assign-mentor"
        payload = json.dumps({"mentor_id": self.mentor_alice_id}).encode("utf-8")

        # Anonymous -> 401
        st_anon, _ = self._http_request("POST", url, user=None, body=payload, content_type="application/json")
        self.assertEqual(st_anon, status.HTTP_401_UNAUTHORIZED)

        # TTS -> 403
        tts_actor = {"ma_nguoi_dung": user_id, "vai_tro": "ThucTapSinh", "ho_ten": "Intern"}
        st_tts, _ = self._http_request("POST", url, user=tts_actor, body=payload, content_type="application/json")
        self.assertEqual(st_tts, status.HTTP_403_FORBIDDEN)

        # Mentor -> 403
        mentor_actor = {"ma_nguoi_dung": self.mentor_alice_id, "vai_tro": "Mentor", "ho_ten": "Alice"}
        st_m, _ = self._http_request("POST", url, user=mentor_actor, body=payload, content_type="application/json")
        self.assertEqual(st_m, status.HTTP_403_FORBIDDEN)

        # HR -> 200
        hr_actor = {"ma_nguoi_dung": self.hr_user_id, "vai_tro": "HR", "ho_ten": "HR"}
        st_hr, _ = self._http_request("POST", url, user=hr_actor, body=payload, content_type="application/json")
        self.assertEqual(st_hr, status.HTTP_200_OK)

    # =========================================================================
    # Test 13: Invalid Mentor & Invalid Application (Section 85, 86)
    # =========================================================================
    def test_invalid_mentor_and_application(self):
        """Attempting to assign non-mentor user or non-eligible application is blocked."""
        user_id, profile_id = self._create_intern("invalid_check")
        p1 = self._create_program("INV-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id, p1)

        # Try assign Admin as mentor -> 404/400
        with self.assertRaises(HTTPException):
            assign_mentor_canonical(self.db, self.admin_user_id, profile_id, program_id=p1, application_id=app1)

        # Try assign TTS as mentor -> 404/400
        with self.assertRaises(HTTPException):
            assign_mentor_canonical(self.db, user_id, profile_id, program_id=p1, application_id=app1)

        # Try assign to rejected application
        self.db.execute("UPDATE UNG_TUYEN_CHUONG_TRINH SET trang_thai = 'TuChoi' WHERE ma_ung_tuyen = ?", (app1,))
        self.db.commit()
        with self.assertRaises(HTTPException):
            assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)

    # =========================================================================
    # Test 14: Context Forgery Protection (Section 87)
    # =========================================================================
    def test_context_forgery_is_prevented(self):
        """Client cannot spoof application to profile mismatch."""
        user_id1, profile_id1 = self._create_intern("forge1")
        user_id2, profile_id2 = self._create_intern("forge2")
        p1 = self._create_program("FORGE-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id1, p1)

        # Claim app1 belongs to profile_id2
        with self.assertRaises(HTTPException):
            assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id2, application_id=app1)

    # =========================================================================
    # Test 15: Department Derivation & Same Department Auth Rule (Section 88, 89)
    # =========================================================================
    def test_department_derivation_and_same_dept_does_not_grant_access(self):
        """TTS department in internship context is derived from program. Same department != authorization."""
        user_id, profile_id = self._create_intern("dept_test")
        intern_actor = {"ma_nguoi_dung": user_id, "vai_tro": "ThucTapSinh", "ho_ten": "Intern Dept"}
        # Program in R&D department
        p_rnd = self._create_program("DEPT-RND", "2026-10-01", "2026-12-31", dept_id=self.rnd_dept_id)
        app = self._apply_and_approve(profile_id, p_rnd)

        service = WeeklyReportService(self.db)
        report = service.create(intern_actor, WeeklyReportCreate(
            program_id=p_rnd,
            week_start=date(2026, 10, 5),
            work_content="R&D Task",
            results="Initial research",
            difficulties="None",
        ))
        service.submit(report["id"], intern_actor)

        # Mentor Carol is in R&D department, but NOT assigned to this TTS
        mentor_carol_actor = {"ma_nguoi_dung": self.mentor_carol_id, "vai_tro": "Mentor", "ho_ten": "Carol"}
        with self.assertRaises(HTTPException) as ctx:
            service.review(report["id"], mentor_carol_actor, WeeklyReportReview(comment="Good progress"))
        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)

        # Now assign Mentor Carol -> review permitted
        assign_mentor_canonical(self.db, self.mentor_carol_id, profile_id, program_id=p_rnd, application_id=app)
        self.db.commit()

        reviewed = service.review(report["id"], mentor_carol_actor, WeeklyReportReview(comment="Good progress"))
        self.assertEqual(reviewed["reviewed_by"], self.mentor_carol_id)

    # =========================================================================
    # Test 16: Program Isolation (Section 90)
    # =========================================================================
    def test_program_isolation_between_mentors(self):
        """Mentor X for Program A cannot review reports from Program B, and vice-versa."""
        user_id, profile_id = self._create_intern("isolation")
        intern_actor = {"ma_nguoi_dung": user_id, "vai_tro": "ThucTapSinh", "ho_ten": "Intern Isolation"}
        p1 = self._create_program("ISO-P1", "2026-10-01", "2026-12-31")
        p2 = self._create_program("ISO-P2", "2027-01-01", "2027-03-31")

        app1 = self._apply_and_approve(profile_id, p1)
        app2 = self._apply_and_approve(profile_id, p2)

        assign_mentor_canonical(self.db, self.mentor_alice_id, profile_id, program_id=p1, application_id=app1)
        assign_mentor_canonical(self.db, self.mentor_bob_id, profile_id, program_id=p2, application_id=app2)
        self.db.commit()

        service = WeeklyReportService(self.db)
        # Create and submit report in Program 2
        rep2 = service.create(intern_actor, WeeklyReportCreate(
            program_id=p2,
            week_start=date(2027, 1, 4),
            work_content="P2 tasks",
            results="Done",
            difficulties="None",
        ))
        service.submit(rep2["id"], intern_actor)

        # Mentor Alice (Program 1) attempts to review report of Program 2 -> 403 Forbidden
        mentor_alice_actor = {"ma_nguoi_dung": self.mentor_alice_id, "vai_tro": "Mentor", "ho_ten": "Alice"}
        with self.assertRaises(HTTPException) as ctx:
            service.review(rep2["id"], mentor_alice_actor, WeeklyReportReview(comment="Trying cross-program"))
        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)

        # Mentor Bob (Program 2) reviews -> allowed
        mentor_bob_actor = {"ma_nguoi_dung": self.mentor_bob_id, "vai_tro": "Mentor", "ho_ten": "Bob"}
        reviewed = service.review(rep2["id"], mentor_bob_actor, WeeklyReportReview(comment="Valid P2 review"))
        self.assertEqual(reviewed["reviewed_by"], self.mentor_bob_id)

    # =========================================================================
    # Test 17: HTTP End-to-End Program Application Assign & Unassign (Section 94)
    # =========================================================================
    def test_http_assign_and_unassign_workflow(self):
        """Full HTTP flow for program application mentor assignment and unassignment."""
        user_id, profile_id = self._create_intern("http_flow")
        p1 = self._create_program("HTTP-P1", "2026-10-01", "2026-12-31")
        app1 = self._apply_and_approve(profile_id, p1)

        hr_actor = {"ma_nguoi_dung": self.hr_user_id, "vai_tro": "HR", "ho_ten": "HR User"}

        # 1. Assign via Program route
        st_assign, data_assign = self._http_request(
            "POST",
            f"/api/programs/{p1}/applications/{app1}/assign-mentor",
            user=hr_actor,
            body=json.dumps({"mentor_id": self.mentor_alice_id}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(st_assign, status.HTTP_200_OK)
        self.assertEqual(data_assign["mentor_id"], self.mentor_alice_id)

        # 2. Verify applicant list reflects assigned mentor
        st_list, data_list = self._http_request(
            "GET",
            f"/api/programs/{p1}/applications",
            user=hr_actor,
        )
        self.assertEqual(st_list, status.HTTP_200_OK)
        target = next(a for a in data_list if a["ma_ung_tuyen"] == app1)
        self.assertEqual(target["ten_mentor"], "Mentor Alice")

        # 3. Unassign via Program route
        st_unassign, data_unassign = self._http_request(
            "DELETE",
            f"/api/programs/{p1}/applications/{app1}/unassign-mentor",
            user=hr_actor,
        )
        self.assertEqual(st_unassign, status.HTTP_200_OK)

        # 4. Applicant list reflects unassigned state
        st_list2, data_list2 = self._http_request(
            "GET",
            f"/api/programs/{p1}/applications",
            user=hr_actor,
        )
        self.assertEqual(st_list2, status.HTTP_200_OK)
        target2 = next(a for a in data_list2 if a["ma_ung_tuyen"] == app1)
        self.assertIsNone(target2.get("ten_mentor"))


if __name__ == "__main__":
    unittest.main()
