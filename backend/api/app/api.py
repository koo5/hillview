import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import os
import sys
# Add common module path for both local development and Docker
common_path = os.path.join(os.path.dirname(__file__), '..', '..', 'common')
sys.path.append(common_path)
from common.database import Base, engine
from common.config import is_rate_limiting_disabled, rate_limit_config

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Silence noisy HTTP libraries
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Configuration
USER_ACCOUNTS = os.getenv("USER_ACCOUNTS", "false").lower() in ("true", "1", "yes")

@asynccontextmanager
async def lifespan(app: FastAPI):
	# Startup
	log.info("Application startup initiated")

	log.info(f"DEV_MODE: {os.getenv('DEV_MODE', 'false')}")

	# Log rate limit configuration
	rate_limit_config.log_configuration()

	log.info("Application startup completed")

	yield

	# Shutdown (if needed in the future)
	log.info("Application shutdown")

app = FastAPI(title="Hillview API", description="API for Hillview application", lifespan=lifespan)

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

# Global Rate Limiting Middleware
class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
	"""Global rate limiting middleware for basic protection."""

	def __init__(self, app):
		super().__init__(app)
		from rate_limiter import general_rate_limiter
		self.rate_limiter = general_rate_limiter

		# Endpoints that bypass global rate limiting (have their own specific limits)
		self.bypass_paths = {
			"/api/auth/token",
			"/api/auth/register",
			"/api/auth/oauth-redirect",
			"/api/auth/oauth-callback",
			"/api/auth/oauth"
		}

	async def dispatch(self, request: Request, call_next):
		# Check if rate limiting is globally disabled
		if is_rate_limiting_disabled():
			#log.debug(f"Rate limiting bypassed globally (NO_LIMITS=true) for {request.url.path}")
			return await call_next(request)

		# Skip rate limiting for certain paths and methods
		if (request.url.path in self.bypass_paths or
			request.method == "OPTIONS" or
			request.url.path.startswith("/api/debug")):
			return await call_next(request)

		# Apply general API rate limiting
		try:
			await self.rate_limiter.enforce_rate_limit(request, 'general_api')
		except HTTPException as e:
			# Return rate limit response
			from fastapi.responses import JSONResponse
			return JSONResponse(
				status_code=e.status_code,
				content={"detail": e.detail},
				headers=e.headers
			)

		return await call_next(request)

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

# Reverse Proxy Middleware - Handle forwarded headers from Caddy
class ReverseProxyMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		# Trust forwarded headers from reverse proxy (Caddy)
		forwarded_proto = request.headers.get("X-Forwarded-Proto")
		forwarded_host = request.headers.get("X-Forwarded-Host")

		if forwarded_proto:
			request.scope["scheme"] = forwarded_proto
		if forwarded_host:
			request.scope["server"] = (forwarded_host, None)

		return await call_next(request)

# Add middlewares (order matters - later added = executed first)
app.add_middleware(CORSLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ReverseProxyMiddleware)

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
		"http://tauri.localhost",
		"https://hillview.cz",
		"https://api.hillview.cz",
	],
	allow_credentials=True,
	allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
	allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Include user routes if USER_ACCOUNTS is enabled
if USER_ACCOUNTS:
	import user_routes
	app.include_router(user_routes.router)

	# Include photo routes (only with user accounts)
	import photo_routes
	app.include_router(photo_routes.router)

	# Include activity routes (only with user accounts)
	import activity_routes
	app.include_router(activity_routes.router)

# Include core routes
import mapillary_routes
app.include_router(mapillary_routes.router)

import hillview_routes
app.include_router(hillview_routes.router)

import hidden_content_routes
app.include_router(hidden_content_routes.router)

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

# Database initialization moved to lifespan handler above

@app.get("/api/debug")
async def debug_endpoint():
	"""Debug endpoint to check if the API is working properly"""
	return {"status": "ok", "message": "API is working properly"}


@app.post("/api/debug/recreate-test-users")
async def recreate_test_users():
	"""Debug endpoint to delete and recreate test users (only available when DEBUG_ENDPOINTS=true)"""
	if not os.getenv("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes"):
		raise HTTPException(status_code=404, detail="Debug endpoints disabled")
	if not USER_ACCOUNTS:
		return {"error": "User accounts are not enabled"}

	import auth
	result = await auth.recreate_test_users()
	return {"status": "success", "message": "Test users re-created", "details": result}

@app.post("/api/debug/clear-database")
async def clear_database():
	"""Debug endpoint to clear all data from the database (only available when DEBUG_ENDPOINTS=true)"""
	if not os.getenv("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes"):
		raise HTTPException(status_code=404, detail="Debug endpoints disabled")
	from sqlalchemy import select, text
	import auth
	from common.database import get_db
	from common.models import User, CachedRegion, MapillaryPhotoCache

	# Get database session
	async for db in get_db():
		# Get all usernames
		usernames_query = select(User.username)
		usernames_result = await db.execute(usernames_query)
		all_usernames = [row[0] for row in usernames_result.fetchall()]

		# Use the existing safe deletion function to delete all users and their photos
		delete_summary = await auth.delete_users_by_usernames(db, all_usernames)

		# Clear Mapillary cache tables (no foreign key dependencies from other tables)
		mapillary_cache_result = await db.execute(text("DELETE FROM mapillary_photo_cache"))
		cached_regions_result = await db.execute(text("DELETE FROM cached_regions"))

		# Clear other tables that might not be covered by user deletion
		token_blacklist_result = await db.execute(text("DELETE FROM token_blacklist"))
		audit_log_result = await db.execute(text("DELETE FROM security_audit_log"))
		hidden_photos_result = await db.execute(text("DELETE FROM hidden_photos"))
		hidden_users_result = await db.execute(text("DELETE FROM hidden_users"))

		await db.commit()
		break

	log.info(f"Database cleared completely")
	return {
		"status": "success",
		"message": "Database cleared successfully",
		"details": {
			"users_deleted": delete_summary["users_deleted"],
			"photos_deleted": delete_summary["photos_deleted"],
			"mapillary_cache_deleted": mapillary_cache_result.rowcount,
			"cached_regions_deleted": cached_regions_result.rowcount,
			"token_blacklist_deleted": token_blacklist_result.rowcount,
			"audit_log_deleted": audit_log_result.rowcount,
			"hidden_photos_deleted": hidden_photos_result.rowcount,
			"hidden_users_deleted": hidden_users_result.rowcount
		}
	}

@app.post("/api/debug/mock-mapillary")
async def set_mock_mapillary_data(mock_data: Dict[str, Any]):
	"""Debug endpoint to set mock Mapillary data for testing (only available when DEBUG_ENDPOINTS=true)"""
	if not os.getenv("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes"):
		raise HTTPException(status_code=404, detail="Debug endpoints disabled")

	from mock_mapillary import mock_mapillary_service
	mock_mapillary_service.set_mock_data(mock_data)

	return {
		"status": "success",
		"message": "Mock Mapillary data set",
		"details": {
			"photos_count": len(mock_data.get('data', []))
		}
	}

@app.delete("/api/debug/mock-mapillary")
async def clear_mock_mapillary_data():
	"""Debug endpoint to clear mock Mapillary data (only available when DEBUG_ENDPOINTS=true)"""
	if not os.getenv("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes"):
		raise HTTPException(status_code=404, detail="Debug endpoints disabled")

	from mock_mapillary import mock_mapillary_service
	mock_mapillary_service.clear_mock_data()

	return {
		"status": "success",
		"message": "Mock Mapillary data cleared"
	}
