"""Admin-only routes: aggregated dashboard signals for the admin UI.

Mounted at /api/admin and gated by require_admin() (see auth.py). The user's
role is surfaced to the client via /auth/me (UserOut.role), so the frontend can
show/hide the Admin menu item and poll the notification counts below.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import ContactMessage, FlaggedPhoto, User
from auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/notifications")
async def get_admin_notifications(
	current_user: User = Depends(require_admin()),
	db: AsyncSession = Depends(get_db),
):
	"""Counts of actionable, unhandled admin items for the menu badge.

	Derived from durable state rather than a per-admin "seen" cursor, so the
	badge clears itself when the underlying items are handled -- a contact
	message moved off 'new', a flag resolved -- not merely when they are viewed.
	Annotation events are intentionally omitted for now: they have no "handled"
	state and would need a seen-cursor, which we defer.
	"""
	contact_new = await db.scalar(
		select(func.count()).select_from(ContactMessage).where(ContactMessage.status == 'new')
	) or 0
	flags_open = await db.scalar(
		select(func.count()).select_from(FlaggedPhoto).where(FlaggedPhoto.resolved.is_(False))
	) or 0

	return {
		"contact_new": contact_new,
		"flags_open": flags_open,
		"total": contact_new + flags_open,
	}
