import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .database import init_db
from .email_outbox import start_email_worker, stop_email_worker
from .security import get_session_user, session_connections
from .routes import allowance_routes, attendance_routes, auth_routes, contract_routes, document_routes, evaluation_routes, intern_routes, leave_routes, master_routes, mentor_routes, metrics_routes, notification_routes, program_routes, support_request_routes, task_routes, weekly_report_routes, work_shift_routes

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
        password_change_path = path == "/api/auth/me" or path == "/api/auth/logout" or (
            path.startswith("/api/auth/users/") and path.endswith("/password")
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
    init_db()
    start_email_worker()


@app.on_event("shutdown")
async def on_shutdown():
    await stop_email_worker()

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
app.include_router(metrics_routes.router)
app.include_router(task_routes.router)
app.include_router(weekly_report_routes.router)
app.include_router(evaluation_routes.router)
app.include_router(work_shift_routes.router)
app.include_router(attendance_routes.router)
app.include_router(leave_routes.router)
app.include_router(allowance_routes.router)
app.include_router(support_request_routes.router)


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
