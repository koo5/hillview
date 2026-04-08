import logging
import yaml
import logging.config

from dsl_utils import y

# Load and apply logging config before uvicorn can override it
with open('logging.yaml', 'r') as f:
    config = yaml.safe_load(f)
    logging.config.dictConfig(config)

root_logger = logging.getLogger()
root_logger.debug('root DEBUG')
root_logger.info('root INFO')
root_logger.warning('root WARNING')
root_logger.error('root ERROR')

log = logging.getLogger(__name__)
# log.warning("Configuring logging levels for noisy libraries")


for level, loggers in y("""
	INFO:
		- common.security_utils
		- google.auth._default
		- firebase_admin
		- passlib.utils.compat
	WARNING:
		- urllib3
		- hpack
		- httpcore
		- httpx
""").items():
	# log.warning(f"Setting {level} level for loggers: {loggers}, {type(loggers)}")
	level = getattr(logging, level)
	for name in loggers:
		logging.getLogger(name).setLevel(level)


# log.warning("Importing FastAPI and related modules")

import time
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

import os
import sys

# Add common module path for both local development and Docker
common_path = os.path.join(os.path.dirname(__file__), '..', '..', 'common')
sys.path.append(common_path)
from common.database import get_db
from common.config import is_rate_limiting_disabled, rate_limit_config, get_cors_origins
from user_routes import start_session_cleanup
import fcm_push

# Configuration
USER_ACCOUNTS = os.getenv("USER_ACCOUNTS", "false").lower() in ("true", "1", "yes")


@asynccontextmanager
async def lifespan(app: FastAPI):
	# Startup
	log.info(f"Application startup initiated, DEV_MODE: {os.getenv('DEV_MODE', 'false')}")
	rate_limit_config.log_configuration()
	await start_session_cleanup()
	fcm_push.init()
	log.info("Application startup completed")
	yield
	# Shutdown
	log.info("Application shutdown initiated")
	from user_routes import stop_session_cleanup
	await stop_session_cleanup()
	log.info("Application shutdown completed")


from fastapi import FastAPI
from swagger_ui import api_doc

# class Settings(BaseSettings):
# 	openapi_url: str = "/openapi.json"
# settings = Settings()

app = FastAPI(
	# openapi_url=settings.openapi_url,
	docs_url=None, redoc_url=None,
	title="Hillview API", description="API for Hillview application", lifespan=lifespan
)


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
			# log.debug(f"Rate limiting bypassed globally (NO_LIMITS=true) for {request.url.path}")
			return await call_next(request)

		# Skip rate limiting for certain paths and methods
		if (request.url.path in self.bypass_paths or
			request.method == "OPTIONS" or
			request.url.path.startswith("/api/debug")):
			return await call_next(request)

		# Worker file uploads get their own limit
		limit_type = 'worker_upload' if request.url.path == "/api/photos/upload-file" else 'general_api'

		# Apply rate limiting
		try:
			await self.rate_limiter.enforce_rate_limit(request, limit_type)
		except HTTPException as e:
			# Return rate limit response
			from fastapi.responses import JSONResponse
			return JSONResponse(
				status_code=e.status_code,
				content={"detail": e.detail},
				headers=e.headers
			)

		return await call_next(request)


# Request logging middleware with real client IP
class RequestLoggingMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		from rate_limiter import get_client_ip

		# Get real client IP (handles proxy headers)
		client_ip = get_client_ip(request)
		start_time = time.time()

		response = await call_next(request)

		# Calculate response time
		process_time = time.time() - start_time

		# Log access in a format similar to standard access logs but with real client IP
		log.info(f'{client_ip} - "{request.method} {request.url.path}" {response.status_code} {process_time:.3f}s')

		return response


# CORS request logging middleware
class CORSLoggingMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		# Log CORS-related request details
		origin = request.headers.get("origin")
		access_control_request_method = request.headers.get("access-control-request-method")
		access_control_request_headers = request.headers.get("access-control-request-headers")

		if request.method == "OPTIONS" or origin:
			#log.info(f"CORS Request: {request.method} {request.url}")
			#log.info(f"  Origin: {origin}")
			if access_control_request_method:
				#log.info(f"  Access-Control-Request-Method: {access_control_request_method}")
				pass
			if access_control_request_headers:
				#log.info(f"  Access-Control-Request-Headers: {access_control_request_headers}")
				pass

		response = await call_next(request)

		# Log CORS-related response headers
		if request.method == "OPTIONS" or origin:
			access_control_allow_origin = response.headers.get("access-control-allow-origin")
			access_control_allow_methods = response.headers.get("access-control-allow-methods")
			access_control_allow_headers = response.headers.get("access-control-allow-headers")
			access_control_allow_credentials = response.headers.get("access-control-allow-credentials")

			#log.info(f"CORS Response: {response.status_code}")
			#log.info(f"  Access-Control-Allow-Origin: {access_control_allow_origin}")
			if access_control_allow_methods:
				#log.info(f"  Access-Control-Allow-Methods: {access_control_allow_methods}")
				pass
			if access_control_allow_headers:
				#log.info(f"  Access-Control-Allow-Headers: {access_control_allow_headers}")
				pass
			if access_control_allow_credentials:
				#log.info(f"  Access-Control-Allow-Credentials: {access_control_allow_credentials}")
				pass

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
app.add_middleware(CORSLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ReverseProxyMiddleware)


# Add exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	"""Log Pydantic validation errors (422) with full details."""
	from fastapi.encoders import jsonable_encoder
	errors = exc.errors()
	log.error(f"Validation error on {request.method} {request.url.path}")
	log.error(f"Validation errors: {errors}")
	# Also log the body if available (for debugging)
	try:
		body = await request.body()
		if body:
			log.error(f"Request body: {body[:2000].decode('utf-8', errors='replace')}")
	except Exception:
		pass
	# Return standard FastAPI validation error response (use jsonable_encoder to handle non-serializable types)
	return JSONResponse(
		status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
		content={"detail": jsonable_encoder(errors)}
	)


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

	# Include best-of routes (only with user accounts)
	import bestof_routes

	app.include_router(bestof_routes.router)

	# Include push notification routes (only with user accounts)
	import push_routes

	app.include_router(push_routes.router)

# Include core routes
import mapillary_routes

app.include_router(mapillary_routes.router)

import hillview_routes

app.include_router(hillview_routes.router)

import hidden_content_routes

app.include_router(hidden_content_routes.router)

import flagged_photos_routes

app.include_router(flagged_photos_routes.router)

import contact_routes

app.include_router(contact_routes.router)

import worker_routes

app.include_router(worker_routes.router)

import annotation_routes

app.include_router(annotation_routes.router)

import featured_routes

app.include_router(featured_routes.router)

import debug_routes

app.include_router(debug_routes.router)


# Self-hosted Swagger UI (assets bundled in swagger-ui-py package, served same-origin under /docs).
# Must be registered after all routers so app.openapi() reflects the full schema.
api_doc(app, config=app.openapi(), url_prefix='/docs', title='Hillview API')


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


