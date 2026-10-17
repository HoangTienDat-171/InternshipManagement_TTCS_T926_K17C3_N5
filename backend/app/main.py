import asyncio
import logging
import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .database import DATABASE_BACKEND, get_db_connection, init_db
from . import audit_service, backup_service
from .email_outbox import start_email_worker, stop_email_worker
from .hrm_storage import ensure_hrm_sqlite_schema
from .hrm_connection_service import bootstrap_legacy_connection, ensure_sqlite_schema
from .security import get_session_user, session_connections
from .routes import allowance_routes, attendance_routes, audit_routes, auth_routes, backup_routes, contract_routes, document_routes, evaluation_routes, final_report_routes, hrm_connection_routes, hrm_routes, intern_routes, leave_routes, master_routes, meeting_routes, mentor_routes, metrics_routes, notification_routes, program_routes, reporting_routes, support_request_routes, task_routes, weekly_report_routes, work_shift_routes

app = FastAPI(
    title="Hệ thống Quản lý Thực tập sinh (Internship Management System)",
    description="Backend API phục vụ Quản lý Thực tập sinh với Kiến trúc Bảo mật 3 Giai đoạn",
    version="1.1.0"
)

app.add_middleware(support_request_routes.SupportRequestBodyLimitMiddleware)

# Giai đoạn 1: Bảo mật khi truyền tải (In Transit Security Middleware)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Ép buộc HTTPS HSTS
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        # Chống sniffing MIME type
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Chống Clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Bảo vệ Cross-Site Scripting
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Giới hạn nguồn Referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Chống cache dữ liệu nhạy cảm nếu là auth/intern
        if request.url.path.startswith("/api/auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(SecurityHeadersMiddleware)

SESSION_REVALIDATION_INTERVAL_SECONDS = 5
logger = logging.getLogger(__name__)
_backup_scheduler_stop: asyncio.Event | None = None
_backup_scheduler_task: asyncio.Task | None = None


@app.middleware("http")
async def audit_business_mutations(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        path = request.url.path.rstrip("/")
        if not path.startswith(("/api/attendance", "/api/interns/me/attendance", "/api/admin/backups", "/api/notifications")) and path != "/api/auth/login":
            route = request.scope.get("route")
            route_path = getattr(route, "path", path)
            parts = [part for part in route_path.split("/") if part]
            resource = (parts[1] if len(parts) > 1 and parts[0] == "api" else "api").upper()
            action = f"API_{request.method}_{resource}"[:120]
            path_ids = [value for value in request.path_params.values() if isinstance(value, (int, str))]
            resource_id = next((str(value) for value in path_ids if str(value).isdigit()), None)
            audit_service.record_request_event(
                request,
                action=action,
                resource=resource,
                resource_id=resource_id,
                outcome="SUCCESS" if response.status_code < 400 else "FAILURE",
                metadata={"http_status": response.status_code},
            )
    return response


@app.middleware("http")
async def validate_api_session(request: Request, call_next):
    path = request.url.path
    public_paths = {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/register-with-cv",
        "/api/auth/forgot-password",
    }
    normalized_path = path.rstrip("/")
    if (
        path.startswith("/api/")
        and request.method != "OPTIONS"
        and normalized_path not in public_paths
    ):
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        user = get_session_user(token) if scheme.lower() == "bearer" and token else None
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác."})
        request.state.current_user = user
        password_change_path = (
            (request.method == "GET" and path == "/api/auth/me")
            or (request.method == "POST" and path == "/api/auth/logout")
            or (
                request.method == "PUT"
                and path == f"/api/auth/users/{user['ma_nguoi_dung']}/password"
            )
        )
        if user.get("must_change_password") and not password_change_path:
            return JSONResponse(status_code=403, content={
                "detail": "Bạn cần đổi mật khẩu tạm thời trước khi tiếp tục.",
                "code": "PASSWORD_CHANGE_REQUIRED",
            })
    return await call_next(request)

# CORS Middleware kết nối React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    global _backup_scheduler_stop, _backup_scheduler_task
    init_db()
    if DATABASE_BACKEND == "sqlite":
        db = get_db_connection()
        try:
            ensure_hrm_sqlite_schema(db)
            ensure_sqlite_schema(db)
            bootstrap_legacy_connection(db)
        finally:
            db.close()
    if os.getenv("IMS_DISABLE_EMAIL_WORKER") != "1":
        start_email_worker()
    conn = get_db_connection()
    try:
        if backup_service.backup_schema_ready(conn):
            _backup_scheduler_stop = asyncio.Event()
            _backup_scheduler_task = asyncio.create_task(backup_service.backup_scheduler_loop(_backup_scheduler_stop))
        else:
            logger.info("US41 backup scheduler is inactive until migration 20261017_us38_us41_us42.sql is applied.")
    finally:
        conn.close()


@app.on_event("shutdown")
async def on_shutdown():
    global _backup_scheduler_stop, _backup_scheduler_task
    await stop_email_worker()
    if _backup_scheduler_stop is not None:
        _backup_scheduler_stop.set()
    if _backup_scheduler_task is not None:
        await _backup_scheduler_task
    _backup_scheduler_stop = None
    _backup_scheduler_task = None

@app.get("/")
def root():
    return {
        "system": "Hệ thống Quản lý Thực tập sinh",
        "security_profile": "3-Stage Defense (In-Transit, At-Rest Bcrypt, App-Layer Protection)",
        "status": "Online",
        "docs_url": "/docs"
    }

app.include_router(auth_routes.router)
app.include_router(intern_routes.router)
app.include_router(master_routes.router)
app.include_router(document_routes.router)
app.include_router(contract_routes.router)
app.include_router(mentor_routes.router)
app.include_router(program_routes.router)
app.include_router(notification_routes.router)
app.include_router(meeting_routes.router)
app.include_router(metrics_routes.router)
app.include_router(task_routes.router)
app.include_router(weekly_report_routes.router)
app.include_router(evaluation_routes.router)
app.include_router(work_shift_routes.router)
app.include_router(attendance_routes.router)
app.include_router(audit_routes.router)
app.include_router(backup_routes.router)
app.include_router(leave_routes.router)
app.include_router(allowance_routes.router)
app.include_router(support_request_routes.router)
app.include_router(final_report_routes.router)
app.include_router(reporting_routes.router)
app.include_router(hrm_routes.router)
app.include_router(hrm_connection_routes.router)


@app.websocket("/api/auth/events")
async def session_events(websocket: WebSocket, token: str = ""):
    user = get_session_user(token) if token else None
    if not user:
        await websocket.close(code=4401)
        return
    user_id = user["ma_nguoi_dung"]
    await session_connections.connect(user_id, user["session_id"], websocket)
    try:
        while True:
            # Revalidate after network interruptions and periodically while connected.
            try:
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=SESSION_REVALIDATION_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass
            if not get_session_user(token):
                await websocket.send_json({
                    "type": "FORCE_LOGOUT",
                    "message": "Phiên đăng nhập đã hết hạn hoặc được thay thế trên thiết bị khác.",
                })
                await websocket.close(code=4401)
                break
    except WebSocketDisconnect:
        pass
    finally:
        session_connections.disconnect(user_id, websocket)
