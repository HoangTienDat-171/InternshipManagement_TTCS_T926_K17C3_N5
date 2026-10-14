from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import database
from app.routes.master_routes import create_department, create_university
from app.schemas import DepartmentCreate, UniversityCreate


def request_as(role):
    return SimpleNamespace(state=SimpleNamespace(current_user={"ma_nguoi_dung": 1, "vai_tro": role}))


class MasterDataCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="ims-master-catalog-")
        cls.db_path = Path(cls.temp_dir.name) / "catalog.sqlite3"
        cls.backend_patch = patch.object(database, "DATABASE_BACKEND", "sqlite")
        cls.path_patch = patch.object(database, "DB_FILE", str(cls.db_path))
        cls.backend_patch.start()
        cls.path_patch.start()
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.path_patch.stop()
        cls.backend_patch.stop()
        cls.temp_dir.cleanup()

    def setUp(self):
        self.db = database.get_db_connection()

    def tearDown(self):
        self.db.close()

    def test_hr_can_create_normalized_department_and_duplicate_is_rejected(self):
        name = f"Engineering {uuid4().hex}"
        result = create_department(DepartmentCreate(ten_phong_ban=f"  {name}   Team  "), request_as("HR"), self.db)
        self.assertEqual(result["ten_phong_ban"], f"{name} Team")

        with self.assertRaises(HTTPException) as error:
            create_department(DepartmentCreate(ten_phong_ban=f"  {name.upper()} TEAM  "), request_as("Admin"), self.db)
        self.assertEqual(error.exception.status_code, 409)

    def test_hr_can_create_university_and_duplicate_is_rejected(self):
        name = f"University {uuid4().hex}"
        result = create_university(UniversityCreate(ten_truong=f"  {name}   Campus  "), request_as("HR"), self.db)
        self.assertEqual(result["ten_truong"], f"{name} Campus")

        with self.assertRaises(HTTPException) as error:
            create_university(UniversityCreate(ten_truong=f" {name.upper()} CAMPUS "), request_as("HR"), self.db)
        self.assertEqual(error.exception.status_code, 409)

    def test_mentor_cannot_create_catalog_items_and_blank_names_are_invalid(self):
        with self.assertRaises(HTTPException) as error:
            create_department(DepartmentCreate(ten_phong_ban="Development"), request_as("Mentor"), self.db)
        self.assertEqual(error.exception.status_code, 403)

        with self.assertRaises(ValidationError):
            DepartmentCreate(ten_phong_ban="   ")
        with self.assertRaises(ValidationError):
            UniversityCreate(ten_truong="   ")


if __name__ == "__main__":
    unittest.main()
