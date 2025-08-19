import logging
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import Base, engine

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Silence noisy HTTP libraries
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Configuration
USER_ACCOUNTS = os.getenv("USER_ACCOUNTS", "false").lower() in ("true", "1", "yes")

app = FastAPI(title="Hillview API", description="API for Hillview application")

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=()"
        
        # Remove server header
        if "Server" in response.headers:
            del response.headers["Server"]
        
        # Content Security Policy (adjust based on your needs)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  # Adjust as needed
            "style-src 'self' 'unsafe-inline'; "  # Adjust as needed
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        return response

# Request logging middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        log.error(f"DEBUG: Request {request.method} {request.url}")
        response = await call_next(request)
        log.error(f"DEBUG: Response {response.status_code}")
        return response

# CORS request logging middleware
class CORSLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log CORS-related request details
        origin = request.headers.get("origin")
        access_control_request_method = request.headers.get("access-control-request-method")
        access_control_request_headers = request.headers.get("access-control-request-headers")
        
        if request.method == "OPTIONS" or origin:
            log.info(f"CORS Request: {request.method} {request.url}")
            log.info(f"  Origin: {origin}")
            if access_control_request_method:
                log.info(f"  Access-Control-Request-Method: {access_control_request_method}")
            if access_control_request_headers:
                log.info(f"  Access-Control-Request-Headers: {access_control_request_headers}")
        
        response = await call_next(request)
        
        # Log CORS-related response headers
        if request.method == "OPTIONS" or origin:
            access_control_allow_origin = response.headers.get("access-control-allow-origin")
            access_control_allow_methods = response.headers.get("access-control-allow-methods")
            access_control_allow_headers = response.headers.get("access-control-allow-headers")
            access_control_allow_credentials = response.headers.get("access-control-allow-credentials")
            
            log.info(f"CORS Response: {response.status_code}")
            log.info(f"  Access-Control-Allow-Origin: {access_control_allow_origin}")
            if access_control_allow_methods:
                log.info(f"  Access-Control-Allow-Methods: {access_control_allow_methods}")
            if access_control_allow_headers:
                log.info(f"  Access-Control-Allow-Headers: {access_control_allow_headers}")
            if access_control_allow_credentials:
                log.info(f"  Access-Control-Allow-Credentials: {access_control_allow_credentials}")
        
        return response

# Add middlewares
app.add_middleware(CORSLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Add exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    log.error(f"Unhandled exception: {exc}")
    log.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8212", 
        "http://127.0.0.1:8212",
        "http://tauri.localhost"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Include user routes if USER_ACCOUNTS is enabled
if USER_ACCOUNTS:
    from .user_routes import router as user_router
    app.include_router(user_router)
    
    # Include photo routes (only with user accounts)
    from .photo_routes import router as photo_router
    app.include_router(photo_router)

# Include Mapillary routes
from .mapillary_routes import router as mapillary_router
app.include_router(mapillary_router)

# Include Hillview routes
from .hillview_routes import router as hillview_router
app.include_router(hillview_router)

# Database migration function
def run_migrations():
    """Run Alembic migrations on startup"""
    from alembic.config import Config
    from alembic import command
    import os
    
    alembic_cfg = Config("/app/app/alembic.ini")
    # Set the database URL from environment variable
    database_url = os.getenv('DATABASE_URL', 'postgresql://hillview:hillview@postgres:5432/hillview')
    # Convert asyncpg to psycopg2 for Alembic
    if database_url.startswith('postgresql+asyncpg://'):
        database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')
    alembic_cfg.set_main_option('sqlalchemy.url', database_url)
    
    # Run migrations
    command.upgrade(alembic_cfg, "head")

# Initialize database
# @app.on_event("startup")
# async def startup():
#     log.info("Application startup completed")

@app.get("/api/debug")
async def debug_endpoint():
    """Debug endpoint to check if the API is working properly"""
    return {"status": "ok", "message": "API is working properly"}

@app.post("/api/debug/recreate-test-users")
async def recreate_test_users():
    """Debug endpoint to delete and recreate test users"""
    if not USER_ACCOUNTS:
        return {"error": "User accounts are not enabled"}
    
    try:
        from .auth import recreate_test_users
        result = await recreate_test_users()
        return {"status": "success", "message": "Test users re-created", "details": result}
    except Exception as e:
        log.error(f"Error recreating test users: {e}")
        return {"status": "error", "message": str(e)}
