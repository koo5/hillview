"""
FastAPI Worker Service for Photo Processing

This service handles photo processing tasks with JWT authentication.
It exposes the process_uploaded_photo function as a REST API endpoint.

IMPORTANT — Startup time & lazy loading:
  On Fly.io with min_machines_running=0, an incoming request wakes the
  machine and the proxy waits for uvicorn to accept connections.  The proxy
  timeout is ~8-10 s — much shorter than the health-check grace_period.
  Heavy libraries (cv2, pyvips, PIL, numpy via photo_processor) take ~10 s
  to import, so they MUST NOT be imported at module level here.

  - photo_processor is imported lazily inside run_photo_processing_sync().
  - PhotoDeletedException lives in the lightweight exceptions.py module so
    we can catch it without importing photo_processor.
  - numpy (np) is lazy-loaded on first call to validate_json_payload().

  If you add new imports, make sure they don't transitively pull in
  photo_processor, cv2, pyvips, or PIL at module load time.
"""
import os
import asyncio
import json
import threading
import logging
import sys
import time
from contextlib import asynccontextmanager

import requests
import psutil
from dotenv import load_dotenv
import socket
import hashlib

# Load environment variables from .env file in same directory as script
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Starlette ≥0.45's MultiPartParser caps each part at 1 MiB by default,
# which rejects normal photo uploads with
# `400 "There was an error parsing the body"`. Raise it to MAX_FILE_SIZE
# (same env var the app's own validator uses).
#
# Important: the cap is bound in *three* places — patching just one is a
# no-op on Starlette ≥0.49 because each layer binds its own default and
# passes it explicitly down the chain. FastAPI calls ``request.form()``
# with no args (``fastapi/routing.py``), Starlette's ``Request.form``
# has its own default, and ``Request._get_form`` likewise — only the
# innermost ``MultiPartParser.__init__`` default would be hit if all
# three callers stopped passing the value explicitly, which they
# don't. So patch the upstream defaults too.
_MAX_PART_SIZE = int(os.environ.get('MAX_FILE_SIZE', 150 * 1024 * 1024))
from starlette.formparsers import MultiPartParser
from starlette.requests import Request
MultiPartParser.__init__.__kwdefaults__['max_part_size'] = _MAX_PART_SIZE
Request.form.__kwdefaults__['max_part_size'] = _MAX_PART_SIZE
Request._get_form.__kwdefaults__['max_part_size'] = _MAX_PART_SIZE

import aiofiles
import httpx
import math
np = None  # lazy-loaded in validate_json_payload (see module docstring)

from typing import Optional, Any
from uuid import UUID
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict
from starlette.concurrency import run_in_threadpool
from throttle import Throttle

throttle = Throttle('app')

# Add parent directories to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from jwt_service import validate_upload_authorization_token, sign_processing_result
from exceptions import PhotoDeletedException

from common.file_utils import (
	validate_and_prepare_photo_file,
	verify_saved_file_content,
	cleanup_file_on_error,
	get_file_size_from_upload
)
from common.security_utils import (
	SecurityValidationError,
	validate_photo_id,
	validate_user_id,
	sanitize_filename
)
from common.config import get_cors_origins
#from photo_processor import photo_processor

# Setup logging
logging.basicConfig(level=logging.DEBUG)
# Quiet noisy HTTP logs
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Import and setup task context logging
from logging_context import setup_task_logging, task_context, current_photo_id, current_task_id
import processing_state
setup_task_logging()


def validate_json_payload(obj: Any, path: str = "") -> None:
	"""Validate that an object can be safely serialized to JSON.

	Raises ValueError with detailed path if any problematic values are found:
	- NaN or infinity floats
	- numpy types that haven't been converted
	- Other non-JSON-serializable types
	"""
	global np
	if np is None:
		import numpy as np

	if obj is None or isinstance(obj, (bool, str)):
		return
	if isinstance(obj, int):
		return
	if isinstance(obj, float):
		if math.isnan(obj):
			raise ValueError(f"NaN float at {path or 'root'}")
		if math.isinf(obj):
			raise ValueError(f"Infinity float at {path or 'root'}")
		return
	if isinstance(obj, dict):
		for k, v in obj.items():
			validate_json_payload(v, f"{path}.{k}" if path else k)
		return
	if isinstance(obj, (list, tuple)):
		for i, item in enumerate(obj):
			validate_json_payload(item, f"{path}[{i}]")
		return
	# Check for numpy types
	if isinstance(obj, (np.integer, np.floating)):
		raise ValueError(f"Unconverted numpy type {type(obj).__name__} at {path or 'root'}")
	if isinstance(obj, np.ndarray):
		raise ValueError(f"Unconverted numpy array at {path or 'root'}")
	# Unknown type
	raise ValueError(f"Non-JSON-serializable type {type(obj).__name__} at {path or 'root'}")


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Start the background task ping loop on startup.

	start_background_loop is defined later in this module; it's only called
	here at startup time, by which point the module is fully imported.
	"""
	# uvicorn replaces the root logger's handlers during startup, so the
	# setup_task_logging() call at module load time only reaches the old
	# basicConfig handler. Re-applying here installs the filter + formatter
	# on uvicorn's handlers so [task=X photo=Y] actually appears in output.
	setup_task_logging()
	start_background_loop()
	yield


# FastAPI app
app = FastAPI(
	title="Hillview Photo Processing Worker",
	description="Photo processing service with JWT authentication",
	version="1.0.1",
	lifespan=lifespan,
)


# CORS configuration
app.add_middleware(
	CORSMiddleware,
	allow_origins=get_cors_origins(),
	allow_credentials=True,
	allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
	allow_headers=["Content-Type", "Authorization", "Accept"],
)

# HTTP Bearer security scheme
security = HTTPBearer()

# Configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads/"))
UPLOAD_DIR.mkdir(exist_ok=True)
API_URL = os.getenv("API_URL", "http://localhost:8055/api")
FLY_MACHINE_ID = os.environ.get("FLY_MACHINE_ID", None)


def get_worker_identity() -> str:
	"""
	Generate a unique worker identity for audit trail.

	This creates a semi-permanent identifier for this worker instance that can be used
	to track which worker processed which photos for debugging and audit purposes.

	The identity includes:
	- Worker hostname/container ID
	- Process start time
	- Short hash for uniqueness

	Example: "worker-container-abc123_20241201-143022_x9k2m"
	"""
	# Get hostname/container identifier
	hostname = socket.gethostname()

	# Get process start time (approximation)
	start_time = datetime.now().strftime("%Y%m%d-%H%M%S")

	# Create a short hash for uniqueness (not used for security, just identifier generation)
	unique_string = f"{hostname}-{start_time}-{os.getpid()}"
	hash_suffix = hashlib.md5(unique_string.encode(), usedforsecurity=False).hexdigest()[:5]

	return f"{hostname}_{start_time}_{hash_suffix}"

# Generate worker identity once at startup
WORKER_IDENTITY = get_worker_identity()
logger.info(f"Worker identity: {WORKER_IDENTITY}, PID: {os.getpid()}, DEV_MODE: {os.getenv('DEV_MODE')}, FLY_MACHINE_ID: {FLY_MACHINE_ID}")

# Semaphore to limit concurrent photo processing
PARALLEL_PROCESSING_CONCURRENCY = int(os.getenv("PARALLEL_PROCESSING_CONCURRENCY", "3"))
logger.info(f"PARALLEL_PROCESSING_CONCURRENCY: {PARALLEL_PROCESSING_CONCURRENCY}")
processing_semaphore = asyncio.Semaphore(PARALLEL_PROCESSING_CONCURRENCY)

# Backpressure: reject new uploads once this many background tasks are queued.
# Each queued task holds two full-size copies on disk (Starlette's multipart
# spool + our UPLOAD_DIR copy) until it gets a semaphore slot, so the cap
# bounds peak disk usage at roughly 2 * MAX_PENDING_TASKS * file size.
MAX_PENDING_TASKS = int(os.getenv("MAX_PENDING_TASKS", "100"))
QUEUE_FULL_RETRY_AFTER_SECONDS = int(os.getenv("QUEUE_FULL_RETRY_AFTER_SECONDS", "500"))
logger.info(f"MAX_PENDING_TASKS: {MAX_PENDING_TASKS}")

# Bound on how long a queued task may wait for a processing slot / free RAM.
# Without it a wedged slot (stuck C code) or RAM starvation would hold the
# queue at "full" forever, permanently rejecting uploads. On timeout the task
# errors out through the existing TimeoutError path: the API is notified with
# retry_after_minutes, the client retries later, and the queue drains.
QUEUE_WAIT_TIMEOUT_SECONDS = int(os.getenv("QUEUE_WAIT_TIMEOUT_SECONDS", "76000"))


def run_photo_processing_sync(file_path: str, filename: str, user_id: UUID, photo_id: str, client_signature: str, ctx_photo_id: str = None, ctx_task_id: str = None, anonymization_override: str = None, metadata: Dict[str, Any] = None, quality: int = None, fast: bool = False, files_to_clean: Optional[list] = None):
	"""
	Sync wrapper to run async photo processing in a dedicated event loop.
	This runs in a thread pool to avoid blocking the main event loop.

	ctx_photo_id and ctx_task_id are used to restore logging context in the new thread.
	anonymization_override: JSON string - null=auto, "[]"=none, "[{...}]"=specific rectangles
	quality: WebP quality (1-100). None=use default (97).
	fast: Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding, reduced size set.
	files_to_clean: mutable list the processor appends intermediate/derived file paths to
	(e.g. the .tiff produced from a CR2); the caller cleans every entry in its finally.
	"""
	# Restore logging context in this thread
	with task_context(photo_id=ctx_photo_id, task_id=ctx_task_id):
		from blur import collect_warnings
		# Bracket the whole sync run with a TLS warning collector so
		# _dev_only calls anywhere downstream (in this thread, including
		# its nested event loop) accumulate into one list. Attached to the
		# result dict for the calling /upload handler to surface.
		with collect_warnings() as warnings:
			loop = asyncio.new_event_loop()
			try:
				from photo_processor import photo_processor
				result = loop.run_until_complete(
					photo_processor.process_uploaded_photo(
						file_path=file_path,
						filename=filename,
						user_id=user_id,
						photo_id=photo_id,
						client_signature=client_signature,
						anonymization_override=anonymization_override,
						metadata=metadata,
						quality=quality,
						fast=fast,
						files_to_clean=files_to_clean,
					)
				)
			finally:
				loop.close()
			if isinstance(result, dict) and warnings:
				result['warnings'] = list(warnings)
			return result


pending_background_tasks_mutex = threading.Lock()
pending_background_tasks = set()
task_id_counter = 1


def pending_tasks_count() -> int:
	with pending_background_tasks_mutex:
		return len(pending_background_tasks)


def queue_is_full() -> bool:
	return pending_tasks_count() >= MAX_PENDING_TASKS


class UploadBackpressureMiddleware:
	"""Pure ASGI middleware: reject /upload* with 503 while the background
	task queue is at capacity, *before* FastAPI parses the multipart body.

	This must run at the ASGI layer — FastAPI calls ``request.form()``
	(draining the entire upload off the socket into the spool file) before
	solving any endpoint dependencies, so an in-endpoint check would only
	fire after the full body was already received and spooled to disk.

	The response is sent without reading the request body. Clients that are
	mid-upload may see a connection reset instead of the 503; all our
	clients treat that as a retryable failure, so either outcome backs
	them off.
	"""

	def __init__(self, app):
		self.app = app

	async def __call__(self, scope, receive, send):
		if (
			scope["type"] == "http"
			and scope["method"] == "POST"
			and scope["path"].startswith("/upload")
			and queue_is_full()
		):
			pending = pending_tasks_count()
			logger.warning(f"Rejecting upload: {pending} pending tasks >= MAX_PENDING_TASKS ({MAX_PENDING_TASKS})")
			body = json.dumps({
				"detail": "worker_queue_full",
				"pending_tasks": pending,
				"retry_after_seconds": QUEUE_FULL_RETRY_AFTER_SECONDS,
			}).encode()
			await send({
				"type": "http.response.start",
				"status": 503,
				"headers": [
					(b"content-type", b"application/json"),
					(b"content-length", str(len(body)).encode()),
					(b"retry-after", str(QUEUE_FULL_RETRY_AFTER_SECONDS).encode()),
				],
			})
			await send({"type": "http.response.body", "body": body})
			return
		await self.app(scope, receive, send)


app.add_middleware(UploadBackpressureMiddleware)

# Debug-only HTTP fault injection, shared with the API; inert unless armed.
from common import debug_faults
debug_faults.install(app)


def _log_worker_status():
	st = worker_status()
	logger.info(
		f"Worker status: pending={st['pending_tasks']} "
		f"queued_for_slot={st['queued_for_slot']} "
		f"slots_in_use={st['slots_in_use']}/{st['concurrency']} "
		f"processing={st['processing']} "
		f"stalled_in_gate={st['stalled_in_gate']} "
		f"ram_mb={st['available_ram_mb']}"
	)
	active = processing_state.format_active()
	if active:
		logger.info(f"Active phases: [{active}]")


def background_loop():
	consecutive_failures = 0
	while True:
		with pending_background_tasks_mutex:
			l = len(pending_background_tasks)
			task0 = list(pending_background_tasks)[0] if l > 0 else None

		if l > 0:
			_log_worker_status()
			try:
				resp = requests.post(
					f"{API_URL}/worker_pending_background_tasks_ping",
					json={
						"worker_identity": WORKER_IDENTITY,
						"fly_machine_id": FLY_MACHINE_ID,
						"pending_tasks": l,
						"task0_id": task0
					},
					timeout=60
				)
				if resp.status_code == 200:
					consecutive_failures = 0
					time.sleep(10)
				else:
					consecutive_failures += 1
					delay = min(2 ** consecutive_failures, 30)
					logger.warning(f"Ping returned {resp.status_code}, backing off {delay}s")
					time.sleep(delay)
			except requests.Timeout:
				consecutive_failures += 1
				time.sleep(min(2 ** consecutive_failures, 30))
			except Exception as e:
				consecutive_failures += 1
				delay = min(2 ** consecutive_failures, 30)
				logger.warning(f"Failed to ping API with pending tasks: {e}, backing off {delay}s")
				time.sleep(delay)
		else:
			# No async-path tasks, but sync /upload requests don't register in
			# pending_background_tasks — log via processing_state so their
			# progress is still visible.
			if processing_state.format_active():
				_log_worker_status()
			consecutive_failures = 0
			time.sleep(10)


# Start background loop in a daemon thread
def start_background_loop():
	thread = threading.Thread(target=background_loop, daemon=True)
	thread.start()
	logger.info("Background task ping loop started")


# Request/Response models
class AltLocation(BaseModel):
	"""Background-tracking alternative location: the live GPS fix when a photo's
	primary location was a manual map pan. Android embeds this in the JPEG's EXIF
	UserComment (Rust writer); browser uploads carry it here and the worker
	synthesizes the same UserComment, so both converge in exif_data."""
	lat: float
	lng: float
	ts: Optional[int] = None
	accuracy: Optional[float] = None
	source: Optional[str] = None  # e.g. 'gps-background'


class BrowserMetadata(BaseModel):
	"""Metadata provided when EXIF can't be written (e.g., browser capture)"""
	latitude: Optional[float] = None
	longitude: Optional[float] = None
	altitude: Optional[float] = None
	bearing: Optional[float] = None
	captured_at: Optional[str] = None  # ISO datetime
	orientation_code: Optional[int] = None  # EXIF orientation (1, 3, 6, 8)
	location_source: Optional[str] = None  # 'gps' or 'map'
	bearing_source: Optional[str] = None
	alt_location: Optional[AltLocation] = None  # background-tracking GPS alternative; worker folds it into UserComment
	accuracy: Optional[float] = None
	encoding: Optional[str] = None  # EXR pixel encoding: 'srgb' or 'linear' (sourced from .exr.encoding sidecar at upload). Worker falls back to the embedded header tag when absent.


class ProcessPhotoResponse(BaseModel):
	success: bool
	message: str
	photo_id: Optional[str] = None
	error: Optional[str] = None
	retry_after_minutes: Optional[int] = None  # None = permanent failure, >0 = retry after N minutes
	warnings: Optional[list[str]] = None  # DEV_MODE speculative-handling notes from blur._dev_only

class ProcessedPhotoData(BaseModel):
	photo_id: str
	processing_status: str = "completed"
	width: Optional[int] = None
	height: Optional[int] = None
	latitude: Optional[float] = None
	longitude: Optional[float] = None
	compass_angle: Optional[float] = None
	altitude: Optional[float] = None
	exif_data: Optional[dict] = None
	sizes: Optional[dict] = None
	detected_objects: Optional[dict] = None
	error: Optional[str] = None
	client_signature: Optional[str] = None  # Base64-encoded ECDSA signature from client
	processed_by_worker: Optional[str] = None  # Worker identity for audit trail
	filename: Optional[str] = None  # Secure filename after processing
	captured_at: Optional[str] = None  # ISO datetime when photo was taken (from EXIF DateTimeOriginal)

# Authentication dependency for upload authorization
async def get_upload_authorization(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
	"""
	Validate upload authorization JWT token.
	Returns upload metadata including photo_id, user_id, client_public_key_id.
	"""
	token = credentials.credentials

	token_data = validate_upload_authorization_token(token)
	if not token_data:
		raise HTTPException(
			status_code=401,
			detail="Invalid upload authorization token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	return token_data

@app.get("/")
async def root():
	"""Health check endpoint."""
	return {"message": "Hillview Photo Processing Worker", "status": "running"}

@app.get("/health")
async def health_check():
	"""Health check endpoint."""
	return {"status": "healthy", "service": "photo-processor"}

def worker_status() -> dict:
	"""Live load snapshot, split across the worker's two independent gates.

	A photo passes through, in order:
	  1. accepted upload  → added to ``pending_background_tasks`` (counts in
	     ``pending_tasks``)
	  2. ``processing_semaphore.acquire()`` (concurrency cap) → ``slots_in_use``
	  3. ``wait_for_free_ram(500)`` then, in the threadpool, the photo_processor
	     start-stagger gate (``rate_limit(PARALLEL_PROCESSING_START_DELAY)``)
	  4. actually encoding → ``processing`` (the stagger throttle's
	     ``_running_tasks``)

	So ``slots_in_use`` is "holds a concurrency slot" while ``processing`` is
	"past the stagger, actually working". A large ``slots_in_use`` with a small
	``processing`` (i.e. ``stalled_in_gate`` high) means the start-stagger /
	RAM gate — NOT the semaphore — is the real concurrency limiter; lower
	``start_stagger_s`` (PARALLEL_PROCESSING_START_DELAY) and/or check
	``available_ram_mb``.

	Reads are lock-free on purpose: the stagger holds photo_processor's
	throttle ``_lock`` for up to START_DELAY, so acquiring it here would stall
	/ready. ``_running_tasks`` / ``_value`` are plain ints (atomic to read).
	photo_processor is imported lazily on first upload, so before any upload
	its module isn't loaded — we read it via sys.modules and report 0 rather
	than forcing the (heavy) import on a preflight.
	"""
	pending = pending_tasks_count()
	slots_free = getattr(processing_semaphore, "_value", None)
	slots_in_use = (PARALLEL_PROCESSING_CONCURRENCY - slots_free
					if slots_free is not None else None)
	pp = sys.modules.get("photo_processor")
	processing = getattr(pp.throttle, "_running_tasks", None) if pp is not None else 0
	start_stagger_s = getattr(pp, "PARALLEL_PROCESSING_START_DELAY", None) if pp is not None else None
	try:
		avail_mb = round(psutil.virtual_memory().available / (1024 * 1024))
	except Exception:
		avail_mb = None
	return {
		"pending_tasks": pending,                       # accepted, not finished (queued + holding a slot)
		"max_pending_tasks": MAX_PENDING_TASKS,
		"concurrency": PARALLEL_PROCESSING_CONCURRENCY,  # max processing slots (semaphore size)
		"slots_in_use": slots_in_use,                   # tasks holding a concurrency slot
		"slots_free": slots_free,
		"queued_for_slot": (max(0, pending - slots_in_use)
							if slots_in_use is not None else None),  # accepted, no slot yet
		"processing": processing,                       # past the start-stagger, actively encoding
		"stalled_in_gate": (max(0, slots_in_use - processing)
							if (slots_in_use is not None and processing is not None) else None),  # have a slot, stuck in stagger / RAM wait
		"start_stagger_s": start_stagger_s,             # PARALLEL_PROCESSING_START_DELAY (admit interval)
		"available_ram_mb": avail_mb,
	}

_PHASE_DOCS = [
	{"phase": "queued",              "where": "app.py",            "meaning": "Accepted, waiting for a semaphore slot (PARALLEL_PROCESSING_CONCURRENCY cap)"},
	{"phase": "wait_ram",            "where": "app.py / throttle", "meaning": "Slot acquired, waiting for 500 MB free RAM before entering the threadpool"},
	{"phase": "wait_stagger_Ns",     "where": "throttle.rate_limit","meaning": "Inside the start-stagger gate; N = reserved delay in seconds (PARALLEL_PROCESSING_START_DELAY)"},
	{"phase": "wait_ram_1500mb",     "where": "throttle.rate_limit","meaning": "Post-stagger RAM gate; waiting for 1500 MB free before starting YOLO + encoding"},
	{"phase": "read_exif",           "where": "photo_processor",   "meaning": "Running exiftool to extract EXIF / GPS metadata"},
	{"phase": "anonymizing",         "where": "photo_processor",   "meaning": "About to enter the throttle gate before YOLO detection"},
	{"phase": "yolo_scale_1.00",     "where": "anonymize.py",      "meaning": "YOLO inference at full resolution (multi-tile pass)"},
	{"phase": "yolo_scale_0.50",     "where": "anonymize.py",      "meaning": "YOLO inference at 0.5× resolution (and so on for lower scales)"},
	{"phase": "blur",                "where": "anonymize.py",      "meaning": "Applying Gaussian blur over detected faces / licence plates"},
	{"phase": "encode_sizes",        "where": "photo_processor",   "meaning": "Resizing + WebP encoding all size variants (full, 320, 640, 1200, 2048, 3072, 4096)"},
	{"phase": "dzi_pyramid",         "where": "photo_processor",   "meaning": "Building the DeepZoom tile pyramid for the zoomable viewer"},
	{"phase": "notifying_api",       "where": "app.py",            "meaning": "POSTing the processing result (EXIF, sizes, detections) back to the API server"},
]

@app.get("/status")
async def status():
	"""Extended status: worker identity, concurrency config, live queue snapshot, per-photo phases. See /status_help for phase definitions."""
	st = worker_status()
	return {
		"worker_identity": WORKER_IDENTITY,
		"fly_machine_id": FLY_MACHINE_ID,
		**st,
		"max_pending_tasks": MAX_PENDING_TASKS,
		"queue_wait_timeout_s": QUEUE_WAIT_TIMEOUT_SECONDS,
		"active_phases": processing_state.get_active_list(),
	}


@app.get("/status_help")
async def status_help():
	"""Describes every phase that can appear in /status active_phases."""
	return {"phases": _PHASE_DOCS}


@app.get("/ready")
async def readiness_check():
	"""Readiness endpoint: 503 while the upload queue is at capacity.

	Lets clients check before transmitting a photo body (the JS client
	preflights this before every upload attempt). Kept separate from
	/health so infra liveness checks don't recycle a machine that is
	merely busy. The body carries a live load snapshot (see worker_status)
	so clients/operators can see running-vs-queued, not just total pending.
	"""
	st = worker_status()
	if st["pending_tasks"] >= MAX_PENDING_TASKS:
		return JSONResponse(
			status_code=503,
			content={"status": "busy", **st},
			headers={"Retry-After": str(QUEUE_FULL_RETRY_AFTER_SECONDS)},
		)
	return {"status": "ready", **st}

@app.post("/debug/max_pending_tasks")
async def debug_set_max_pending_tasks(value: int):
	"""DEV_MODE-only runtime knob (mirrors the API's debug-endpoint pattern,
	gated on the worker's existing test-mode flag — 404 when off, so it's
	inert in production).

	Integration tests use value=0 to exercise queue-full behavior without
	actually filling the queue with MAX_PENDING_TASKS concurrent uploads.
	"""
	global MAX_PENDING_TASKS
	if os.environ.get('DEV_MODE', 'false').lower() != 'true':
		raise HTTPException(status_code=404, detail="Not found")
	old = MAX_PENDING_TASKS
	MAX_PENDING_TASKS = value
	logger.warning(f"DEV_MODE: MAX_PENDING_TASKS overridden {old} -> {value}")
	return {"old": old, "new": value}

# Chaos-monkey HTTP fault injection. Same typed GET/POST/DELETE shape as the API
# (common.debug_faults.add_fault_routes), gated DEV_MODE-only (faults_enabled) — like
# /debug/max_pending_tasks above — so it's inert in production (this is a real fly.io
# prod service with no IP guard) and can't be opened by a stray DEBUG_ENDPOINTS.
debug_faults.add_fault_routes(app, prefix="/debug/faults")

# Keep the DEV_MODE-only /debug/* routes (faults, max_pending_tasks) out of the
# public OpenAPI schema in prod. They're inert there, but there's no reason to
# advertise them on a no-IP-guard fly.io service. Mirrors the API's openapi
# filter; gated DEV_MODE-only to match the fault/knob gate above.
if os.environ.get('DEV_MODE', 'false').lower() != 'true':
	_full_openapi = app.openapi

	def _openapi_without_debug():
		schema = _full_openapi()
		for path in [p for p in schema.get("paths", {}) if "/debug" in p]:
			del schema["paths"][path]
		return schema

	app.openapi = _openapi_without_debug

@app.post("/await")
async def await_handler(task_id: str, request: Request):
	"""Wait for a background task to complete, sending periodic heartbeats to keep connection alive.
	Closes after 15s with {"status": "timeout"} to force fresh TCP connections from the caller."""

	async def heartbeat_generator():
		deadline = time.time() + 15
		while time.time() < deadline:
			if await request.is_disconnected():
				logger.info(f"Client {str(request.client)} disconnected while awaiting task {task_id}")
				return
			with pending_background_tasks_mutex:
				if task_id not in pending_background_tasks:
					yield b'{"status": "completed"}\n'
					return
			try:
				logger.debug(f"Awaiting task {task_id}, sending heartbeat to client {str(request.client)}")
			except Exception as e:
				logger.debug(f"Awaiting task {task_id}, sending heartbeat (client info unavailable: {e})")
			yield b'.\n'  # Heartbeat
			await asyncio.sleep(5)
		yield b'{"status": "timeout"}\n'

	return StreamingResponse(heartbeat_generator(), media_type="application/x-ndjson")




@app.get("/appcheck")
async def appcheck():
	"""Health check endpoint."""
	return {"status": "healthy", "service": "photo-processor"}
@app.get("/servicecheck")
async def servicecheck():
	"""Health check endpoint."""
	return {"status": "healthy", "service": "photo-processor"}


def validate_upload_parameters(upload_auth: dict, file) -> (str, str):

	# Extract upload authorization data
	raw_photo_id = upload_auth["photo_id"]
	raw_user_id = upload_auth["user_id"]
	client_key_id = upload_auth["client_public_key_id"]

	# Sanitize and validate critical parameters for filesystem and logging safety
	try:
		photo_id = validate_photo_id(raw_photo_id)
		user_id = validate_user_id(raw_user_id)
	except SecurityValidationError as e:
		logger.error(f"Invalid upload parameters: {e}")
		raise HTTPException(
			status_code=400,
			detail=f"Invalid upload parameters: {str(e)}"
		)

	logger.info(f"receive photo {photo_id}, user {user_id}, key {client_key_id}: {file.filename} ...")
	return photo_id, user_id


@app.post("/upload", response_model=ProcessPhotoResponse)
async def upload_sync(
	file: UploadFile = File(...),
	client_signature: str = Form(...),
	anonymization_override: Optional[str] = Form(None),  # JSON: null=auto, "[]"=none, "[{...}]"=specific
	metadata: Optional[str] = Form(None),  # JSON: metadata when EXIF can't be written (e.g., browser capture)
	quality: Optional[int] = Form(None),  # WebP quality (1-100). None=use default (97).
	fast: Optional[bool] = Form(None),  # Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding
	upload_auth: dict = Depends(get_upload_authorization)
):
	photo_id, user_id = validate_upload_parameters(upload_auth, file)
	return await upload(file, client_signature, photo_id, user_id, anonymization_override=anonymization_override, metadata=metadata, quality=quality, fast=bool(fast))


@app.post("/upload_async")
async def upload_async(
	file: UploadFile = File(...),
	client_signature: str = Form(...),
	anonymization_override: Optional[str] = Form(None),  # JSON: null=auto, "[]"=none, "[{...}]"=specific
	metadata: Optional[str] = Form(None),  # JSON: metadata when EXIF can't be written (e.g., browser capture)
	quality: Optional[int] = Form(None),  # WebP quality (1-100). None=use default (97).
	fast: Optional[bool] = Form(None),  # Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding
	upload_auth: dict = Depends(get_upload_authorization),
	background_tasks: BackgroundTasks = None
):
	global task_id_counter
	photo_id, user_id = validate_upload_parameters(upload_auth, file)
	with pending_background_tasks_mutex:
		task_id = f"{task_id_counter}_{time.time()}"
		task_id_counter += 1
		pending_background_tasks.add(task_id)
	background_tasks.add_task(upload, file, client_signature, photo_id, user_id, task_id, anonymization_override, metadata, quality, bool(fast))

	return {'success': True}


async def upload(file: UploadFile, client_signature: str, photo_id: str, user_id: str, task_id = None, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	with task_context(photo_id=photo_id, task_id=task_id):
		return await _upload_inner(file, client_signature, photo_id, user_id, task_id, anonymization_override, metadata, quality, fast)


async def _upload_inner(file: UploadFile, client_signature: str, photo_id: str, user_id: str, task_id = None, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	files_to_clean: list = []
	try:
		file_path, processing_status, error_message, retry_after_minutes, processing_result, secure_filename, files_to_clean = await process(file, client_signature, photo_id, user_id, anonymization_override, metadata, quality, fast)

		# DEV_MODE-only speculative-handling notes from blur._dev_only,
		# stuffed into processing_result by run_photo_processing_sync.
		warnings = (processing_result or {}).get("warnings") if isinstance(processing_result, dict) else None

		# Handle deleted photos early - no need to notify API
		if processing_status == "deleted":
			logger.info(f"Photo {photo_id} was deleted during processing, returning success")
			return ProcessPhotoResponse(
				success=True,
				photo_id=photo_id,
				message="Photo was deleted during processing",
				warnings=warnings,
			)

		# Always notify API server of result
		try:
			processed_data = ProcessedPhotoData(
				photo_id=photo_id,
				processing_status=processing_status,
				client_signature=client_signature,
				processed_by_worker=WORKER_IDENTITY,
				error=error_message
			)

			# Add success data if processing succeeded
			if processing_status == "completed" and processing_result:
				processed_data.width = processing_result.get("width")
				processed_data.height = processing_result.get("height")
				processed_data.latitude = processing_result.get("latitude")
				processed_data.longitude = processing_result.get("longitude")
				processed_data.compass_angle = processing_result.get("compass_angle")
				processed_data.altitude = processing_result.get("altitude")
				processed_data.exif_data = processing_result.get("exif_data")
				processed_data.sizes = processing_result.get("sizes")
				processed_data.detected_objects = processing_result.get("detected_objects")
				processed_data.filename = secure_filename
				processed_data.captured_at = processing_result.get("captured_at")

			# Send to API server
			worker_signature = sign_processing_result(processed_data.dict())
			payload = {
				"processed_data": processed_data.dict(),
				"worker_signature": worker_signature
			}

			# Validate payload before sending - fail fast if there are problematic values
			try:
				validate_json_payload(payload)
			except ValueError as e:
				logger.error(f"Payload validation failed for photo {photo_id}: {e}")
				logger.error(f"Problematic payload: {payload}")
				raise

			processing_state.set_phase("notifying_api")
			logger.info(f"Sending processing result to API server for photo {photo_id}")
			logger.info(f"Payload: {payload}")

			max_retries = 5
			async with httpx.AsyncClient() as client:
				for attempt in range(max_retries):
					try:
						response = await client.post(
							f"{API_URL}/photos/processed",
							json=payload,
							headers={"Content-Type": "application/json"},
							timeout=220.0
						)
					except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
						if attempt < max_retries - 1:
							delay = 2 ** attempt
							logger.warning(f"Connection error sending result for photo {photo_id} (attempt {attempt+1}/{max_retries}): {e}, retrying in {delay}s")
							await asyncio.sleep(delay)
							continue
						logger.error(f"Connection error sending result for photo {photo_id} after {max_retries} attempts: {e}")
						raise

					if response.status_code == 410:
						logger.info(f"Photo {photo_id} was deleted during processing, skipping result submission")
						return ProcessPhotoResponse(
							success=True,
							photo_id=photo_id,
							message="Photo was deleted during processing",
							warnings=warnings,
						)

					if response.status_code == 404 and os.environ.get('DEV_MODE', 'false').lower() == 'true':
						logger.info(f"DEV_MODE: photo {photo_id} not found at API (db likely cleared for next test), skipping result submission")
						return ProcessPhotoResponse(
							success=True,
							photo_id=photo_id,
							message="Photo not found (DEV_MODE)",
							warnings=warnings,
						)

					if response.status_code >= 500 and attempt < max_retries - 1:
						delay = 2 ** attempt
						logger.warning(f"Server error {response.status_code} for photo {photo_id} (attempt {attempt+1}/{max_retries}): {response.text}, retrying in {delay}s")
						await asyncio.sleep(delay)
						continue

					if response.status_code != 200:
						logger.error(f"API rejected processing result for photo {photo_id}: {response.status_code} - {response.text}")
					response.raise_for_status()
					logger.info(f"Successfully notified API server for photo {photo_id}")
					break

		except Exception as e:
			import traceback
			logger.error(f"Error notifying API for photo {photo_id}: {type(e).__name__}: {e}")
			logger.error(f"Traceback: {traceback.format_exc()}")
			raise HTTPException(status_code=500, detail="Failed to register result with API server")

	finally:
		processing_state.clear_phase()
		for path in files_to_clean:
			cleanup_file_on_error(Path(path))
		if task_id is not None:
			with pending_background_tasks_mutex:
				pending_background_tasks.discard(task_id)


	# Return success response
	return ProcessPhotoResponse(
		success=processing_status == "completed",
		message="Photo processed successfully" if processing_status == "completed" else "Photo processing failed",
		photo_id=photo_id,
		error=error_message if processing_status in ["failed", "error"] else None,
		retry_after_minutes=retry_after_minutes,
		warnings=warnings,
	)


async def process(file: UploadFile, client_signature: str, photo_id: str, user_id: str, anonymization_override: Optional[str] = None, metadata: Optional[str] = None, quality: Optional[int] = None, fast: bool = False):

	file_path = None
	error_message = None
	retry_after_minutes = None
	processing_result = None
	secure_filename = None
	# Everything in this list gets cleaned up in _upload_inner's finally.
	# The processor appends any intermediate files it creates (e.g. a .tiff
	# derived from an uploaded .CR2) so the caller can clean them all.
	files_to_clean: list = []

	safe_filename = sanitize_filename(file.filename)

	try:

		# Get file size and validate file
		file_size = get_file_size_from_upload(file.file)
		safe_filename, secure_filename, file_path = validate_and_prepare_photo_file(
			filename=file.filename,
			file_size=file_size,
			content_type=file.content_type,
			user_id=user_id,
			upload_base_dir=str(UPLOAD_DIR)
		)
		files_to_clean.append(str(file_path))

		# Save uploaded file
		async with aiofiles.open(file_path, 'wb') as f:
			content = await file.read()
			await f.write(content)

		# Verify file content
		if not verify_saved_file_content(str(file_path), "image"):
			raise ValueError("Invalid image file content")

		logger.info(f"File saved successfully: {file_path}")

		# Process the photo with concurrency limit
		user_uuid = UUID(user_id)

		# Bounded waits for a slot and for RAM — on timeout the task aborts
		# through the TimeoutError handler below instead of wedging the queue.
		processing_state.set_phase("queued")
		logger.info(f"Queued for processing slot (pending={pending_tasks_count()})")
		try:
			await asyncio.wait_for(processing_semaphore.acquire(), timeout=QUEUE_WAIT_TIMEOUT_SECONDS)
		except asyncio.TimeoutError:
			raise TimeoutError(f"No processing slot free after {QUEUE_WAIT_TIMEOUT_SECONDS}s")
		processing_state.set_phase("wait_ram")
		logger.info(f"Processing slot acquired")
		try:
			await throttle.wait_for_free_ram(500, timeout=QUEUE_WAIT_TIMEOUT_SECONDS)

			# Run processing in thread to avoid blocking the event loop
			# Capture current context to pass to the thread
			ctx_photo_id = current_photo_id.get()
			ctx_task_id = current_task_id.get()

			# Parse metadata JSON string if provided (e.g., from browser capture)
			parsed_metadata = None
			if metadata:
				parsed_metadata = BrowserMetadata.model_validate_json(metadata).model_dump(exclude_none=True)

			processing_result = await run_in_threadpool(
				run_photo_processing_sync,
				str(file_path),
				safe_filename,
				user_uuid,
				photo_id,
				client_signature,
				ctx_photo_id,
				ctx_task_id,
				anonymization_override,
				parsed_metadata,
				quality,
				fast,
				files_to_clean,
			)
		finally:
			processing_semaphore.release()

		if not processing_result:
			raise ValueError("Processing returned no result")

		logger.info(f"Photo processing completed for {safe_filename}")
		processing_status = "completed"

	except TimeoutError as te:
		logger.error(f"TimeoutError (processing slot / free RAM wait) for photo {photo_id}: {te}")
		processing_status = "error"
		error_message = "Insufficient resources to process photo, please retry later"
		retry_after_minutes = 15

	except ValueError as processing_error:
		# Processing errors (EXIF missing, corrupted data, etc.) - permanent failures
		logger.error(f"Photo processing failed for {safe_filename}: {processing_error}")
		processing_status = "error"
		error_message = str(processing_error)
		retry_after_minutes = None  # Permanent failure, no retry

	except PhotoDeletedException as e:
		# Photo was deleted during processing - this is expected, not an error
		logger.info(f"Photo deleted during processing: {e}")
		processing_status = "deleted"
		error_message = None
		retry_after_minutes = None

	except (IOError, OSError, PermissionError) as system_error:
		# System/IO errors (disk full, permissions, etc.) - retriable failures
		logger.error(f"System error processing photo {safe_filename}: {system_error}")
		processing_status = "error"
		error_message = f"System error: {system_error}"
		retry_after_minutes = 5  # Retry in 5 minutes

	except Exception as unexpected_error:
		# Unexpected errors - retriable failures with longer delay
		logger.error(f"Unexpected error processing photo {safe_filename}: {unexpected_error}")
		# exc_info = (type(exc), exc, exc.__traceback__)
		# logger.error('Exception occurred', exc_info=exc_info)
		processing_status = "error"
		error_message = f"Unexpected error: {unexpected_error}"
		retry_after_minutes = 10  # Retry in 10 minutes

	return file_path, processing_status, error_message, retry_after_minutes, processing_result, secure_filename, files_to_clean
