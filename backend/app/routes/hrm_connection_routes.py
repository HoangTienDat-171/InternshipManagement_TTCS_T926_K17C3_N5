"""Admin controls for isolated, loopback-only HRM Sandbox sources."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_db
from .. import hrm_connection_service as connections
from ..security import require_role

router = APIRouter(prefix="/api/integrations/hrm/connections", tags=["HRM Connections"])


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    connection_name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=32, max_length=256)


class ConnectionRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    connection_name: str = Field(min_length=1, max_length=100)


class ActivateConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_active_id: str | None = Field(default=None, max_length=32)
    confirm: bool


class ReconnectConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=32, max_length=256)


def _admin(request: Request):
    return require_role(request, "Admin")


@router.get("")
def get_connections(request: Request, db=Depends(get_db)):
    _admin(request)
    return connections.list_connections(db)


@router.post("/test")
async def test_configuration(payload: ConnectionInput, request: Request):
    _admin(request)
    return await connections.test_configuration(payload.connection_name, payload.endpoint, payload.api_key)


@router.post("")
async def add_connection(payload: ConnectionInput, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    await connections.test_configuration(payload.connection_name, payload.endpoint, payload.api_key)
    return connections.add_connection(
        db, payload.connection_name, payload.endpoint, payload.api_key,
        int(actor["ma_nguoi_dung"]),
    )


@router.patch("/{connection_id}")
def rename_connection(connection_id: str, payload: ConnectionRename, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return connections.update_connection_name(db, connection_id, payload.connection_name, int(actor["ma_nguoi_dung"]))


@router.post("/{connection_id}/test")
async def test_saved_connection(connection_id: str, request: Request, db=Depends(get_db)):
    _admin(request)
    _, row = await connections.test_connection_id(db, connection_id)
    return {"connection_id": connection_id, "state": row["state"], "endpoint": row["endpoint"], "message": row["last_check_message"]}


@router.post("/{connection_id}/pause")
def pause_connection(connection_id: str, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return connections.pause_connection(db, connection_id, int(actor["ma_nguoi_dung"]))


@router.post("/{connection_id}/resume")
async def resume_connection(connection_id: str, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return await connections.resume_connection(db, connection_id, int(actor["ma_nguoi_dung"]))


@router.post("/{connection_id}/reconnect")
async def reconnect_connection(connection_id: str, payload: ReconnectConnection, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return await connections.reconnect_connection(db, connection_id, payload.api_key, int(actor["ma_nguoi_dung"]))


@router.post("/{connection_id}/disconnect")
def disconnect_connection(connection_id: str, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return connections.disconnect_connection(db, connection_id, int(actor["ma_nguoi_dung"]))


@router.post("/{connection_id}/activate")
async def activate_connection(connection_id: str, payload: ActivateConnection, request: Request, db=Depends(get_db)):
    actor = _admin(request)
    return await connections.activate_connection(
        db, connection_id, payload.expected_active_id, payload.confirm,
        int(actor["ma_nguoi_dung"]),
    )


@router.get("/{connection_id}/history")
def get_connection_history(
    connection_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    _admin(request)
    return connections.connection_history(db, connection_id, page, page_size)
