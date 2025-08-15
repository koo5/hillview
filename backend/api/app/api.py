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

# Add security headers middleware
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
    allow_origins=["http://localhost:8212", "http://127.0.0.1:8212"],  # Add your frontend URLs
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
@app.on_event("startup")
async def startup():
    # Run database migrations first
    try:
        run_migrations()
        log.info("Database migrations completed successfully")
    except Exception as e:
        log.error(f"Error running migrations: {e}")
        # Fallback to create_all for backward compatibility
        log.info("Falling back to create_all")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    # Create test users if enabled
    if USER_ACCOUNTS:
        from .auth import ensure_test_users
        await ensure_test_users()

@app.get("/api/debug")
async def debug_endpoint():
    """Debug endpoint to check if the API is working properly"""
    return {"status": "ok", "message": "API is working properly"}