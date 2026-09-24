from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .database import init_db
from .routes import auth_routes, intern_routes, master_routes

app = FastAPI(
    title="Hệ thống Quản lý Thực tập sinh (Internship Management System)",
    description="Backend API phục vụ Quản lý Thực tập sinh với Kiến trúc Bảo mật 3 Giai đoạn",
    version="1.1.0"
)

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

# CORS Middleware kết nối React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

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
