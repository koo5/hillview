import logging
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import os

from .database import Base, engine

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

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
        response.headers.pop("Server", None)
        
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
        #content={"detail": str(exc)},
    )

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5000", "http://localhost:8089", "http://localhost:8212"],  # Add your frontend URLs
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

# Initialize database
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # Create tables on startup
        await conn.run_sync(Base.metadata.create_all)

@app.get("/api/debug")
async def debug_endpoint():
    """Debug endpoint to check if the API is working properly"""
    return {"status": "ok", "message": "API is working properly"}