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

@router.get("/universities", response_model=List[University])
def get_universities(db: sqlite3.Connection = Depends(get_db)):
    """Danh mục trường đại học"""
    cursor = db.cursor()
    cursor.execute("SELECT ma_truong, ten_truong, dia_chi, nguoi_lien_he, email_lien_he FROM TRUONG_DAI_HOC ORDER BY ma_truong ASC")
    return [dict(row) for row in cursor.fetchall()]


@router.post("/departments", response_model=Department, status_code=status.HTTP_201_CREATED)
def create_department(data: DepartmentCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    try:
        db.execute("BEGIN IMMEDIATE")
        _assert_name_available(db, "PHONG_BAN", "ten_phong_ban", data.ten_phong_ban, "Phòng ban")
        cursor = db.execute("INSERT INTO PHONG_BAN (ten_phong_ban) VALUES (?)", (data.ten_phong_ban,))
        row = db.execute(
            "SELECT ma_phong_ban, ten_phong_ban, mo_ta FROM PHONG_BAN WHERE ma_phong_ban = ?",
            (cursor.lastrowid,),
        ).fetchone()
        db.commit()
        return dict(row)
    except HTTPException:
        db.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phòng ban đã tồn tại.") from exc
    except Exception:
        db.rollback()
        raise


@router.post("/universities", response_model=University, status_code=status.HTTP_201_CREATED)
def create_university(data: UniversityCreate, request: Request, db: sqlite3.Connection = Depends(get_db)):
    require_role(request, "Admin", "HR")
    try:
        db.execute("BEGIN IMMEDIATE")
        _assert_name_available(db, "TRUONG_DAI_HOC", "ten_truong", data.ten_truong, "Trường đại học")
        cursor = db.execute("INSERT INTO TRUONG_DAI_HOC (ten_truong) VALUES (?)", (data.ten_truong,))
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
