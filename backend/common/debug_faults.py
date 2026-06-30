"""Internal-only HTTP fault injection for testing client recuperation.

Shared by the API and worker FastAPI apps — both call ``install(app)``.
Arm a fault for a path glob so matching requests fail with a chosen status
(optionally after a delay), for a limited count or until cleared.

Inert in production: fault injection — the middleware, the per-request matcher, and
the arm/clear endpoints — is gated PURELY on ``DEV_MODE``, stricter than the
read-only debug endpoints (which ``DEBUG_ENDPOINTS`` may enable). Injecting a fault
actively breaks a live request, so it must only ever run on an explicit dev/test
box, never prod. The middleware also no-ops when nothing is armed. State is
per-process — arming on the API affects only the API; arm on the worker (its own
``/debug/faults`` endpoint) to fault worker requests.

The web stack (starlette) is imported lazily in ``install()`` so the fault logic
(arm/match/clear/snapshot) stays importable — and unit-testable — without it.
"""

import fnmatch
import os
import threading
from dataclasses import dataclass
from typing import List, Optional


def is_enabled() -> bool:
	"""Broad debug-endpoint gate: DEBUG_ENDPOINTS or DEV_MODE.

	Used for the read-only/diagnostic debug routes. Fault INJECTION uses the
	stricter faults_enabled() (DEV_MODE-only) instead — see below.
	"""
	env = os.environ
	return (
		env.get("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes")
		or env.get("DEV_MODE", "false").lower() in ("true", "1", "yes")
	)


def faults_enabled() -> bool:
	"""Fault injection gate — DEV_MODE only, intentionally stricter than is_enabled().

	A fault breaks a live request, so unlike the read-only debug endpoints it must
	never be active anywhere but an explicit dev/test box. DEBUG_ENDPOINTS (which can
	plausibly be on in a staging-ish env to expose diagnostics) must NOT enable it.
	DEV_MODE is the unambiguous "not prod" signal, and the same gate the worker's
	other debug knob (max_pending_tasks) uses.
	"""
	return os.environ.get("DEV_MODE", "false").lower() in ("true", "1", "yes")


@dataclass
class Fault:
	path: str  # glob, matched against request.url.path
	status: int = 503
	detail: str = "Injected fault (debug)"
	methods: Optional[List[str]] = None  # None = any method
	delay_seconds: float = 0.0
	remaining: Optional[int] = None  # None = until cleared; else per-hit countdown


_lock = threading.Lock()
_faults: List[Fault] = []


def arm(
	path: str,
	status: int = 503,
	detail: str = "Injected fault (debug)",
	methods: Optional[List[str]] = None,
	count: Optional[int] = None,
	delay_seconds: float = 0.0,
) -> Fault:
	fault = Fault(
		path=path,
		status=status,
		detail=detail,
		methods=[m.upper() for m in methods] if methods else None,
		delay_seconds=delay_seconds,
		remaining=count,
	)
	with _lock:
		_faults.append(fault)
	return fault


def clear() -> None:
	with _lock:
		_faults.clear()


def snapshot() -> List[dict]:
	with _lock:
		return [vars(f).copy() for f in _faults]


def match(method: str, path: str) -> Optional[Fault]:
	"""Return the first live fault matching this request, consuming one hit."""
	# Fast path: nothing armed (the normal / production case).
	if not _faults:
		return None
	if not faults_enabled():
		return None
	method_up = method.upper()
	with _lock:
		for f in _faults:
			if f.methods and method_up not in f.methods:
				continue
			if not fnmatch.fnmatch(path, f.path):
				continue
			if f.remaining is not None:
				if f.remaining <= 0:
					continue
				f.remaining -= 1
			return f
	return None


def add_fault_routes(target, prefix: str = "/faults") -> None:
	"""Register the GET/POST/DELETE fault endpoints on a FastAPI app or router.

	The api mounts these on its internal (localhost-guarded) router; the worker
	mounts them on its app under /debug — same request shape and verbs in both,
	only the mount point / network guard differs. Both 404 unless faults_enabled()
	(DEV_MODE only), so arming a fault and the middleware that applies it share one
	gate — you can never arm a fault on a box where the middleware isn't installed.

	fastapi/pydantic are imported lazily so the fault logic above stays importable
	(and unit-testable) without the web stack.
	"""
	from fastapi import HTTPException, status
	from pydantic import BaseModel, Field
	from typing import List as _List, Optional as _Optional

	def _require_enabled() -> None:
		if not faults_enabled():
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug endpoints disabled")

	class FaultSpec(BaseModel):
		path: str = Field(..., description="URL-path glob, e.g. '/api/auth/me' or '/upload*'")
		status: int = Field(503, description="HTTP status returned for matching requests")
		detail: str = Field("Injected fault (debug)", description="Response body detail")
		methods: _Optional[_List[str]] = Field(None, description="Restrict to these methods (default: any)")
		count: _Optional[int] = Field(None, description="Fail this many requests then stop (default: until cleared)")
		delay_seconds: float = Field(0.0, ge=0, description="Delay before failing (e.g. to simulate a slow/timeout)")

	@target.get(prefix)
	async def list_faults():
		"""List currently-armed HTTP faults."""
		_require_enabled()
		return {"faults": snapshot()}

	@target.post(prefix)
	async def arm_fault(spec: FaultSpec):
		"""Arm an HTTP fault so matching requests fail (chaos-monkey request nuking)."""
		_require_enabled()
		arm(
			path=spec.path,
			status=spec.status,
			detail=spec.detail,
			methods=spec.methods,
			count=spec.count,
			delay_seconds=spec.delay_seconds,
		)
		return {"status": "ok", "faults": snapshot()}

	@target.delete(prefix)
	async def clear_faults():
		"""Clear all armed HTTP faults."""
		_require_enabled()
		clear()
		return {"status": "ok", "faults": snapshot()}


def install(app) -> None:
	"""Add the fault-injection middleware to a Starlette/FastAPI app.

	Implemented as a PURE ASGI middleware, deliberately NOT a BaseHTTPMiddleware:
	when no fault matches it forwards scope/receive/send straight to the app, so it
	adds no body buffering or response proxying. BaseHTTPMiddleware re-wraps the
	request/response in anyio memory streams, and stacking one more of those under
	the app's existing BaseHTTPMiddlewares intermittently broke body-carrying
	authenticated requests (e.g. /api/auth/register-client-key would fail at the
	network layer in some browsers). A pure passthrough avoids that entirely.

	Only installed when faults can actually be armed (faults_enabled() — DEV_MODE
	only), so in production (and any DEBUG_ENDPOINTS-but-not-DEV_MODE env) the
	middleware is never even added to the stack — zero overhead, zero risk.

	starlette is imported here (lazily) rather than at module top so the fault
	logic above stays importable without the web stack.
	"""
	if not faults_enabled():
		return

	import asyncio

	from starlette.responses import JSONResponse

	class FaultInjectionMiddleware:
		def __init__(self, app):
			self.app = app

		async def __call__(self, scope, receive, send):
			# Only HTTP requests can match a fault; everything else (websocket,
			# lifespan) passes straight through untouched.
			if scope.get("type") != "http":
				await self.app(scope, receive, send)
				return
			fault = match(scope["method"], scope["path"])
			if fault is None:
				# The common case (nothing armed): a direct passthrough, no buffering.
				await self.app(scope, receive, send)
				return
			if fault.delay_seconds > 0:
				await asyncio.sleep(fault.delay_seconds)
			response = JSONResponse(status_code=fault.status, content={"detail": fault.detail})
			await response(scope, receive, send)

	app.add_middleware(FaultInjectionMiddleware)
