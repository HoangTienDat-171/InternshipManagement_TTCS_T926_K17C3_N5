"""Opaque, server-validated sessions and realtime session notifications."""
import hashlib
import secrets
from typing import Any

from fastapi import HTTPException, Request, status, WebSocket

from .database import get_db_connection, has_password_change_column


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_session_user(token: str) -> dict[str, Any] | None:
    conn = get_db_connection()
    try:
        password_flag = "u.must_change_password" if has_password_change_column(conn) else "0 AS must_change_password"
        row = conn.execute("""
            SELECT u.ma_nguoi_dung, u.ho_ten, u.email, u.so_dien_thoai,
                   u.vai_tro, u.trang_thai, u.ma_phong_ban, p.ten_phong_ban,
                   s.session_id, {password_flag}
            FROM ACTIVE_SESSIONS s
            JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = s.ma_nguoi_dung
            LEFT JOIN PHONG_BAN p ON p.ma_phong_ban = u.ma_phong_ban
            WHERE s.token_hash = ?
        """.format(password_flag=password_flag), (token_digest(token),)).fetchone()
        if not row or row["trang_thai"] != "HoatDong":
            return None
        return dict(row)
    finally:
        conn.close()


def require_role(request: Request, *roles: str) -> dict[str, Any]:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ.")
    if roles and user["vai_tro"] not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền thực hiện thao tác này.")
    return user


class SessionConnections:
    def __init__(self):
        self.connections: dict[int, dict[WebSocket, str]] = {}

    async def connect(self, user_id: int, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(user_id, {})[websocket] = session_id

    def disconnect(self, user_id: int, websocket: WebSocket):
        sockets = self.connections.get(user_id)
        if sockets:
            sockets.pop(websocket, None)
            if not sockets:
                self.connections.pop(user_id, None)

    async def publish(self, user_id: int, event: dict[str, Any], session_id: str | None = None):
        for socket, connected_session_id in tuple(self.connections.get(user_id, {}).items()):
            if session_id and connected_session_id != session_id:
                continue
            try:
                await socket.send_json(event)
            except Exception:
                self.disconnect(user_id, socket)


session_connections = SessionConnections()


async def publish_force_logout(user_id: int, session_id: str | None = None):
    await session_connections.publish(user_id, {
        "type": "FORCE_LOGOUT",
        "message": "Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.",
    }, session_id)


async def publish_workspace_updated(user_id: int):
    await session_connections.publish(user_id, {"type": "WORKSPACE_UPDATED"})


def new_session_token() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(18)
