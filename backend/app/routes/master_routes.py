from fastapi import APIRouter, Depends
import sqlite3
from typing import List
from ..database import get_db
from ..schemas import Department, University

router = APIRouter(prefix="/api/master", tags=["Master Data"])

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
