"""Admin-only routes: aggregated dashboard signals for the admin UI.

Mounted at /api/admin and gated by require_admin() (see auth.py). The user's
role is surfaced to the client via /auth/me (UserOut.role), so the frontend can
show/hide the Admin menu item and poll the notification counts below.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import (
	AnnotationModeration, ContactMessage, FlaggedPhoto, Photo, PhotoAnnotation, PhotoModerationAudit, User,
)
from auth import require_admin, require_moderator
from push_notifications import create_notification_for_user

ANNOTATION_EVENT_TYPES = ('created', 'updated', 'deleted')


def _role_str(role) -> Optional[str]:
	"""Normalize a role (UserRole enum or stored string) to a lowercase string."""
	if role is None:
		return None
	return str(getattr(role, 'value', role)).lower()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# The lifecycle a contact message moves through. 'new' is the only "unhandled"
# state, so moving a message off 'new' is what clears it from the badge count.
CONTACT_STATUSES = ('new', 'read', 'replied', 'archived')


def _serialize_contact_message(msg: ContactMessage, username: Optional[str] = None) -> dict:
	return {
		"id": msg.id,
		"contact_info": msg.contact_info,
		"message": msg.message,
		"user_id": msg.user_id,
		# The sender's account username (for registered senders), so the admin sees
		# who it really is, not just the contact string they typed.
		"username": username,
		"created_at": msg.created_at,
		"status": msg.status,
		"admin_notes": msg.admin_notes,
		"replied_at": msg.replied_at,
		"replied_by": msg.replied_by,
		"ip_address": msg.ip_address,
	}


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


@router.get("/contact/messages")
async def list_contact_messages(
	limit: int = 50,
	offset: int = 0,
	status_filter: Optional[str] = None,
	current_user: User = Depends(require_admin()),
	db: AsyncSession = Depends(get_db),
):
	"""List contact messages, newest first. Optionally filter by status."""
	# Outer-join the sender's account (guests have no user_id) to surface the real
	# username alongside the typed contact string.
	query = (
		select(ContactMessage, User.username)
		.join(User, ContactMessage.user_id == User.id, isouter=True)
		.order_by(desc(ContactMessage.created_at))
	)
	if status_filter:
		query = query.where(ContactMessage.status == status_filter)
	query = query.offset(max(0, offset)).limit(max(1, min(limit, 200)))

	result = await db.execute(query)
	rows = result.all()
	return {
		"messages": [_serialize_contact_message(m, username) for m, username in rows],
		"total": len(rows),
	}


class ContactMessageUpdate(BaseModel):
	status: Optional[str] = None
	admin_notes: Optional[str] = None


@router.patch("/contact/messages/{message_id}")
async def update_contact_message(
	message_id: int,
	payload: ContactMessageUpdate,
	current_user: User = Depends(require_admin()),
	db: AsyncSession = Depends(get_db),
):
	"""Update a contact message's status and/or admin notes.

	Moving the status off 'new' is how the admin handles a message, which also
	decrements the badge count (see get_admin_notifications). Setting the status
	to 'replied' stamps who replied and when.
	"""
	msg = await db.get(ContactMessage, message_id)
	if msg is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact message not found")

	if payload.status is not None:
		if payload.status not in CONTACT_STATUSES:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid status. Allowed: {', '.join(CONTACT_STATUSES)}",
			)
		msg.status = payload.status
		if payload.status == 'replied':
			msg.replied_at = datetime.now(timezone.utc)
			msg.replied_by = current_user.id

	if payload.admin_notes is not None:
		msg.admin_notes = payload.admin_notes

	await db.commit()
	await db.refresh(msg)
	return _serialize_contact_message(msg)


@router.get("/annotation-events")
async def list_annotation_events(
	limit: int = 50,
	offset: int = 0,
	photo_id: Optional[str] = None,
	user_id: Optional[str] = None,
	event_type: Optional[str] = None,
	current_user: User = Depends(require_moderator()),
	db: AsyncSession = Depends(get_db),
):
	"""Reverse-chronological log of every annotation event (create/edit/delete).

	Each row in photo_annotations IS an event: 'created'/'updated' carry the new
	body and name the author; 'deleted' is a tombstone naming the deleter. The
	full edit chain is reconstructable via superseded_by. Read-only for now;
	per-event undo lands in a later pass (see docs/todo/event-audit-undo.md).
	"""
	if event_type is not None and event_type not in ANNOTATION_EVENT_TYPES:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"Invalid event_type. Allowed: {', '.join(ANNOTATION_EVENT_TYPES)}",
		)

	# Joins for context:
	#  - Photo: deep-link + zoomview bounds (coords/width).
	#  - Pred (predecessor): the row THIS event superseded → its body is the "old
	#    text" replaced/removed by this event.
	#  - Succ (successor) + SuccUser: the row that superseded THIS event → what
	#    version replaced it, and by whom.
	Pred = aliased(PhotoAnnotation)
	Succ = aliased(PhotoAnnotation)
	SuccUser = aliased(User)
	query = (
		select(
			PhotoAnnotation, User.username, User.role,
			ST_Y(Photo.geometry).label('lat'),
			ST_X(Photo.geometry).label('lon'),
			Photo.compass_angle.label('bearing'),
			Photo.width.label('width'),
			Pred.body.label('prev_body'),
			Succ.id.label('succ_id'),
			Succ.event_type.label('succ_type'),
			SuccUser.username.label('succ_username'),
		)
		.join(User, PhotoAnnotation.user_id == User.id)
		.join(Photo, PhotoAnnotation.photo_id == Photo.id, isouter=True)
		.join(Pred, Pred.superseded_by == PhotoAnnotation.id, isouter=True)
		.join(Succ, PhotoAnnotation.superseded_by == Succ.id, isouter=True)
		.join(SuccUser, Succ.user_id == SuccUser.id, isouter=True)
		.order_by(desc(PhotoAnnotation.created_at))
	)
	if photo_id:
		query = query.where(PhotoAnnotation.photo_id == photo_id)
	if user_id:
		query = query.where(PhotoAnnotation.user_id == user_id)
	if event_type:
		query = query.where(PhotoAnnotation.event_type == event_type)
	query = query.offset(max(0, offset)).limit(max(1, min(limit, 200)))

	result = await db.execute(query)
	rows = result.all()

	# Moderation reasons for the visible events, from the annotation_moderation
	# sidecar: an event may BE a moderator undo (result_event_id) or the target
	# that was reverted (target_event_id).
	event_ids = [r[0].id for r in rows]
	by_result: dict = {}
	by_target: dict = {}
	if event_ids:
		mod_rows = (await db.execute(
			select(AnnotationModeration).where(
				or_(
					AnnotationModeration.result_event_id.in_(event_ids),
					AnnotationModeration.target_event_id.in_(event_ids),
				)
			)
		)).scalars().all()
		for m in mod_rows:
			if m.result_event_id:
				by_result[m.result_event_id] = m
			if m.target_event_id:
				by_target[m.target_event_id] = m

	def _mod(m) -> Optional[dict]:
		if m is None:
			return None
		return {"action": m.action, "reason": m.reason, "moderator_username": m.moderator_username}

	return {
		"events": [
			{
				"id": ann.id,
				"photo_id": ann.photo_id,
				"user_id": ann.user_id,
				"username": username,
				# Normalized lowercase role of the acting user, so the UI can flag
				# events by ordinary (non-admin/moderator) users for scrutiny.
				"actor_role": str(getattr(role, 'value', role)).lower() if role is not None else None,
				"event_type": ann.event_type,
				"body": ann.body,
				"target": ann.target,
				"is_current": ann.is_current,
				"superseded_by": ann.superseded_by,
				"created_at": ann.created_at,
				# Photo context for deep-linking (null if the photo row is gone).
				"photo_lat": lat,
				"photo_lon": lon,
				"photo_bearing": bearing,
				"photo_width": width,
				# Chain context.
				"prev_body": prev_body,  # the text this event replaced/removed
				"superseded_by_event": (
					{"id": succ_id, "event_type": succ_type, "username": succ_username}
					if succ_id else None
				),
				# Moderation context (from the sidecar).
				"moderation": _mod(by_result.get(ann.id)),  # this event IS a moderator undo
				"reverted": _mod(by_target.get(ann.id)),    # this event was reverted by a moderator
			}
			for ann, username, role, lat, lon, bearing, width, prev_body, succ_id, succ_type, succ_username in rows
		],
	}


class AnnotationUndoRequest(BaseModel):
	reason: Optional[str] = None


def _undo_message(action: str, reason: Optional[str]) -> tuple:
	"""(title, body) for the notification sent to the affected author."""
	titles = {
		'undo_create': 'An annotation you added was removed',
		'undo_update': 'An edit you made was reverted',
		'undo_delete': 'An annotation you deleted was restored',
	}
	defaults = {
		'undo_create': 'A moderator removed an annotation you created.',
		'undo_update': 'A moderator reverted an edit you made to an annotation.',
		'undo_delete': 'A moderator restored an annotation you had deleted.',
	}
	title = titles.get(action, 'An annotation of yours was moderated')
	clean = reason.strip() if reason and reason.strip() else None
	body = clean or defaults.get(action, 'A moderator reverted one of your annotations.')
	return title, body


@router.post("/annotation-events/{event_id}/undo")
async def undo_annotation_event(
	event_id: str,
	payload: AnnotationUndoRequest,
	current_user: User = Depends(require_moderator()),
	db: AsyncSession = Depends(get_db),
):
	"""Undo an annotation event by appending a new event that restores prior state.

	Only the current tip of a chain (is_current) can be undone; the append-only
	history is preserved. Writes an annotation_moderation record and notifies the
	affected author with the optional reason. See docs/todo/event-audit-undo.md.
	"""
	# Snapshot the acting moderator up front (avoids post-commit attribute reloads).
	moderator_id = current_user.id
	moderator_username = current_user.username
	moderator_role = _role_str(current_user.role)

	target = await db.get(PhotoAnnotation, event_id)
	if target is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation event not found")
	if not target.is_current:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="Only the current version of a chain can be undone",
		)

	photo_id = target.photo_id

	# The row this tip superseded (its predecessor) — the content to restore.
	pred = (await db.execute(
		select(PhotoAnnotation).where(PhotoAnnotation.superseded_by == target.id)
	)).scalars().first()

	# Subject: the author whose work is being reverted.
	subject = await db.get(User, target.user_id)
	subject_id = subject.id if subject else None
	subject_username = subject.username if subject else None

	et = target.event_type
	if et == 'created':
		action = 'undo_create'
		new = PhotoAnnotation(photo_id=photo_id, user_id=moderator_id,
			body=None, target=None, is_current=True, event_type='deleted')
	elif et == 'updated':
		if pred is None:
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No prior version to restore")
		action = 'undo_update'
		new = PhotoAnnotation(photo_id=photo_id, user_id=moderator_id,
			body=pred.body, target=pred.target, is_current=True, event_type='updated')
	elif et == 'deleted':
		if pred is None:
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No prior version to restore")
		action = 'undo_delete'
		new = PhotoAnnotation(photo_id=photo_id, user_id=moderator_id,
			body=pred.body, target=pred.target, is_current=True, event_type='updated')
	else:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot undo event_type '{et}'")

	db.add(new)
	await db.flush()  # populate new.id
	result_event_id = new.id

	target.is_current = False
	target.superseded_by = result_event_id

	mod = AnnotationModeration(
		action=action,
		target_event_id=event_id,
		result_event_id=result_event_id,
		photo_id=photo_id,
		moderator_user_id=moderator_id,
		moderator_username=moderator_username,
		moderator_role=moderator_role,
		subject_user_id=subject_id,
		subject_username=subject_username,
		reason=(payload.reason.strip() if payload.reason and payload.reason.strip() else None),
	)
	db.add(mod)
	await db.commit()

	# Notify the affected author (best-effort; the undo is already durable). Never
	# notify a moderator undoing their own event.
	notified = False
	if subject_id and subject_id != moderator_id:
		title, body = _undo_message(action, payload.reason)
		route = f"/photo/hillview-{photo_id}" if photo_id else None
		try:
			notif_id = await create_notification_for_user(db, subject_id, {
				'type': 'annotation_reverted', 'title': title, 'body': body, 'route': route,
			})
			mod.notification_id = notif_id
			await db.commit()
			notified = True
		except Exception as e:
			logger.warning(f"undo notify failed for user {subject_id}: {e}")

	return {
		"undone_event_id": event_id,
		"result_event_id": result_event_id,
		"action": action,
		"notified": notified,
	}


def _activity_summary(kind: str, event_type: str, count: int, ctx: dict) -> str:
	"""Compose the (actor-less) action text; the UI prepends the actor name."""
	if kind == 'contact':
		return 'sent a contact message' if count == 1 else f'sent {count} contact messages'
	if kind == 'moderation':
		verb = 'deleted' if event_type == 'delete' else event_type
		return f"{verb} {ctx['owner']}'s photo" if count == 1 else f'{verb} {count} photos'
	if kind == 'annotation':
		# event_type is already past tense: created / updated / deleted
		return f'{event_type} an annotation' if count == 1 else f'{event_type} {count} annotations'
	if kind == 'flag':
		return f"flagged a {ctx['source']} photo" if count == 1 else f'flagged {count} photos'
	if kind == 'upload':
		label = ctx.get('label') or 'a photo'
		return f'uploaded {label}' if count == 1 else f'uploaded {count} photos'
	return ''


def _activity_link(kind: str, count: int, ctx: dict) -> Optional[str]:
	if kind == 'contact':
		return '/admin/contact'
	if kind == 'moderation':
		return '/admin/audit'
	if kind == 'annotation':
		return '/admin/annotations'
	if kind == 'flag':
		return '/admin/flags'
	if kind == 'upload':
		# A single upload deep-links to the photo; a collapsed burst goes to the feed.
		return f"/photo/{ctx['uid']}" if count == 1 and ctx.get('uid') else '/activity'
	return None


@router.get("/activity")
async def admin_activity(
	limit: int = 50,
	current_user: User = Depends(require_admin()),
	db: AsyncSession = Depends(get_db),
):
	"""Merged, reverse-chronological feed of server activity for the dashboard.

	Merges the latest rows from each source at query time (no denormalized feed
	table), then squashes consecutive runs of the same actor + kind + event_type
	into a single counted row — so a burst of uploads reads as "uploaded 20
	photos" rather than 20 lines.
	"""
	n = max(1, min(limit, 200))
	raw: list[dict] = []

	# Contact messages (submitter may be a guest → outer join to User).
	rows = (await db.execute(
		select(ContactMessage, User.username, User.role)
		.join(User, ContactMessage.user_id == User.id, isouter=True)
		.order_by(desc(ContactMessage.created_at)).limit(n)
	)).all()
	for m, username, role in rows:
		raw.append({'kind': 'contact', 'id': str(m.id), 'at': m.created_at,
			'actor': username or m.contact_info, 'actor_role': _role_str(role),
			'event_type': m.status, 'ctx': {'contact_info': m.contact_info}})

	# Moderation actions (actor/owner already snapshotted on the audit row).
	rows = (await db.execute(
		select(PhotoModerationAudit).order_by(desc(PhotoModerationAudit.created_at)).limit(n)
	)).scalars().all()
	for a in rows:
		raw.append({'kind': 'moderation', 'id': a.id, 'at': a.created_at,
			'actor': a.actor_username or a.actor_user_id, 'actor_role': _role_str(a.actor_role),
			'event_type': a.action, 'ctx': {'owner': a.photo_owner_username or 'someone'}})

	# Annotation events.
	rows = (await db.execute(
		select(PhotoAnnotation, User.username, User.role)
		.join(User, PhotoAnnotation.user_id == User.id)
		.order_by(desc(PhotoAnnotation.created_at)).limit(n)
	)).all()
	for ann, username, role in rows:
		raw.append({'kind': 'annotation', 'id': ann.id, 'at': ann.created_at,
			'actor': username, 'actor_role': _role_str(role),
			'event_type': ann.event_type, 'ctx': {}})

	# Flags (flagging user may be gone → outer join).
	rows = (await db.execute(
		select(FlaggedPhoto, User.username, User.role)
		.join(User, FlaggedPhoto.flagging_user_id == User.id, isouter=True)
		.order_by(desc(FlaggedPhoto.flagged_at)).limit(n)
	)).all()
	for f, username, role in rows:
		raw.append({'kind': 'flag', 'id': f.id, 'at': f.flagged_at,
			'actor': username or 'someone', 'actor_role': _role_str(role),
			'event_type': 'resolved' if f.resolved else 'open', 'ctx': {'source': f.photo_source}})

	# Uploads.
	rows = (await db.execute(
		select(Photo, User.username, User.role)
		.join(User, Photo.owner_id == User.id, isouter=True)
		.where(Photo.deleted.is_(False))
		.order_by(desc(Photo.uploaded_at)).limit(n)
	)).all()
	for p, username, role in rows:
		raw.append({'kind': 'upload', 'id': p.id, 'at': p.uploaded_at,
			'actor': username or 'someone', 'actor_role': _role_str(role),
			'event_type': 'created', 'ctx': {'label': p.title or p.original_filename, 'uid': f'hillview-{p.id}'}})

	# Newest first (guard against a stray NULL timestamp).
	raw.sort(key=lambda e: e['at'].timestamp() if e['at'] else 0.0, reverse=True)

	# Squash consecutive same-actor/kind/event_type runs into counted rows.
	groups: list[dict] = []
	for e in raw:
		last = groups[-1] if groups else None
		if last and last['kind'] == e['kind'] and last['actor'] == e['actor'] and last['event_type'] == e['event_type']:
			last['count'] += 1
			last['since'] = e['at']  # oldest so far in the run
		else:
			groups.append({**e, 'count': 1, 'since': e['at']})

	return {
		"events": [
			{
				"kind": g['kind'],
				"id": g['id'],
				"at": g['at'],
				"since": g['since'],
				"actor": g['actor'],
				"actor_role": g['actor_role'],
				"event_type": g['event_type'],
				"count": g['count'],
				"summary": _activity_summary(g['kind'], g['event_type'], g['count'], g['ctx']),
				"link": _activity_link(g['kind'], g['count'], g['ctx']),
			}
			for g in groups[:n]
		],
	}
