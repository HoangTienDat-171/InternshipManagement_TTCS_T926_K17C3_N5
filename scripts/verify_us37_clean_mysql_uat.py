"""Assert that clean US37 UAT points to its isolated MySQL schema and is empty."""
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
        if counts["intern_profiles"] or counts["hrm_directory"] or counts["department_mappings"]:
            raise SystemExit("Clean UAT contains unexpected demo, employee, or mapping records.")
        if counts["users"] != 2:
            raise SystemExit("Clean UAT does not contain exactly the two expected UAT accounts.")
    finally:
        connection.close()
    print("IMS_DATABASE=ims_us37_clean_uat")
    print("IMS_HRM_DIRECTORY=0")
    print("IMS_DEPARTMENT_MAPPINGS=0")


if __name__ == "__main__":
    main()
