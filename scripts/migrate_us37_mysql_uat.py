"""Initialize only the dedicated local MySQL database used for US37 UAT."""
from __future__ import annotations

import os
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import database  # noqa: E402
from app.hrm_storage import hrm_schema_ready  # noqa: E402

EXPECTED_SCHEMA = "internship_management_us37_uat"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
US37_MIGRATIONS = (
    "20261015_us37_bidirectional_workflows.sql",
    "20261015_us37_hrm_sandbox.sql",
    "20261015_us37_department_overrides.sql",
)


def require_uat_target() -> None:
    host = os.getenv("MYSQL_HOST", "").strip().lower()
    if (
        database.DATABASE_BACKEND != "mysql"
        or os.getenv("MYSQL_DATABASE", "").strip() != EXPECTED_SCHEMA
        or host not in LOCAL_HOSTS
    ):
        raise RuntimeError("Refusing schema initialization outside the local US37 MySQL UAT database.")
    connection = database.get_db_connection()
    try:
        identity = connection.execute(
            "SELECT DATABASE() AS schema_name, @@port AS server_port"
        ).fetchone()
        if not identity or identity["schema_name"] != EXPECTED_SCHEMA:
            raise RuntimeError("Connected MySQL schema did not match the isolated UAT target.")
        expected_port = int(os.getenv("MYSQL_PORT", "3306"))
        if int(identity["server_port"]) != expected_port:
            raise RuntimeError("Connected MySQL server port did not match the local UAT configuration.")
    finally:
        connection.close()


def apply_migration(path: Path) -> int:
    sql = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    connection = database.get_db_connection()
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return len(statements)


def main() -> None:
    require_uat_target()
    for name in ("NGUOI_DUNG", "HO_SO_THUC_TAP", "PHONG_BAN", "CHUONG_TRINH_THUC_TAP", "UNG_TUYEN_CHUONG_TRINH"):
        connection = database.get_db_connection()
        try:
            connection.execute(f"SELECT 1 FROM {name} LIMIT 0")
        finally:
            connection.close()

    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    applied = 0
    for name in US37_MIGRATIONS:
        path = migration_dir / name
        if not path.is_file():
            raise RuntimeError(f"Required US37 migration is missing: {name}")
        applied += apply_migration(path)

    connection = database.get_db_connection()
    try:
        if not hrm_schema_ready(connection):
            raise RuntimeError("US37 migration did not create every required table.")
        table_count = connection.execute(
            "SELECT COUNT(*) AS total FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
        ).fetchone()["total"]
    finally:
        connection.close()
    print(f"MySQL UAT schema ready; {table_count} tables; {applied} US37 migration statements applied.")


if __name__ == "__main__":
    main()
