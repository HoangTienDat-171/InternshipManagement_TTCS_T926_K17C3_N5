"""Exercise the shared ledger through real SQL and HTTP routing in isolated SQLite."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app import database
from app.allowance_service import AllowanceService
from app.routes import allowance_routes
from app.schemas import AllowanceCreate, AllowanceUpdate


class AllowanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ims-us25-us26-")
        cls.path = Path(cls.temp.name) / "allowances.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()
        conn = database.get_db_connection()
        cls.users = {}
        for role, name in [("Admin", "admin"), ("HR", "hr"), ("Mentor", "mentor"),
                           ("ThucTapSinh", "alice"), ("ThucTapSinh", "bob")]:
            user_id = conn.execute("""INSERT INTO NGUOI_DUNG
                (ho_ten,email,mat_khau,vai_tro,trang_thai) VALUES (?,?,'unused',?,'HoatDong')""",
                (name, name + "@allowances.example.test", role)).lastrowid
            cls.users[name] = {"ma_nguoi_dung": user_id, "vai_tro": role}
        cls.profiles = {}
        for name in ("alice", "bob"):
            cls.profiles[name] = conn.execute("""INSERT INTO HO_SO_THUC_TAP
                (ma_nguoi_dung,trang_thai_xet_duyet) VALUES (?,'DaDuyet')""",
                (cls.users[name]["ma_nguoi_dung"],)).lastrowid
        cls.programs = []
        for i in range(3):
            cls.programs.append(conn.execute("""INSERT INTO CHUONG_TRINH_THUC_TAP
                (ma_ct,ten_ct,chi_tieu,trang_thai) VALUES (?, ?, 10, 'DaDong')""",
                (f"ALLOW-{i}", f"Historical program {i}")).lastrowid)
        cls.applications = {}
        for name in ("alice", "bob"):
            for i, program in enumerate(cls.programs):
                cls.applications[name, i] = conn.execute("""INSERT INTO UNG_TUYEN_CHUONG_TRINH
                    (ma_chuong_trinh,ma_ho_so,trang_thai) VALUES (?,?,?)""",
                    (program, cls.profiles[name], "ChoDuyet" if i == 2 else "DaDuyet")).lastrowid
        conn.commit()
        conn.close()
        cls.http_app = FastAPI()

        async def test_identity(request, call_next):
            request.state.current_user = request.scope["state"]["test_user"]
            return await call_next(request)

        async def test_db():
            yield cls.active_db

        cls.http_app.middleware("http")(test_identity)
        cls.http_app.dependency_overrides[database.get_db] = test_db
        cls.http_app.include_router(allowance_routes.router)

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()
        self.__class__.active_db = self.db
        self.db.execute("DELETE FROM PHU_CAP_THUC_TAP")
        self.db.commit()
        self.service = AllowanceService(self.db)

    def tearDown(self):
        self.__class__.active_db = None
        self.db.close()

    def payload(self, name="alice", program=0, ky="2026-10", amount="1500000.50"):
        return {"ma_ung_tuyen": self.applications[name, program], "ky": ky,
                "so_tien": amount, "ghi_chu": "Monthly allowance"}

    def create(self, **kwargs):
        return self.service.save(AllowanceCreate(**self.payload(**kwargs)).model_dump(),
                                 self.users["hr"]["ma_nguoi_dung"])

    def http(self, method, path, user=None, body=None):
        body_bytes = json.dumps(body).encode() if body is not None else b""
        clean_path, _, query = path.partition("?")
        headers = [(b"host", b"testserver"), (b"content-type", b"application/json")]
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                 "http_version": "1.1", "method": method, "scheme": "http",
                 "path": clean_path, "raw_path": clean_path.encode(), "query_string": query.encode(),
                 "headers": headers, "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
                 "state": {"test_user": self.users.get(user)}}
        result = {"body": bytearray()}

        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                result["status"] = message["status"]
            elif message["type"] == "http.response.body":
                result["body"].extend(message.get("body", b""))

        asyncio.run(self.http_app(scope, receive, send))
        return result["status"], json.loads(result["body"])

    def test_hr_create_and_admin_update_are_visible_to_intern(self):
        status, created = self.http("POST", "/api/allowances", "hr", self.payload())
        self.assertEqual(status, 201)
        status, mine = self.http("GET", "/api/interns/me/allowances", "alice")
        self.assertEqual(status, 200)
        self.assertEqual(mine["items"][0]["so_tien"], "1500000.50")
        self.assertEqual(mine["items"][0]["ma_chuong_trinh"], self.programs[0])
        status, updated = self.http("PUT", f"/api/allowances/{created['id']}", "admin",
                                    {"ky": "2026-09", "so_tien": "1800000.01", "ghi_chu": "Updated"})
        self.assertEqual(status, 200)
        status, detail = self.http("GET", f"/api/interns/me/allowances/{created['id']}", "alice")
        self.assertEqual(detail["so_tien"], "1800000.01")
        self.assertEqual(detail["ghi_chu"], "Updated")
        self.assertEqual(detail["ky"], "2026-09")
        self.assertEqual(updated["created_by"], self.users["hr"]["ma_nguoi_dung"])
        self.assertEqual(updated["updated_by"], self.users["admin"]["ma_nguoi_dung"])
        self.assertEqual(updated["created_at"], created["created_at"])
        self.assertGreater(updated["updated_at"], created["updated_at"])
        self.assertEqual(updated["ma_ung_tuyen"], created["ma_ung_tuyen"])

    def test_money_boundaries_exact_storage(self):
        for i, amount in enumerate(["0", "0.01", "9999999999999.99"]):
            with self.subTest(amount=amount):
                row = self.create(ky=f"2026-{i+1:02d}", amount=amount)
                stored = self.db.execute("SELECT so_tien_minor FROM PHU_CAP_THUC_TAP WHERE id=?",
                                         (row["id"],)).fetchone()[0]
                self.assertIsInstance(stored, int)
                self.assertEqual(Decimal(row["so_tien"]), Decimal(amount))
                self.assertEqual(stored, int(Decimal(amount) * 100))

    def test_both_management_roles_can_create_read_and_update(self):
        for i, user in enumerate(["admin", "hr"]):
            status, row = self.http("POST", "/api/allowances", user,
                                    self.payload(ky=f"2026-{i+1:02d}"))
            self.assertEqual(status, 201)
            self.assertEqual(row["created_by"], self.users[user]["ma_nguoi_dung"])
            self.assertEqual(self.http("GET", f"/api/allowances/{row['id']}", user)[0], 200)
            self.assertEqual(self.http("PUT", f"/api/allowances/{row['id']}", user,
                {"ky": row["ky"], "so_tien": "2500000", "ghi_chu": ""})[0], 200)

    def test_self_program_filter_is_scoped_to_session(self):
        program = self.db.execute("""INSERT INTO CHUONG_TRINH_THUC_TAP
            (ma_ct,ten_ct,chi_tieu,trang_thai) VALUES ('BOB-ONLY','Bob only',5,'DangMo')""").lastrowid
        app_id = self.db.execute("""INSERT INTO UNG_TUYEN_CHUONG_TRINH
            (ma_chuong_trinh,ma_ho_so,trang_thai) VALUES (?,?,'DaDuyet')""",
            (program, self.profiles["bob"])).lastrowid
        self.db.commit()
        try:
            data = self.http("GET", "/api/interns/me/allowance-programs", "alice")[1]
            self.assertNotIn(program, [row["ma_chuong_trinh"] for row in data])
            self.assertEqual(self.http("GET", f"/api/interns/me/allowances?program_id={program}", "alice")[1]["total"], 0)
        finally:
            self.db.execute("DELETE FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen=?", (app_id,))
            self.db.execute("DELETE FROM CHUONG_TRINH_THUC_TAP WHERE ma_chuong_trinh=?", (program,))
            self.db.commit()

    def test_invalid_amounts_rejected_without_rows(self):
        for amount in ["-0.01", "10000000000000", "1.001", "NaN", "Infinity", True, 0.1, "x"]:
            with self.subTest(amount=amount):
                status, _ = self.http("POST", "/api/allowances", "hr", self.payload(amount=amount))
                self.assertEqual(status, 422)
        self.assertEqual(self.service.list_records()["total"], 0)

    def test_invalid_periods_and_query_bounds(self):
        for ky in ["2026-00", "2026-13", "2026-1", "2026-10-01", "0000-01", "abcd-10"]:
            with self.subTest(ky=ky):
                self.assertEqual(self.http("POST", "/api/allowances", "hr", self.payload(ky=ky))[0], 422)
                self.assertEqual(self.http("GET", "/api/allowances?ky=" + ky, "hr")[0], 422)
        for query in ["page=0", "page_size=101", "year=999", "program_id=0", "search=" + "x"*101]:
            self.assertEqual(self.http("GET", "/api/allowances?" + query, "hr")[0], 422)

    def test_duplicate_profile_month_across_programs_and_database_unique(self):
        self.create()
        with self.assertRaises(HTTPException) as ctx:
            self.create(program=1)
        self.assertEqual(ctx.exception.status_code, 409)
        # Bypass API to independently verify the database business key.
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""INSERT INTO PHU_CAP_THUC_TAP
                (ma_ho_so,ma_ung_tuyen,ky,so_tien_minor,created_by,updated_by)
                VALUES (?,?, '2026-10',100,?,?)""", (self.profiles["alice"],
                self.applications["alice",1], self.users["hr"]["ma_nguoi_dung"], self.users["hr"]["ma_nguoi_dung"]))
        self.db.rollback()
        self.assertEqual(self.service.list_records()["total"], 1)

    def test_update_duplicate_preserves_previous_record(self):
        first = self.create(ky="2026-09")
        second = self.create()
        status, _ = self.http("PUT", f"/api/allowances/{second['id']}", "hr",
                              {"ky": first["ky"], "so_tien": "0", "ghi_chu": "Must not persist"})
        self.assertEqual(status, 409)
        self.assertEqual(self.service.detail(second["id"]), second)

    def test_concurrent_create_has_one_winner(self):
        barrier = Barrier(2)
        data = AllowanceCreate(**self.payload()).model_dump()

        def submit():
            conn = database.get_db_connection()
            try:
                barrier.wait(timeout=5)
                AllowanceService(conn).save(data, self.users["hr"]["ma_nguoi_dung"])
                return 201
            except HTTPException as exc:
                return exc.status_code
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: submit(), range(2))), [201, 409])
        self.assertEqual(self.service.list_records()["total"], 1)

    def test_unauthenticated_all_endpoints(self):
        for path in ["/api/allowances", "/api/allowances/profiles", "/api/allowances/programs",
                     "/api/allowances/1", "/api/interns/me/allowances", "/api/interns/me/allowances/1",
                     "/api/interns/me/allowance-programs"]:
            self.assertEqual(self.http("GET", path)[0], 401)

    def test_mentor_and_intern_cannot_access_manager_or_write(self):
        row = self.create()
        for user in ["mentor", "alice"]:
            for path in ["/api/allowances", "/api/allowances/profiles", "/api/allowances/programs", f"/api/allowances/{row['id']}"]:
                self.assertEqual(self.http("GET", path, user)[0], 403)
            self.assertEqual(self.http("POST", "/api/allowances", user, self.payload())[0], 403)
            self.assertEqual(self.http("PUT", f"/api/allowances/{row['id']}", user,
                                      {"ky":"2026-10","so_tien":"1"})[0], 403)

    def test_self_detail_idor_and_query_owner_spoof(self):
        alice = self.create()
        bob = self.create(name="bob")
        status, _ = self.http("GET", f"/api/interns/me/allowances/{bob['id']}", "alice")
        self.assertEqual(status, 404)
        status, data = self.http("GET", f"/api/interns/me/allowances?user_id={self.users['bob']['ma_nguoi_dung']}", "alice")
        self.assertEqual(status, 200)
        self.assertEqual([r["id"] for r in data["items"]], [alice["id"]])
        for role in ["admin", "hr", "mentor"]:
            self.assertEqual(self.http("GET", "/api/interns/me/allowances", role)[0], 403)

    def test_self_api_is_read_only(self):
        row = self.create()
        for method, path in [("POST", "/api/interns/me/allowances"),
                             ("PUT", f"/api/interns/me/allowances/{row['id']}"),
                             ("DELETE", f"/api/interns/me/allowances/{row['id']}")]:
            self.assertEqual(self.http(method, path, "alice", self.payload())[0], 405)

    def test_missing_and_unapproved_profiles_are_rejected(self):
        invalid = self.payload(program=2)
        self.assertEqual(self.http("POST", "/api/allowances", "hr", invalid)[0], 409)
        invalid["ma_ung_tuyen"] = 99999999
        self.assertEqual(self.http("POST", "/api/allowances", "hr", invalid)[0], 404)
        self.assertEqual(self.service.list_records()["total"], 0)

    def test_linkage_and_audit_fields_cannot_be_spoofed(self):
        for key in ["created_by", "updated_by", "created_at", "updated_at", "ma_ho_so", "ma_chuong_trinh"]:
            payload = {**self.payload(), key: "spoof"}
            self.assertEqual(self.http("POST", "/api/allowances", "hr", payload)[0], 422)
        row = self.create()
        for key in ["ma_ung_tuyen", "ma_ho_so", "created_by", "updated_by"]:
            self.assertEqual(self.http("PUT", f"/api/allowances/{row['id']}", "hr",
                {"ky":"2026-10", "so_tien":"1", key:1})[0], 422)

    def test_server_filter_pagination_and_sequential_program_history(self):
        self.create(ky="2026-09")
        self.create(program=1, ky="2027-01")
        self.create(name="bob", ky="2026-10")
        status, all_data = self.http("GET", "/api/allowances?page_size=1&page=2", "hr")
        self.assertEqual(status, 200)
        self.assertEqual(all_data["total"], 3)
        self.assertEqual(all_data["items"][0]["ky"], "2026-10")
        query = f"/api/allowances?search=alice&program_id={self.programs[1]}&year=2027&ky=2027-01&page_size=1"
        data = self.http("GET", query, "admin")[1]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["ma_ung_tuyen"], self.applications["alice",1])
        mine = self.http("GET", "/api/interns/me/allowances", "alice")[1]
        self.assertEqual(mine["total"], 2)
        self.assertEqual([r["ma_chuong_trinh"] for r in mine["items"]], [self.programs[1],self.programs[0]])
        self.assertEqual(self.http("GET", "/api/interns/me/allowances?year=2026", "alice")[1]["total"], 1)
        self.assertEqual(self.service.list_records(page=100)["items"], [])

    def test_empty_history_and_options_search_pagination(self):
        data = self.http("GET", "/api/interns/me/allowances", "alice")[1]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total"], 0)
        options = self.http("GET", "/api/allowances/profiles?search=alice&page_size=1&page=2", "hr")[1]
        self.assertEqual(options["total"], 2)
        self.assertEqual(len(options["items"]), 1)
        self.assertEqual(options["items"][0]["ma_ho_so"], self.profiles["alice"])
        options = self.service.options(program_id=self.programs[2])
        self.assertEqual(options["total"], 0)

    def test_database_checks_foreign_keys_and_init_is_repeatable(self):
        row = self.create()
        database.init_db()
        self.assertEqual(self.service.detail(row["id"])["so_tien"], row["so_tien"])
        for key, value in [("so_tien_minor", -1), ("so_tien_minor", 1.5),
                           ("ky", "2026-13"), ("ky", "2026-00"), ("ky", "x"),
                           ("ma_ho_so", 999999), ("ma_ung_tuyen", 999999)]:
            with self.subTest(column=key):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(f"UPDATE PHU_CAP_THUC_TAP SET {key}=? WHERE id=?", (value,row["id"]))
                self.db.rollback()
        fk = self.db.execute("PRAGMA foreign_key_list(PHU_CAP_THUC_TAP)").fetchall()
        self.assertEqual(len(fk), 4)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM UNG_TUYEN_CHUONG_TRINH WHERE ma_ung_tuyen=?", (row["ma_ung_tuyen"],))
        self.db.rollback()

    def test_note_length_and_whitespace(self):
        payload = self.payload()
        payload["ghi_chu"] = "x" * 1001
        self.assertEqual(self.http("POST", "/api/allowances", "hr", payload)[0], 422)
        payload["ghi_chu"] = "  Accepted note  "
        self.assertEqual(self.http("POST", "/api/allowances", "hr", payload)[1]["ghi_chu"], "Accepted note")


if __name__ == "__main__":
    unittest.main()
