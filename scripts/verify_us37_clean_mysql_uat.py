"""Report safe counts for the isolated US37 UAT schema without assuming it is empty."""
from __future__ import annotations

from app import database


EXPECTED_SCHEMA = "ims_us37_clean_uat"


def main() -> None:
    if database.DATABASE_BACKEND != "mysql":
        raise SystemExit("IMS is not using MySQL.")
    connection = database.get_db_connection()
    try:
        schema = connection.execute("SELECT DATABASE() AS schema_name").fetchone()["schema_name"]
        if schema != EXPECTED_SCHEMA:
            raise SystemExit("IMS connected to an unexpected database.")
        checks = {
            "users": "SELECT COUNT(*) AS n FROM NGUOI_DUNG",
            "intern_profiles": "SELECT COUNT(*) AS n FROM HO_SO_THUC_TAP",
            "hrm_directory": "SELECT COUNT(*) AS n FROM HRM_EMPLOYEE_DIRECTORY",
            "department_mappings": "SELECT COUNT(*) AS n FROM HRM_DEPARTMENT_MAPPINGS",
        }
        counts = {
            name: int(connection.execute(statement).fetchone()["n"])
            for name, statement in checks.items()
        }
        accounts = connection.execute(
            "SELECT email, vai_tro FROM NGUOI_DUNG "
            "WHERE email IN ('admin@internship.vn', 'hr@internship.vn')"
        ).fetchall()
        roles = {str(row["email"]): str(row["vai_tro"]) for row in accounts}
        if roles.get("admin@internship.vn") != "Admin" or roles.get("hr@internship.vn") != "HR":
            raise SystemExit("The expected local UAT Admin and HR accounts are missing or have the wrong role.")
    finally:
        connection.close()
    print("IMS_DATABASE=ims_us37_clean_uat")
    print(f"IMS_UAT_ACCOUNTS={counts['users']}")
    print(f"IMS_INTERN_PROFILES={counts['intern_profiles']}")
    print(f"IMS_HRM_DIRECTORY={counts['hrm_directory']}")
    print(f"IMS_DEPARTMENT_MAPPINGS={counts['department_mappings']}")


if __name__ == "__main__":
    main()
