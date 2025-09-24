import logging
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

import os
import sys
# Add common module path for both local development and Docker
common_path = os.path.join(os.path.dirname(__file__), '..', '..', 'common')
sys.path.append(common_path)
from common.database import Base, engine, get_db
from common.config import is_rate_limiting_disabled, rate_limit_config, get_cors_origins
from debug_utils import debug_only, safe_str_id, clear_system_tables, cleanup_upload_directories

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
	log.info(f"Application startup initiated, DEV_MODE: {os.getenv('DEV_MODE', 'false')}")
	rate_limit_config.log_configuration()

	# Start OAuth session cleanup task
	try:
		from user_routes import start_session_cleanup
		await start_session_cleanup()
	except Exception as e:
		log.error(f"Failed to start OAuth session cleanup: {e}")

	log.info("Application startup completed")

	yield

	# Shutdown
	log.info("Application shutdown initiated")
	try:
		from user_routes import stop_session_cleanup
		await stop_session_cleanup()
	except Exception as e:
		log.error(f"Failed to stop OAuth session cleanup: {e}")
	log.info("Application shutdown completed")




from fastapi import FastAPI
from fastapi.openapi.docs import (
	get_redoc_html,
	get_swagger_ui_html,
	get_swagger_ui_oauth2_redirect_html,
)


# class Settings(BaseSettings):
# 	openapi_url: str = "/openapi.json"
#settings = Settings()

app = FastAPI(
	#openapi_url=settings.openapi_url,
	docs_url=None, redoc_url=None,
	title="Hillview API", description="API for Hillview application", lifespan=lifespan
)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
	return get_swagger_ui_html(
		openapi_url=app.openapi_url,
		title=app.title + " - Swagger UI",
		oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
		swagger_js_url="static/swagger-ui-bundle.js",
		swagger_css_url="static/swagger-ui.css",
	)

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
	return get_swagger_ui_oauth2_redirect_html()













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
		log.debug(f"HTTP {request.method} {request.url}")
		response = await call_next(request)
		log.debug(f"HTTP {response.status_code}")
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

		# Extract and store the real client IP from proxy headers
		real_client_ip = None

		# Check for proxy headers in order of preference
		# X-Forwarded-For can contain multiple IPs, use the first (original client)
		forwarded_for = request.headers.get("X-Forwarded-For")
		if forwarded_for:
			# X-Forwarded-For format: "client_ip, proxy1_ip, proxy2_ip, ..."
			client_ip = forwarded_for.split(",")[0].strip()
			if client_ip:
				real_client_ip = client_ip

		# Check X-Real-IP (typically set by nginx)
		if not real_client_ip:
			real_ip = request.headers.get("X-Real-IP")
			if real_ip:
				real_client_ip = real_ip.strip()

		# Check CF-Connecting-IP (Cloudflare)
		if not real_client_ip:
			cf_connecting_ip = request.headers.get("CF-Connecting-IP")
			if cf_connecting_ip:
				real_client_ip = cf_connecting_ip.strip()

		# Store the real client IP in request state for get_client_ip() to use
		request.state.real_client_ip = real_client_ip

		return await call_next(request)

# Add middlewares (order matters - later added = executed first)
#app.add_middleware(CORSLoggingMiddleware)
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
	allow_origins=get_cors_origins(),
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

	# Include rating routes (only with user accounts)
	import rating_routes
	app.include_router(rating_routes.router)

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
@debug_only
async def recreate_test_users():
	if not USER_ACCOUNTS:
		return {"error": "User accounts are not enabled"}

	import auth
	result = await auth.recreate_test_users()
	return {"status": "success", "message": "Test users re-created", "details": result}

@app.post("/api/debug/clear-database")
@debug_only
async def clear_database():
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

		# Clear any remaining orphaned photos (photos without owners)
		from sqlalchemy import select
		from common.models import Photo
		from photos import delete_all_user_photo_files

		# Get any remaining photos in the database
		remaining_photos_query = select(Photo)
		remaining_photos_result = await db.execute(remaining_photos_query)
		remaining_photos = remaining_photos_result.scalars().all()

		orphaned_photos_deleted = 0
		if remaining_photos:
			# Delete the physical files for orphaned photos
			deleted_files_count = await delete_all_user_photo_files(remaining_photos)
			log.info(f"Deleted {deleted_files_count}/{len(remaining_photos)} orphaned photo files")

			# Delete orphaned photos from database
			orphaned_delete_stmt = text("DELETE FROM photos")
			orphaned_result = await db.execute(orphaned_delete_stmt)
			orphaned_photos_deleted = orphaned_result.rowcount
			log.info(f"Deleted {orphaned_photos_deleted} orphaned photos from database")

		# Clear Mapillary cache tables (no foreign key dependencies from other tables)
		from mapillary_routes import clear_mapillary_cache_tables
		mapillary_deletion_counts = await clear_mapillary_cache_tables(db)

		# Clear other tables that might not be covered by user deletion
		system_deletion_counts = await clear_system_tables(db)

		# Final cleanup: remove any remaining files in upload directories
		# This ensures we clean up files even if database records are inconsistent
		upload_dirs_cleaned = await cleanup_upload_directories()

		await db.commit()
		break

	log.info(f"Database cleared completely")
	return {
		"status": "success",
		"message": "Database cleared successfully",
		"details": {
			"users_deleted": delete_summary["users_deleted"],
			"photos_deleted": delete_summary["photos_deleted"],
			"orphaned_photos_deleted": orphaned_photos_deleted,
			"mapillary_cache_deleted": mapillary_deletion_counts["mapillary_cache_deleted"],
			"cached_regions_deleted": mapillary_deletion_counts["cached_regions_deleted"],
			**system_deletion_counts,
			**upload_dirs_cleaned
		}
	}

@app.post("/api/debug/mock-mapillary")
@debug_only
async def set_mock_mapillary_data(mock_data: Dict[str, Any], db: AsyncSession = Depends(get_db)):

	from mock_mapillary import mock_mapillary_service
	mock_mapillary_service.set_mock_data(mock_data)

	# Get cache info to warn about potential confusion
	from sqlalchemy import text
	try:
		cache_photos_result = await db.execute(text("SELECT COUNT(*) as count FROM mapillary_cache"))
		cache_photos_count = cache_photos_result.scalar()

		cache_areas_result = await db.execute(text("SELECT COUNT(*) as count FROM mapillary_cached_areas"))
		cache_areas_count = cache_areas_result.scalar()
	except Exception as e:
		# Tables might not exist yet - that's fine, means no cached data
		log.debug(f"Cache tables don't exist yet (normal for fresh database): {e}")
		cache_photos_count = 0
		cache_areas_count = 0

	return {
		"status": "success",
		"message": "Mock Mapillary data set",
		"details": {
			"photos_count": len(mock_data.get('data', [])),
			"cache_info": {
				"cached_photos": cache_photos_count,
				"cached_areas": cache_areas_count,
				"warning": "If cache_photos > 0, cached data may override mock data. Use clear-database first for pure mock testing." if cache_photos_count > 0 else None
			}
		}
	}

@app.delete("/api/debug/mock-mapillary")
@debug_only
async def clear_mock_mapillary_data():

	from mock_mapillary import mock_mapillary_service
	mock_mapillary_service.clear_mock_data()

	return {
		"status": "success",
		"message": "Mock Mapillary data cleared"
	}
