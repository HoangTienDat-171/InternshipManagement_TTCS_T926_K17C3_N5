"""Shared, Admin-managed department and university catalogs."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .. import database
from ..database import get_db
from ..schemas import (
    Department,
    DepartmentCreate,
    DepartmentUpdate,
    University,
    UniversityCreate,
    UniversityUpdate,
)
from ..security import require_role

router = APIRouter(prefix="/api/master", tags=["Master Data"])


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _require_admin(request: Request) -> dict[str, Any]:
    return require_role(request, "Admin")


def _require_catalog_schema(db) -> None:
    if database.DATABASE_BACKEND == "mysql":
        present = db.execute(
            "SELECT COUNT(*) AS total FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN "
            "('IMS_DEPARTMENT_CATALOG_META', 'IMS_UNIVERSITY_CATALOG_META', 'IMS_MASTER_DATA_AUDIT')"
        ).fetchone()
        if not present or int(present["total"]) != 3:
            raise HTTPException(
                status_code=503,
                detail="Thiếu schema danh mục dùng chung. Hãy áp dụng migration master-data trên database UAT trước.",
            )
    else:
        names = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if not {"IMS_DEPARTMENT_CATALOG_META", "IMS_UNIVERSITY_CATALOG_META", "IMS_MASTER_DATA_AUDIT"}.issubset(names):
            raise HTTPException(status_code=503, detail="Schema danh mục chưa được khởi tạo; hãy khởi động lại backend SQLite.")


def _assert_name_available(db, table: str, column: str, value: str, label: str, id_column: str, current_id: int | None = None) -> None:
    rows = db.execute(f"SELECT {id_column} AS item_id, {column} AS item_name FROM {table}").fetchall()
    if any(
        int(row["item_id"]) != current_id and _normalized_name(str(row["item_name"] or "")) == _normalized_name(value)
        for row in rows
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{label} đã tồn tại với cùng tên (không phân biệt hoa/thường hoặc khoảng trắng).")


def _assert_code_available(db, table: str, value: str, current_id: int | None = None) -> None:
    if not value:
        return
    rows = db.execute(f"SELECT ma_dinh_danh, {table} AS item_id FROM "
                       f"{'IMS_DEPARTMENT_CATALOG_META' if table == 'ma_phong_ban' else 'IMS_UNIVERSITY_CATALOG_META'}").fetchall()
    if any(str(row["ma_dinh_danh"] or "").casefold() == value.casefold() and int(row["item_id"]) != current_id for row in rows):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mã danh mục đã được sử dụng.")


def _audit(db, entity_type: str, entity_id: int, event_type: str, actor_id: int, before: dict | None, after: dict) -> None:
    db.execute(
        "INSERT INTO IMS_MASTER_DATA_AUDIT (entity_type, entity_id, event_type, before_json, after_json, actor_user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, event_type,
         json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
         json.dumps(after, ensure_ascii=False, default=str), actor_id, _now()),
    )


def _department(db, department_id: int) -> dict | None:
    row = db.execute(
        """SELECT p.ma_phong_ban, p.ten_phong_ban, p.mo_ta,
                  m.ma_dinh_danh, COALESCE(m.is_active, 1) AS is_active, m.updated_at,
                  SUM(CASE WHEN u.vai_tro = 'Mentor' THEN 1 ELSE 0 END) AS mentor_count,
                  SUM(CASE WHEN u.vai_tro = 'ThucTapSinh' THEN 1 ELSE 0 END) AS intern_count
           FROM PHONG_BAN p
           LEFT JOIN IMS_DEPARTMENT_CATALOG_META m ON m.ma_phong_ban = p.ma_phong_ban
           LEFT JOIN NGUOI_DUNG u ON u.ma_phong_ban = p.ma_phong_ban
           WHERE p.ma_phong_ban = ?
           GROUP BY p.ma_phong_ban, p.ten_phong_ban, p.mo_ta, m.ma_dinh_danh, m.is_active, m.updated_at""",
        (department_id,),
    ).fetchone()
    return dict(row) if row else None


def _university(db, university_id: int) -> dict | None:
    row = db.execute(
        """SELECT t.ma_truong, t.ten_truong, t.dia_chi, t.nguoi_lien_he, t.email_lien_he,
                  m.ma_dinh_danh, m.ten_viet_tat, COALESCE(m.is_active, 1) AS is_active, m.updated_at,
                  (SELECT COUNT(*) FROM HO_SO_THUC_TAP h WHERE h.ma_truong = t.ma_truong) AS intern_count
           FROM TRUONG_DAI_HOC t
           LEFT JOIN IMS_UNIVERSITY_CATALOG_META m ON m.ma_truong = t.ma_truong
           WHERE t.ma_truong = ?""",
        (university_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/departments", response_model=List[Department])
def get_departments(
    include_inactive: bool = Query(False),
    db=Depends(get_db),
):
    _require_catalog_schema(db)
    rows = db.execute(
        """SELECT p.ma_phong_ban, p.ten_phong_ban, p.mo_ta,
                  m.ma_dinh_danh,
                  COALESCE(m.is_active, 1) AS is_active, m.updated_at,
                  SUM(CASE WHEN u.vai_tro = 'Mentor' THEN 1 ELSE 0 END) AS mentor_count,
                  SUM(CASE WHEN u.vai_tro = 'ThucTapSinh' THEN 1 ELSE 0 END) AS intern_count
           FROM PHONG_BAN p
           LEFT JOIN IMS_DEPARTMENT_CATALOG_META m ON m.ma_phong_ban = p.ma_phong_ban
           LEFT JOIN NGUOI_DUNG u ON u.ma_phong_ban = p.ma_phong_ban
           GROUP BY p.ma_phong_ban, p.ten_phong_ban, p.mo_ta, m.ma_dinh_danh, m.is_active, m.updated_at
           HAVING ? = 1 OR COALESCE(m.is_active, 1) = 1
           ORDER BY p.ma_phong_ban""",
        (1 if include_inactive else 0,),
    ).fetchall()
    return [dict(row) for row in rows]


@router.post("/departments", response_model=Department, status_code=status.HTTP_201_CREATED)
def create_department(data: DepartmentCreate, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_catalog_schema(db)
    name = data.ten_phong_ban
    _assert_name_available(db, "PHONG_BAN", "ten_phong_ban", name, "Phòng ban", "ma_phong_ban")
    code = data.ma_dinh_danh
    lock_acquired = False
    lock_name = f"ims:department:{hashlib.sha256((code or name.casefold()).encode('utf-8')).hexdigest()[:48]}"
    try:
        if database.DATABASE_BACKEND == "mysql":
            lock = db.execute("SELECT GET_LOCK(?, 10) AS acquired", (lock_name,)).fetchone()
            lock_acquired = bool(lock and lock["acquired"] == 1)
            if not lock_acquired:
                raise HTTPException(status_code=503, detail="Danh mục đang được cập nhật; vui lòng thử lại.")
            db.execute("SELECT ma_phong_ban FROM PHONG_BAN FOR UPDATE").fetchall()
            _assert_name_available(db, "PHONG_BAN", "ten_phong_ban", name, "Phòng ban", "ma_phong_ban")
        else:
            db.execute("BEGIN IMMEDIATE")
            _assert_name_available(db, "PHONG_BAN", "ten_phong_ban", name, "Phòng ban", "ma_phong_ban")
        cursor = db.execute("INSERT INTO PHONG_BAN (ten_phong_ban, mo_ta) VALUES (?, ?)", (name, data.mo_ta))
        department_id = int(cursor.lastrowid)
        code = code or f"PB-{department_id:04d}"
        if not re.fullmatch(r"[A-Z0-9_-]{2,32}", code):
            raise HTTPException(status_code=422, detail="Mã phòng ban chỉ được gồm 2–32 chữ cái, chữ số, dấu gạch ngang hoặc gạch dưới.")
        _assert_code_available(db, "ma_phong_ban", code)
        db.execute(
            "INSERT INTO IMS_DEPARTMENT_CATALOG_META (ma_phong_ban, ma_dinh_danh, is_active, updated_at) VALUES (?, ?, 1, ?)",
            (department_id, code, _now()),
        )
        result = _department(db, department_id)
        _audit(db, "DEPARTMENT", department_id, "CREATED", int(actor["ma_nguoi_dung"]), None, result)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Phòng ban hoặc mã phòng ban bị trùng; hãy tải lại danh mục.") from exc
    finally:
        if lock_acquired:
            try:
                db.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
            except Exception:
                pass


@router.patch("/departments/{department_id}", response_model=Department)
def update_department(department_id: int, data: DepartmentUpdate, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_catalog_schema(db)
    before = _department(db, department_id)
    if not before:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return before
    name = changes.get("ten_phong_ban", before["ten_phong_ban"])
    if "ten_phong_ban" in changes:
        _assert_name_available(db, "PHONG_BAN", "ten_phong_ban", name, "Phòng ban", "ma_phong_ban", department_id)
    description = changes.get("mo_ta", before["mo_ta"])
    active = int(changes.get("is_active", before["is_active"]))
    try:
        db.execute("UPDATE PHONG_BAN SET ten_phong_ban = ?, mo_ta = ? WHERE ma_phong_ban = ?", (name, description, department_id))
        db.execute("UPDATE IMS_DEPARTMENT_CATALOG_META SET is_active = ?, updated_at = ? WHERE ma_phong_ban = ?", (active, _now(), department_id))
        after = _department(db, department_id)
        _audit(db, "DEPARTMENT", department_id, "UPDATED" if active == before["is_active"] else ("ACTIVATED" if active else "DEACTIVATED"), int(actor["ma_nguoi_dung"]), before, after)
        db.commit()
        return after
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Không thể cập nhật phòng ban do dữ liệu vừa thay đổi; tải lại danh mục rồi thử lại.") from exc


@router.get("/universities", response_model=List[University])
def get_universities(include_inactive: bool = Query(False), db=Depends(get_db)):
    _require_catalog_schema(db)
    rows = db.execute(
        """SELECT t.ma_truong, t.ten_truong, t.dia_chi, t.nguoi_lien_he, t.email_lien_he,
                  m.ma_dinh_danh, m.ten_viet_tat, COALESCE(m.is_active, 1) AS is_active, m.updated_at,
                  (SELECT COUNT(*) FROM HO_SO_THUC_TAP h WHERE h.ma_truong = t.ma_truong) AS intern_count
           FROM TRUONG_DAI_HOC t
           LEFT JOIN IMS_UNIVERSITY_CATALOG_META m ON m.ma_truong = t.ma_truong
           WHERE ? = 1 OR COALESCE(m.is_active, 1) = 1
           ORDER BY t.ma_truong""",
        (1 if include_inactive else 0,),
    ).fetchall()
    return [dict(row) for row in rows]


@router.post("/universities", response_model=University, status_code=status.HTTP_201_CREATED)
def create_university(data: UniversityCreate, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_catalog_schema(db)
    name = data.ten_truong
    code = (data.ma_dinh_danh or "").strip().upper() or None
    if code and not re.fullmatch(r"[A-Z0-9_-]{2,32}", code):
        raise HTTPException(status_code=422, detail="Mã trường chỉ được gồm 2–32 chữ cái, chữ số, dấu gạch ngang hoặc gạch dưới.")
    _assert_code_available(db, "ma_truong", code or "")
    lock_acquired = False
    lock_name = f"ims:university:{hashlib.sha256((code or name.casefold()).encode('utf-8')).hexdigest()[:48]}"
    try:
        if database.DATABASE_BACKEND == "mysql":
            lock = db.execute("SELECT GET_LOCK(?, 10) AS acquired", (lock_name,)).fetchone()
            lock_acquired = bool(lock and lock["acquired"] == 1)
            if not lock_acquired:
                raise HTTPException(status_code=503, detail="Danh mục đang được cập nhật; vui lòng thử lại.")
            _assert_name_available(db, "TRUONG_DAI_HOC", "ten_truong", name, "Trường đại học", "ma_truong")
        else:
            db.execute("BEGIN IMMEDIATE")
            _assert_name_available(db, "TRUONG_DAI_HOC", "ten_truong", name, "Trường đại học", "ma_truong")
        cursor = db.execute("INSERT INTO TRUONG_DAI_HOC (ten_truong) VALUES (?)", (name,))
        university_id = int(cursor.lastrowid)
        db.execute(
            "INSERT INTO IMS_UNIVERSITY_CATALOG_META (ma_truong, ma_dinh_danh, ten_viet_tat, is_active, updated_at) VALUES (?, ?, ?, 1, ?)",
            (university_id, code, (data.ten_viet_tat or "").strip() or None, _now()),
        )
        result = _university(db, university_id)
        _audit(db, "UNIVERSITY", university_id, "CREATED", int(actor["ma_nguoi_dung"]), None, result)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Trường đại học hoặc mã trường bị trùng; hãy tải lại danh mục.") from exc
    finally:
        if lock_acquired:
            try:
                db.execute("SELECT RELEASE_LOCK(?)", (lock_name,))
            except Exception:
                pass


@router.patch("/universities/{university_id}", response_model=University)
def update_university(university_id: int, data: UniversityUpdate, request: Request, db=Depends(get_db)):
    actor = _require_admin(request)
    _require_catalog_schema(db)
    before = _university(db, university_id)
    if not before:
        raise HTTPException(status_code=404, detail="Không tìm thấy trường đại học.")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return before
    name = changes.get("ten_truong", before["ten_truong"])
    if "ten_truong" in changes:
        _assert_name_available(db, "TRUONG_DAI_HOC", "ten_truong", name, "Trường đại học", "ma_truong", university_id)
    code = (changes.get("ma_dinh_danh", before["ma_dinh_danh"]) or "").strip().upper() or None
    if code and not re.fullmatch(r"[A-Z0-9_-]{2,32}", code):
        raise HTTPException(status_code=422, detail="Mã trường chỉ được gồm 2–32 chữ cái, chữ số, dấu gạch ngang hoặc gạch dưới.")
    _assert_code_available(db, "ma_truong", code or "", university_id)
    abbreviation = (changes.get("ten_viet_tat", before["ten_viet_tat"]) or "").strip() or None
    active = int(changes.get("is_active", before["is_active"]))
    try:
        db.execute("UPDATE TRUONG_DAI_HOC SET ten_truong = ? WHERE ma_truong = ?", (name, university_id))
        db.execute(
            "UPDATE IMS_UNIVERSITY_CATALOG_META SET ma_dinh_danh = ?, ten_viet_tat = ?, is_active = ?, updated_at = ? WHERE ma_truong = ?",
            (code, abbreviation, active, _now(), university_id),
        )
        after = _university(db, university_id)
        event = "UPDATED" if active == before["is_active"] else ("ACTIVATED" if active else "DEACTIVATED")
        _audit(db, "UNIVERSITY", university_id, event, int(actor["ma_nguoi_dung"]), before, after)
        db.commit()
        return after
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Không thể cập nhật trường đại học do dữ liệu vừa thay đổi; hãy tải lại danh mục.") from exc


@router.get("/audit")
def get_master_data_audit(
    request: Request,
    entity_type: str | None = Query(None, pattern="^(DEPARTMENT|UNIVERSITY)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _require_admin(request)
    _require_catalog_schema(db)
    where = "WHERE a.entity_type = ?" if entity_type else ""
    parameters = (entity_type,) if entity_type else ()
    total = int(db.execute(f"SELECT COUNT(*) AS total FROM IMS_MASTER_DATA_AUDIT a {where}", parameters).fetchone()["total"])
    items = db.execute(
        f"""SELECT a.id, a.entity_type, a.entity_id, a.event_type, a.before_json, a.after_json,
                   a.actor_user_id, u.ho_ten AS actor_name, a.created_at
            FROM IMS_MASTER_DATA_AUDIT a LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = a.actor_user_id
            {where} ORDER BY a.id DESC LIMIT ? OFFSET ?""",
        (*parameters, page_size, (page - 1) * page_size),
    ).fetchall()
    return {"items": [dict(row) for row in items], "total": total, "page": page, "page_size": page_size}
