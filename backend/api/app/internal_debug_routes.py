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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import debug_delays
import push_toggle
from auth import (
	clear_user_force_logout,
	force_user_logout,
	is_user_force_logged_out,
)
from common.database import get_db
from common.models import Notification, User
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


class PushEnabledRequest(BaseModel):
	enabled: bool = Field(..., description="Turn outgoing push (FCM + UnifiedPush) on or off.")


@router.get("/push-enabled")
async def get_push_enabled():
	"""Report current outgoing-push runtime state."""
	return {"enabled": push_toggle.is_enabled()}


@router.post("/push-enabled")
async def set_push_enabled(req: PushEnabledRequest):
	"""Toggle outgoing push (FCM + UnifiedPush). Test-state wipes reset to
	the DEV_MODE-driven default; in prod that default is ON."""
	push_toggle.set_enabled(req.enabled)
	return {"status": "ok", "enabled": push_toggle.is_enabled()}


@router.post("/clear-notifications")
async def clear_notifications(db: AsyncSession = Depends(get_db)):
	"""Truncate the `notifications` table.

	Activity-broadcast push emission filters out users who got an
	activity_broadcast row in the last 12 hours. Clearing the table
	makes every registered user eligible again — required so tests (and
	manual reproductions) can re-trigger the broadcast on demand without
	waiting out the window.
	"""
	result = await db.execute(delete(Notification))
	await db.commit()
	return {"status": "ok", "deleted": result.rowcount}


class ForceLogoutRequest(BaseModel):
	username: str = Field(..., description="Username whose sessions should be rejected")
	clear: bool = Field(False, description="If true, clear the flag instead of setting it")


@router.post("/force-logout-user")
async def force_logout_user(req: ForceLogoutRequest, db: AsyncSession = Depends(get_db)):
	"""Mark a user such that every subsequent access-token validation and
	refresh-token attempt is rejected with 401 — until the flag is cleared
	(manually via `clear=true`, or automatically on the user's next
	successful password login).

	Test scenarios use this to drive the Android client's "Login Required"
	notification path without touching client internals or needing to know
	the user's tokens.
	"""
	result = await db.execute(select(User).where(User.username == req.username))
	user = result.scalars().first()
	if user is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

	if req.clear:
		clear_user_force_logout(user.id)
	else:
		force_user_logout(user.id)

	return {
		"status": "ok",
		"username": user.username,
		"user_id": str(user.id),
		"force_logged_out": is_user_force_logged_out(user.id),
	}
