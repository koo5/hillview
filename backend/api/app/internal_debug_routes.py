"""Internal-only debug/ops endpoints.

Guarded by `require_internal_ip` (localhost-only, no proxy headers) so
they're safe to ship in prod: an operator with shell on the API box can
reach them via `curl http://127.0.0.1:<port>/api/internal/debug/...`
while the public Caddy front end rejects the `/api/internal/*` path.

Current tenants:
  - `debug_delays` knobs (see `debug_delays.py`). Inject artificial
    latency into named hot paths. Handy for reproducing slow-network
    behavior (photo-upload foreground notification visibility,
    client-side timeout tuning, etc.) without touching code or
    infrastructure.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import debug_delays
from internal_guard import require_internal_ip

log = logging.getLogger(__name__)

router = APIRouter(
	prefix="/api/internal/debug",
	tags=["internal-debug"],
	dependencies=[Depends(require_internal_ip)],
)


class SetDelayRequest(BaseModel):
	name: str = Field(..., description="Named hot-path key, e.g. 'authorize_upload'")
	seconds: float = Field(..., ge=0, description="Artificial sleep in seconds; 0 to clear")


@router.get("/delays")
async def list_delays():
	"""List currently-configured artificial delays."""
	return {"delays": debug_delays.snapshot()}


@router.post("/delays")
async def set_delay(req: SetDelayRequest):
	"""Set or clear an artificial delay for a named hot-path."""
	try:
		debug_delays.set_delay(req.name, req.seconds)
	except ValueError as e:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
	return {"status": "ok", "delays": debug_delays.snapshot()}
