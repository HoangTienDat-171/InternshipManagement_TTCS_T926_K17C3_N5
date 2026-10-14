import hashlib
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import List
from ..database import get_db
from ..schemas import Department, DepartmentCreate, University
from ..security import require_role

router = APIRouter(prefix="/api/master", tags=["Master Data"])

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
