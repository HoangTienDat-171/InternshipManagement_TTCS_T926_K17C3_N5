"""Local, authenticated database + uploads backup service for US41."""
import asyncio
import errno
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import database
from .audit_service import write_audit_event


logger = logging.getLogger(__name__)
_SQLITE_BACKUP_LOCK = threading.Lock()
_BACKUP_NAME = re.compile(r"^ims_backup_[A-Za-z0-9_.-]+\.zip$")
_MYSQL_DATABASE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_RESERVED_PUBLIC_SEGMENTS = {"public", "static", "dist", "build"}


class BackupError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def backup_schema_ready(db) -> bool:
    required = {"IMS_BACKUP_SETTINGS", "IMS_BACKUP_JOBS", "IMS_AUDIT_LOG"}
    if database.DATABASE_BACKEND == "mysql":
        rows = db.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN (?, ?, ?)",
            tuple(required),
        ).fetchall()
        # Windows MySQL commonly reports table names in lowercase when
        # lower_case_table_names is enabled. Compare normalized names so the
        # feature remains available regardless of the server's identifier case.
        return required.issubset({str(row["TABLE_NAME"]).upper() for row in rows})
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?)",
        tuple(required),
    ).fetchall()
    return required.issubset({row["name"] for row in rows})


def backup_directory() -> Path:
    configured = os.getenv("IMS_BACKUP_DIRECTORY", "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        local_app_data = os.getenv("LOCALAPPDATA")
        base = Path(local_app_data).expanduser() if local_app_data else Path.home() / ".local" / "share"
        root = (base / "IMS-Backups").resolve()
    if any(part.casefold() in _RESERVED_PUBLIC_SEGMENTS for part in root.parts):
        raise BackupError("UNSAFE_BACKUP_DIRECTORY")
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            root.chmod(0o700)
        except OSError as exc:
            raise BackupError("BACKUP_DIRECTORY_PERMISSIONS_FAILED") from exc
    return root


def _upload_root() -> Path:
    return (Path(database.DB_FILE).resolve().parent / "uploads").resolve()


def _find_mysql_tool(name: str) -> str:
    configured = os.getenv(f"IMS_{name.upper()}_BIN", "").strip()
    candidates = [configured, shutil.which(name)]
    program_files = [os.getenv("ProgramFiles"), os.getenv("ProgramW6432")]
    for base in filter(None, program_files):
        candidates.extend(str(path) for path in Path(base).glob("MySQL/*/bin/" + name + ".exe"))
        candidates.extend(str(path) for path in Path(base).glob("MySQL/MySQL Server */bin/" + name + ".exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise BackupError(f"{name.upper()}_NOT_FOUND")


def _mysql_client_file(directory: Path) -> Path:
    values = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": os.getenv("MYSQL_PORT", "3306"),
        "user": os.getenv("MYSQL_USER", ""),
        "password": os.getenv("MYSQL_PASSWORD", ""),
    }
    if not values["user"] or not values["password"]:
        raise BackupError("MYSQL_CREDENTIALS_MISSING")
    if any("\n" in value or "\r" in value for value in values.values()):
        raise BackupError("MYSQL_CREDENTIALS_INVALID")

    def quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    path = directory / f".mysql-client-{uuid.uuid4().hex}.cnf"
    payload = "[client]\n" + "".join(f"{key}={quote(value)}\n" for key, value in values.items())
    path.write_text(payload, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # The file inherits the current user's private temp-directory ACL on Windows.
    return path


def _dump_mysql(destination: Path, temporary_directory: Path) -> tuple[str, list[str], dict[str, int]]:
    database_name = os.getenv("MYSQL_DATABASE", "").strip()
    if not _MYSQL_DATABASE.fullmatch(database_name):
        raise BackupError("MYSQL_DATABASE_INVALID")
    dump_tool = _find_mysql_tool("mysqldump")
    options_file = _mysql_client_file(temporary_directory)
    args = [
        dump_tool,
        f"--defaults-extra-file={options_file}",
        "--single-transaction", "--quick", "--routines", "--triggers", "--events", "--no-tablespaces",
        "--hex-blob", "--set-gtid-purged=OFF", "--column-statistics=0", database_name,
    ]
    try:
        with destination.open("wb") as output:
            result = subprocess.run(args, stdout=output, stderr=subprocess.PIPE, timeout=3600, check=False)
    except subprocess.TimeoutExpired as exc:
        logger.warning("MySQL dump timed out after the configured limit.")
        raise BackupError("MYSQLDUMP_TIMEOUT") from exc
    except OSError as exc:
        logger.warning("MySQL dump executable could not be started (OS error %s).", exc.errno)
        raise BackupError("MYSQLDUMP_EXECUTION_FAILED") from exc
    finally:
        options_file.unlink(missing_ok=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        if re.search(r"show events[\s\S]*access denied|access denied[\s\S]*show events", stderr, re.IGNORECASE):
            code = "MYSQLDUMP_EVENT_PRIVILEGE_MISSING"
        elif re.search(r"access denied|need .* privilege|permission denied", stderr, re.IGNORECASE):
            code = "MYSQLDUMP_PRIVILEGE_MISSING"
        elif re.search(r"unknown (?:variable|option)|unknown option", stderr, re.IGNORECASE):
            code = "MYSQLDUMP_UNSUPPORTED_OPTION"
        elif re.search(r"can't connect|connection refused|unable to connect", stderr, re.IGNORECASE):
            code = "MYSQLDUMP_CONNECTION_FAILED"
        else:
            code = "MYSQLDUMP_FAILED"
        # Keep stderr out of logs and the database: client diagnostics can contain
        # account, host, and schema identifiers. The stable category is sufficient.
        logger.warning("MySQL dump exited with code %s; classified as %s.", result.returncode, code)
        raise BackupError(code)
    tables = _list_mysql_tables()
    return database_name, tables, _count_mysql_rows(tables)


def _list_mysql_tables() -> list[str]:
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
        ).fetchall()
        return [str(row["TABLE_NAME"]) for row in rows]
    finally:
        conn.close()


def _count_mysql_rows(tables: list[str]) -> dict[str, int]:
    conn = database.get_db_connection()
    try:
        counts = {}
        for table in tables:
            if not re.fullmatch(r"[A-Za-z0-9_$]{1,64}", table):
                raise BackupError("DATABASE_SCHEMA_INVALID")
            counts[table] = int(conn.execute(f"SELECT COUNT(*) AS total FROM `{table}`").fetchone()["total"])
        return counts
    finally:
        conn.close()


def _count_mysql_foreign_keys() -> int:
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS total FROM (
                   SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
                   WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL
                   GROUP BY TABLE_NAME, CONSTRAINT_NAME
               ) AS foreign_key_constraints"""
        ).fetchone()
        return int(row["total"])
    finally:
        conn.close()


def _dump_sqlite(destination: Path) -> tuple[str, list[str], dict[str, int]]:
    source = sqlite3.connect(database.DB_FILE)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        tables = [row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        row_counts = {}
        for table in tables:
            quoted = table.replace('"', '""')
            row_counts[table] = int(source.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
    finally:
        target.close()
        source.close()
    return Path(database.DB_FILE).stem, tables, row_counts


def _upload_paths() -> list[Path]:
    root = _upload_root()
    if not root.is_dir():
        return []
    paths = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        resolved = path.resolve()
        if root not in resolved.parents:
            continue
        paths.append(resolved)
    return sorted(paths)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_uploads(archive: zipfile.ZipFile, upload_manifest: list[dict]) -> None:
    root = _upload_root()
    for item in upload_manifest:
        relative = Path(str(item["path"]))
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or path.is_symlink():
            raise BackupError("BACKUP_UPLOAD_CHANGED")
        expected_size = int(item["size_bytes"])
        expected_digest = str(item["sha256"])
        if path.stat().st_size != expected_size or _file_sha256(path) != expected_digest:
            raise BackupError("BACKUP_UPLOAD_CHANGED")
        archive_name = f"uploads/{relative.as_posix()}"
        try:
            info = zipfile.ZipInfo(archive_name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.file_size = expected_size
            with path.open("rb") as source, archive.open(info, "w") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            info = archive.getinfo(archive_name)
            digest = hashlib.sha256()
            size = 0
            with archive.open(info, "r") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            if size != expected_size or digest.hexdigest() != expected_digest:
                raise BackupError("BACKUP_UPLOAD_CHANGED")
        except FileNotFoundError as exc:
            raise BackupError("BACKUP_UPLOAD_CHANGED") from exc


def _job_row(db, job_id: int) -> dict:
    row = db.execute(
        """SELECT id, backup_type, status, started_by, started_at, finished_at,
                  file_name, file_size_bytes, checksum_sha256, checksum_status,
                  checksum_checked_at, manifest, error_code
           FROM IMS_BACKUP_JOBS WHERE id = ?""", (job_id,)
    ).fetchone()
    return dict(row) if row else {}


def _public_job(row: dict) -> dict:
    result = dict(row)
    if result.get("manifest"):
        try:
            manifest = json.loads(result["manifest"]) if isinstance(result["manifest"], str) else result["manifest"]
            if manifest.get("result") == "PASS" and manifest.get("restore_database"):
                result["manifest"] = {
                    "restore_database": manifest.get("restore_database"),
                    "source_backup_id": manifest.get("source_backup_id"),
                    "table_count": len(manifest.get("tables", [])),
                    "foreign_key_constraints": int(manifest.get("foreign_key_constraints", 0)),
                    "upload_file_count": int(manifest.get("upload_files", 0)),
                }
            else:
                result["manifest"] = {
                    "database_backend": manifest.get("database_backend"),
                    "database_name": manifest.get("database_name"),
                    "schema_version": manifest.get("schema_version"),
                    "table_count": len(manifest.get("tables", [])),
                    "upload_file_count": len(manifest.get("upload_files", [])),
                }
        except (TypeError, ValueError):
            result["manifest"] = None
    for name in ("started_at", "finished_at", "checksum_checked_at"):
        if result.get(name) is not None:
            result[name] = str(result[name])
    return result


def list_backups(db, *, page: int = 1, page_size: int = 20) -> dict:
    if not backup_schema_ready(db):
        raise BackupError("FEATURE_MIGRATION_REQUIRED")
    total = int(db.execute("SELECT COUNT(*) AS total FROM IMS_BACKUP_JOBS").fetchone()["total"])
    rows = db.execute(
        """SELECT id, backup_type, status, started_by, started_at, finished_at,
                  file_name, file_size_bytes, checksum_sha256, checksum_status,
                  checksum_checked_at, manifest, error_code
           FROM IMS_BACKUP_JOBS ORDER BY id DESC LIMIT ? OFFSET ?""",
        (page_size, (page - 1) * page_size),
    ).fetchall()
    return {"items": [_public_job(dict(row)) for row in rows], "total": total, "page": page, "page_size": page_size}


def get_settings(db) -> dict:
    if not backup_schema_ready(db):
        raise BackupError("FEATURE_MIGRATION_REQUIRED")
    row = db.execute(
        "SELECT schedule_enabled, interval_hours, retention_count, updated_at FROM IMS_BACKUP_SETTINGS WHERE id = 1"
    ).fetchone()
    if not row:
        raise BackupError("FEATURE_MIGRATION_REQUIRED")
    root = backup_directory()
    return {
        "schedule_enabled": bool(row["schedule_enabled"]),
        "interval_hours": int(row["interval_hours"]),
        "retention_count": int(row["retention_count"]),
        "storage_directory": str(root),
        "updated_at": str(row["updated_at"]),
    }


def update_settings(db, *, schedule_enabled: bool, interval_hours: int, retention_count: int, actor: dict) -> dict:
    if not backup_schema_ready(db):
        raise BackupError("FEATURE_MIGRATION_REQUIRED")
    db.execute(
        """UPDATE IMS_BACKUP_SETTINGS
           SET schedule_enabled = ?, interval_hours = ?, retention_count = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = 1""",
        (1 if schedule_enabled else 0, interval_hours, retention_count, actor["ma_nguoi_dung"]),
    )
    write_audit_event(
        db, actor=actor, action="BACKUP_SETTINGS_UPDATED", resource="BACKUP_SETTINGS",
        outcome="SUCCESS", resource_id="1",
        metadata={"schedule_enabled": schedule_enabled, "interval_hours": interval_hours, "retention_count": retention_count},
    )
    db.commit()
    return get_settings(db)


def _acquire_backup_lock(conn) -> bool:
    if database.DATABASE_BACKEND == "mysql":
        row = conn.execute("SELECT GET_LOCK('ims:us41:backup', 0) AS acquired").fetchone()
        return bool(row and row["acquired"] == 1)
    return _SQLITE_BACKUP_LOCK.acquire(blocking=False)


def _release_backup_lock(conn) -> None:
    if database.DATABASE_BACKEND == "mysql":
        try:
            conn.execute("SELECT RELEASE_LOCK('ims:us41:backup')")
        except Exception:
            logger.exception("Could not release backup coordination lock")
    elif _SQLITE_BACKUP_LOCK.locked():
        _SQLITE_BACKUP_LOCK.release()


def _apply_retention(conn, retention_count: int, *, actor: dict | None = None) -> int:
    if retention_count <= 0:
        return 0
    rows = conn.execute(
        """SELECT id, file_name FROM IMS_BACKUP_JOBS
           WHERE status = 'SUCCESS' AND backup_type IN ('MANUAL','SCHEDULED')
           ORDER BY id DESC"""
    ).fetchall()
    expired = rows[retention_count:]
    root = backup_directory()
    safe_expired = []
    for row in expired:
        name = str(row["file_name"] or "")
        if not _BACKUP_NAME.fullmatch(name):
            continue
        path = root / name
        if path.parent.resolve() != root.resolve():
            continue
        safe_expired.append((row["id"], path))

    # Commit logical expiry before touching files. If deletion fails or the process
    # stops, the UI never claims a removed artifact is still a successful backup.
    for job_id, _path in safe_expired:
        conn.execute(
            "UPDATE IMS_BACKUP_JOBS SET status='EXPIRED' WHERE id=? AND status='SUCCESS'",
            (job_id,),
        )
    if safe_expired:
        write_audit_event(
            conn,
            actor=actor,
            action="BACKUP_RETENTION_APPLIED",
            resource="BACKUP_SETTINGS",
            outcome="SUCCESS",
            metadata={"retention_count": retention_count, "files_expired": len(safe_expired)},
        )
        conn.commit()

    removed = 0
    for _job_id, path in safe_expired:
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError:
            # Keep the extra file for manual cleanup; its database row is already
            # EXPIRED and cannot be mistaken for the retained recovery set.
            logger.exception("Expired backup artifact could not be removed")
    return removed


def create_backup(*, actor: dict | None = None, backup_type: str = "MANUAL") -> dict:
    if backup_type not in {"MANUAL", "SCHEDULED"}:
        raise BackupError("BACKUP_TYPE_INVALID")
    conn = database.get_db_connection()
    acquired = False
    job_id = None
    archive_path = None
    try:
        if not backup_schema_ready(conn):
            raise BackupError("FEATURE_MIGRATION_REQUIRED")
        acquired = _acquire_backup_lock(conn)
        if not acquired:
            raise BackupError("BACKUP_ALREADY_RUNNING")
        # A prior process can leave a stale RUNNING marker after a crash; the DB lock
        # proves no active writer holds it before marking entries older than 24h failed.
        conn.execute(
            "UPDATE IMS_BACKUP_JOBS SET status='FAILED', finished_at=CURRENT_TIMESTAMP, error_code='PROCESS_INTERRUPTED' "
            "WHERE status='RUNNING' AND started_at < CURRENT_TIMESTAMP - INTERVAL 24 HOUR"
            if database.DATABASE_BACKEND == "mysql" else
            "UPDATE IMS_BACKUP_JOBS SET status='FAILED', finished_at=CURRENT_TIMESTAMP, error_code='PROCESS_INTERRUPTED' "
            "WHERE status='RUNNING' AND started_at < datetime('now','-24 hours')"
        )
        cursor = conn.execute(
            """INSERT INTO IMS_BACKUP_JOBS (backup_type, status, started_by, started_at)
               VALUES (?, 'RUNNING', ?, CURRENT_TIMESTAMP)""",
            (backup_type, actor.get("ma_nguoi_dung") if actor else None),
        )
        job_id = int(cursor.lastrowid)
        conn.commit()
        root = backup_directory()
        disk = shutil.disk_usage(root)
        if disk.free < 50 * 1024 * 1024:
            raise BackupError("INSUFFICIENT_DISK_SPACE")
        file_name = f"ims_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.zip"
        archive_path = root / file_name
        upload_root = _upload_root()
        with tempfile.TemporaryDirectory(prefix="ims-us41-", dir=root) as temp:
            temp_dir = Path(temp)
            if database.DATABASE_BACKEND == "mysql":
                database_name, tables, row_counts = _dump_mysql(temp_dir / "database.sql", temp_dir)
                foreign_key_constraints = _count_mysql_foreign_keys()
            elif database.DATABASE_BACKEND == "sqlite":
                database_name, tables, row_counts = _dump_sqlite(temp_dir / "database.sqlite3")
                foreign_key_constraints = None
            else:
                raise BackupError("DATABASE_BACKEND_UNSUPPORTED")
            upload_paths = _upload_paths()
            upload_manifest = [
                {
                    "path": path.relative_to(upload_root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
                for path in upload_paths
            ]
            manifest = {
                "manifest_version": 1,
                "created_at": datetime.now().astimezone().isoformat(),
                "backup_type": backup_type,
                "database_backend": database.DATABASE_BACKEND,
                "database_name": database_name,
                "schema_version": os.getenv("IMS_SCHEMA_VERSION", "unversioned"),
                "tables": tables,
                "table_row_counts": row_counts,
                "foreign_key_constraints": foreign_key_constraints,
                "upload_files": upload_manifest,
                "uploads_present": upload_root.is_dir(),
            }
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                database_file = temp_dir / ("database.sql" if database.DATABASE_BACKEND == "mysql" else "database.sqlite3")
                archive.write(database_file, database_file.name)
                _archive_uploads(archive, upload_manifest)
                archive.write(manifest_path, "manifest.json")
        if os.name != "nt":
            archive_path.chmod(0o600)
        digest = hashlib.sha256()
        with archive_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        checksum = digest.hexdigest()
        size = archive_path.stat().st_size
        settings = conn.execute("SELECT retention_count FROM IMS_BACKUP_SETTINGS WHERE id=1").fetchone()
        retention_count = int(settings["retention_count"]) if settings else 0
        conn.execute(
            """UPDATE IMS_BACKUP_JOBS SET status='SUCCESS', finished_at=CURRENT_TIMESTAMP,
                 file_name=?, file_size_bytes=?, checksum_sha256=?, checksum_status='PENDING', manifest=?, error_code=NULL
               WHERE id=?""",
            (file_name, size, checksum, json.dumps(manifest, ensure_ascii=False), job_id),
        )
        write_audit_event(
            conn, actor=actor, action="BACKUP_CREATED", resource="BACKUP", resource_id=job_id,
            outcome="SUCCESS", metadata={"backup_type": backup_type, "file_name": file_name, "file_size_bytes": size, "checksum_sha256": checksum},
        )
        conn.commit()
        if retention_count > 0:
            try:
                _apply_retention(conn, retention_count, actor=actor)
            except Exception:
                conn.rollback()
                logger.exception("Configured backup retention could not be applied")
        return _public_job(_job_row(conn, job_id))
    except Exception as exc:
        conn.rollback()
        if archive_path is not None:
            try:
                archive_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Partial backup archive cleanup failed")
        if job_id is not None:
            disk_full = isinstance(exc, OSError) and (
                exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == 112
            )
            code = exc.code if isinstance(exc, BackupError) else "INSUFFICIENT_DISK_SPACE" if disk_full else "BACKUP_FAILED"
            try:
                conn.execute(
                    "UPDATE IMS_BACKUP_JOBS SET status='FAILED', finished_at=CURRENT_TIMESTAMP, error_code=? WHERE id=?",
                    (code, job_id),
                )
                write_audit_event(
                    conn, actor=actor, action="BACKUP_FAILED", resource="BACKUP", resource_id=job_id,
                    outcome="FAILURE", metadata={"error_code": code, "backup_type": backup_type},
                )
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Backup job failure could not be persisted")
        if isinstance(exc, BackupError):
            raise
        logger.exception("Backup job failed")
        raise BackupError("BACKUP_FAILED") from exc
    finally:
        if acquired:
            _release_backup_lock(conn)
        conn.close()


def verify_backup(job_id: int, *, actor: dict) -> dict:
    conn = database.get_db_connection()
    try:
        if not backup_schema_ready(conn):
            raise BackupError("FEATURE_MIGRATION_REQUIRED")
        row = conn.execute("SELECT file_name, checksum_sha256, status, backup_type FROM IMS_BACKUP_JOBS WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise BackupError("BACKUP_NOT_FOUND")
        if row["backup_type"] == "RESTORE_VERIFICATION":
            raise BackupError("BACKUP_ARTIFACT_NOT_FOUND")
        file_name = str(row["file_name"] or "")
        valid_name = bool(_BACKUP_NAME.fullmatch(file_name))
        path = backup_directory() / file_name if valid_name else None
        digest = hashlib.sha256()
        if path and path.is_file() and path.parent.resolve() == backup_directory().resolve():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            status = "VALID" if digest.hexdigest() == str(row["checksum_sha256"] or "") else "INVALID"
        else:
            status = "INVALID"
        conn.execute(
            "UPDATE IMS_BACKUP_JOBS SET checksum_status=?, checksum_checked_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, job_id),
        )
        write_audit_event(
            conn, actor=actor, action="BACKUP_CHECKSUM_VERIFIED", resource="BACKUP", resource_id=job_id,
            outcome="SUCCESS" if status == "VALID" else "FAILURE", metadata={"checksum_status": status},
        )
        conn.commit()
        return {"id": job_id, "checksum_status": status}
    finally:
        conn.close()


async def backup_scheduler_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            conn = database.get_db_connection()
            try:
                if backup_schema_ready(conn):
                    settings = conn.execute(
                        "SELECT schedule_enabled, interval_hours FROM IMS_BACKUP_SETTINGS WHERE id=1"
                    ).fetchone()
                    latest = conn.execute(
                        "SELECT started_at FROM IMS_BACKUP_JOBS WHERE status IN ('SUCCESS','RUNNING') ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    now_row = conn.execute("SELECT CURRENT_TIMESTAMP AS server_now").fetchone()
                    if settings and settings["schedule_enabled"]:
                        now = datetime.fromisoformat(str(now_row["server_now"]))
                        last = datetime.fromisoformat(str(latest["started_at"])) if latest else None
                        if last is None or now - last >= timedelta(hours=int(settings["interval_hours"])):
                            await asyncio.to_thread(create_backup, actor=None, backup_type="SCHEDULED")
            finally:
                conn.close()
        except Exception:
            logger.exception("Scheduled backup check failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
