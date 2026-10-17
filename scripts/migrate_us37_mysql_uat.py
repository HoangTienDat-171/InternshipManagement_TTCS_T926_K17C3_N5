"""Initialize only the dedicated local MySQL database used for US37 UAT."""
from __future__ import annotations

import os
import re
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import database  # noqa: E402
from app.hrm_storage import hrm_schema_ready  # noqa: E402

ALLOWED_SCHEMAS = {"internship_management_us37_uat", "ims_us37_clean_uat"}
EXPECTED_SCHEMA = os.getenv("US37_MYSQL_UAT_SCHEMA", "internship_management_us37_uat").strip()
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
US37_MIGRATIONS = (
    "20261015_us37_bidirectional_workflows.sql",
    "20261015_us37_hrm_sandbox.sql",
    "20261015_us37_department_overrides.sql",
    "20261016_master_data_and_hrm_connections.sql",
)
CORE_SCHEMA_SQL = Path(__file__).resolve().parents[1] / "intership_management.sql"
REQUIRED_CORE_TABLES = {
    "PHONG_BAN",
    "TRUONG_DAI_HOC",
    "NGUOI_DUNG",
    "HO_SO_THUC_TAP",
    "TAI_LIEU_HO_SO",
    "CHUONG_TRINH_THUC_TAP",
    "UNG_TUYEN_CHUONG_TRINH",
}


def require_uat_target() -> None:
    host = os.getenv("MYSQL_HOST", "").strip().lower()
    if (
        database.DATABASE_BACKEND != "mysql"
        or EXPECTED_SCHEMA not in ALLOWED_SCHEMAS
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


def core_schema_statements() -> list[tuple[str, str]]:
    """Extract only CREATE TABLE DDL; the legacy file also contains unsafe USE and demo INSERTs."""
    if not CORE_SCHEMA_SQL.is_file():
        raise RuntimeError("The MySQL core schema source file is missing.")
    source = CORE_SCHEMA_SQL.read_text(encoding="utf-8")
    source = re.sub(r"(?m)^\s*--[^\r\n]*(?:\r?\n|$)", "", source)
    statements = []
    for item in source.split(";"):
        statement = item.strip()
        match = re.match(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?",
            statement,
            flags=re.IGNORECASE,
        )
        if match:
            statements.append((match.group(1).upper(), statement + ";"))
    if not statements:
        raise RuntimeError("No safe CREATE TABLE statements were found in the MySQL core schema source.")
    return statements


def ensure_core_schema() -> None:
    declared = core_schema_statements()
    declared_names = {name for name, _ in declared}
    connection = database.get_db_connection()
    try:
        rows = connection.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
        ).fetchall()
        existing = {str(row["TABLE_NAME"]).upper() for row in rows}
        if REQUIRED_CORE_TABLES.issubset(existing):
            return
        if existing and not existing.issubset(declared_names):
            raise RuntimeError(
                "The clean UAT schema contains tables but lacks required core tables; refusing to modify a partial or unrelated schema."
            )
        if existing:
            for table_name in existing:
                count = connection.execute(f"SELECT COUNT(*) AS total FROM `{table_name}`").fetchone()["total"]
                if int(count) != 0:
                    raise RuntimeError(
                        "The clean UAT schema contains data in a partial core schema; refusing to continue."
                    )
        for _, statement in declared:
            connection.execute(statement)
        connection.commit()
        created = connection.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
        ).fetchall()
        created_names = {str(row["TABLE_NAME"]).upper() for row in created}
        if not REQUIRED_CORE_TABLES.issubset(created_names):
            raise RuntimeError("The MySQL core schema bootstrap did not create all required IMS tables.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    require_uat_target()
    ensure_core_schema()
    database.init_db()
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
