import logging
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

# Include Mapillary routes
from .mapillary_routes import router as mapillary_router
app.include_router(mapillary_router)

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