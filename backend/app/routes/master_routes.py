import hashlib
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List
from ..database import get_db
from ..schemas import Department, DepartmentCreate, University, UniversityCreate
from ..security import require_role

router = APIRouter(prefix="/api/master", tags=["Master Data"])


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _assert_name_available(db, table: str, column: str, value: str, label: str) -> None:
    rows = db.execute(f"SELECT {column} FROM {table}").fetchall()
    if any(_normalized_name(row[column]) == _normalized_name(value) for row in rows):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{label} đã tồn tại.")

@router.get("/departments", response_model=List[Department])
def get_departments(db: sqlite3.Connection = Depends(get_db)):
    """Danh mục phòng ban"""
    cursor = db.cursor()
    cursor.execute("SELECT ma_phong_ban, ten_phong_ban, mo_ta FROM PHONG_BAN ORDER BY ma_phong_ban ASC")
    return [dict(row) for row in cursor.fetchall()]


@router.post("/departments", response_model=Department, status_code=status.HTTP_201_CREATED)
def create_department(data: DepartmentCreate, request: Request, db=Depends(get_db)):
    require_role(request, "Admin", "HR")
    name = data.ten_phong_ban
    canonical_name = name.casefold()
    sqlite_database = isinstance(db, sqlite3.Connection)
    lock_name = f"ims:department:{hashlib.sha256(canonical_name.encode('utf-8')).hexdigest()[:48]}"
    lock_acquired = False

    try:
        if sqlite_database:
            db.execute("BEGIN IMMEDIATE")
        else:
            lock = db.execute("SELECT GET_LOCK(?, 10) AS acquired", (lock_name,)).fetchone()
            lock_acquired = bool(lock and lock["acquired"] == 1)
            if not lock_acquired:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Không thể khóa danh mục phòng ban để kiểm tra trùng. Vui lòng thử lại.",
                )

        rows = db.execute("SELECT ten_phong_ban FROM PHONG_BAN").fetchall()
        existing_names = {
            " ".join(str(row["ten_phong_ban"] or "").split()).casefold()
            for row in rows
        }
        if canonical_name in existing_names:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phòng ban này đã tồn tại.",
            )

        cursor = db.execute(
            "INSERT INTO PHONG_BAN (ten_phong_ban) VALUES (?)",
            (name,),
        )
        department_id = cursor.lastrowid
        db.commit()
        row = db.execute(
            "SELECT ma_phong_ban, ten_phong_ban, mo_ta FROM PHONG_BAN WHERE ma_phong_ban = ?",
            (department_id,),
        ).fetchone()
        return dict(row)
    except HTTPException:
        raise
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phòng ban này đã tồn tại hoặc không hợp lệ.",
        ) from error
    except Exception:
        db.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                db.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
            except Exception:
                # Closing the MySQL connection also releases a named lock.
                pass


@router.get("/universities", response_model=List[University])
def get_universities(db: sqlite3.Connection = Depends(get_db)):
    """Danh mục trường đại học"""
    cursor = db.cursor()
    cursor.execute("SELECT ma_truong, ten_truong, dia_chi, nguoi_lien_he, email_lien_he FROM TRUONG_DAI_HOC ORDER BY ma_truong ASC")
    return [dict(row) for row in cursor.fetchall()]


@router.post("/universities", response_model=University, status_code=status.HTTP_201_CREATED)
def create_university(data: UniversityCreate, request: Request, db=Depends(get_db)):
    require_role(request, "Admin", "HR")
    name = data.ten_truong
    canonical_name = _normalized_name(name)
    sqlite_database = isinstance(db, sqlite3.Connection)
    lock_name = f"ims:university:{hashlib.sha256(canonical_name.encode('utf-8')).hexdigest()[:48]}"
    lock_acquired = False

    try:
        if sqlite_database:
            db.execute("BEGIN IMMEDIATE")
        else:
            lock = db.execute("SELECT GET_LOCK(?, 10) AS acquired", (lock_name,)).fetchone()
            lock_acquired = bool(lock and lock["acquired"] == 1)
            if not lock_acquired:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Không thể khóa danh mục trường đại học để kiểm tra trùng. Vui lòng thử lại.",
                )

        _assert_name_available(db, "TRUONG_DAI_HOC", "ten_truong", name, "Trường đại học")
        cursor = db.execute("INSERT INTO TRUONG_DAI_HOC (ten_truong) VALUES (?)", (name,))
        row = db.execute(
            "SELECT ma_truong, ten_truong, dia_chi, nguoi_lien_he, email_lien_he "
            "FROM TRUONG_DAI_HOC WHERE ma_truong = ?",
            (cursor.lastrowid,),
        ).fetchone()
        db.commit()
        return dict(row)
    except HTTPException:
        db.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Trường đại học đã tồn tại.") from exc
    except Exception:
        db.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                db.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
            except Exception:
                # Closing the MySQL connection also releases a named lock.
                pass
