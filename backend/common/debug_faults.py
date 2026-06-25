"""Internal-only HTTP fault injection for testing client recuperation.

Shared by the API and worker FastAPI apps — both call ``install(app)``.
Arm a fault for a path glob so matching requests fail with a chosen status
(optionally after a delay), for a limited count or until cleared.

Inert in production: faults can only be armed through each service's debug
endpoint (gated on ``DEBUG_ENDPOINTS`` / ``DEV_MODE``), and the middleware no-ops
when nothing is armed. State is per-process — arming on the API affects only the
API; arm on the worker (its own ``/debug/faults`` endpoint) to fault worker
requests.

The web stack (starlette) is imported lazily in ``install()`` so the fault logic
(arm/match/clear/snapshot) stays importable — and unit-testable — without it.
"""

import fnmatch
import os
import threading
from dataclasses import dataclass
from typing import List, Optional


def is_enabled() -> bool:
	"""Fault injection is only active in dev/test (never armed/applied in prod)."""
	env = os.environ
	return (
		env.get("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes")
		or env.get("DEV_MODE", "false").lower() in ("true", "1", "yes")
	)


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
	if not is_enabled():
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


def add_fault_routes(target, prefix: str = "/faults", gate=None) -> None:
	"""Register the GET/POST/DELETE fault endpoints on a FastAPI app or router.

	The api mounts these on its internal (localhost-guarded) router; the worker
	mounts them on its app under /debug — same request shape and verbs in both,
	only the mount point / network guard differs.

	`gate` is the enable predicate the handlers enforce (404 when it returns False);
	defaults to is_enabled() (DEBUG_ENDPOINTS or DEV_MODE). The worker passes a
	DEV_MODE-only predicate so its fault route stays gated exactly like its other
	debug knob (max_pending_tasks) and can't be opened by a stray DEBUG_ENDPOINTS in
	the worker's prod env — it's an internet-adjacent fly.io service with no IP guard.

	fastapi/pydantic are imported lazily so the fault logic above stays importable
	(and unit-testable) without the web stack.
	"""
	from fastapi import HTTPException, status
	from pydantic import BaseModel, Field
	from typing import List as _List, Optional as _Optional

	enabled = gate or is_enabled

	class FaultSpec(BaseModel):
		path: str = Field(..., description="URL-path glob, e.g. '/api/auth/me' or '/upload*'")
		status: int = Field(503, description="HTTP status returned for matching requests")
		detail: str = Field("Injected fault (debug)", description="Response body detail")
		methods: _Optional[_List[str]] = Field(None, description="Restrict to these methods (default: any)")
		count: _Optional[int] = Field(None, description="Fail this many requests then stop (default: until cleared)")
		delay_seconds: float = Field(0.0, ge=0, description="Delay before failing (e.g. to simulate a slow/timeout)")

	def _require_enabled() -> None:
		if not enabled():
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug endpoints disabled")

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

	starlette is imported here (lazily) rather than at module top so the fault
	logic above stays importable without the web stack.
	"""
	import asyncio

	from starlette.middleware.base import BaseHTTPMiddleware
	from starlette.responses import JSONResponse

	class FaultInjectionMiddleware(BaseHTTPMiddleware):
		async def dispatch(self, request, call_next):
			fault = match(request.method, request.url.path)
			if fault is not None:
				if fault.delay_seconds > 0:
					await asyncio.sleep(fault.delay_seconds)
				return JSONResponse(status_code=fault.status, content={"detail": fault.detail})
			return await call_next(request)

	app.add_middleware(FaultInjectionMiddleware)
