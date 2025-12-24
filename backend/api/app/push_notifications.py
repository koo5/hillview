from typing import List, Optional, Dict, Any, TypedDict
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import asyncio
import httpx, logging

from common.models import PushRegistration, Notification, User, UserPublicKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, and_, update, delete
from fcm_push import send_fcm_push, send_fcm_batch, is_fcm_configured

logger = logging.getLogger(__name__)


class NotificationDict(TypedDict, total=False):
	"""Notification data structure passed through the notification system."""
	type: str           # 'activity_broadcast', 'photo_liked', etc.
	title: str
	body: str
	route: Optional[str]  # '/activity', '/photos/123', etc. (stored in action_data column)
	expires_at: Optional[datetime]


# Core notification functions (for use by other parts of the app)

async def create_notification_for_any(
	db: AsyncSession,
	recipient: dict,  # {'type': 'user'|'client', 'id': ...}
	notification: NotificationDict
) -> int:
	"""Create a notification for a user or client device."""
	if recipient['type'] == 'user':
		return await create_notification_for_user(db, recipient['id'], notification)
	elif recipient['type'] == 'client':
		return await create_notification_for_client(db, recipient['id'], notification)
	else:
		raise ValueError(f"Unknown recipient type: {recipient['type']}")



async def create_notification_for_user(
	db: AsyncSession,
	user_id: str,
	notif: NotificationDict
) -> int:
	"""Create a notification for a user and send push. Returns notification ID."""
	# Create notification record
	notification = Notification(
		user_id=user_id,
		type=notif['type'],
		title=notif['title'],
		body=notif['body'],
		action_type=None,  # deprecated
		action_data=notif.get('route'),  # route stored in action_data column
		expires_at=notif.get('expires_at')
	)

	db.add(notification)
	await db.commit()
	await db.refresh(notification)

	# Send push notification to user's registered devices
	await send_push_to_user(user_id, db, notif)

	return notification.id


async def create_notification_for_client(
	db: AsyncSession,
	client_key_id: str,
	notif: NotificationDict
) -> int:
	"""Create a notification for a client device and send push. Returns notification ID."""
	# Verify the client_key_id exists in push_registrations
	registration_query = select(PushRegistration).where(
		PushRegistration.client_key_id == client_key_id
	)
	result = await db.execute(registration_query)
	registration = result.scalar_one_or_none()

	if not registration:
		raise ValueError(f"No push registration found for client_key_id: {client_key_id}")

	# Create notification record
	notification = Notification(
		client_key_id=client_key_id,
		type=notif['type'],
		title=notif['title'],
		body=notif['body'],
		action_type=None,  # deprecated
		action_data=notif.get('route'),  # route stored in action_data column
		expires_at=notif.get('expires_at')
	)

	db.add(notification)
	await db.commit()
	await db.refresh(notification)

	# Send push notification to this specific client
	await send_push_to_client(client_key_id, db, notif)

	return notification.id


async def send_push_to_user(user_id: str, db: AsyncSession, notif: NotificationDict):
	"""Send push notification to all registered devices for a user."""
	# Get all client_key_ids for the user
	user_keys_query = select(UserPublicKey.key_id).where(
		UserPublicKey.user_id == user_id,
		UserPublicKey.is_active == True
	)
	user_keys_result = await db.execute(user_keys_query)
	client_key_ids = [row[0] for row in user_keys_result.fetchall()]

	if not client_key_ids:
		return

	# Send push to each client_key_id
	for client_key_id in client_key_ids:
		await send_push_to_client(client_key_id, db, notif)


async def send_push_to_client(client_key_id: str, db: AsyncSession, notif: NotificationDict):
	"""Send push notification to a specific client device."""
	# Get push registration for this client key
	registration_query = select(PushRegistration).where(
		PushRegistration.client_key_id == client_key_id
	)
	result = await db.execute(registration_query)
	registration = result.scalar_one_or_none()

	if not registration:
		return

	# Send push to the registered endpoint
	async with httpx.AsyncClient(timeout=30.0) as client:
		try:
			# Check if this is an FCM token or UnifiedPush URL
			if registration.push_endpoint.startswith('fcm:'):
				if not is_fcm_configured():
					logger.warning(f"FCM not configured")
					return

				# Send via FCM with notification content and route
				success = await send_fcm_push(
					fcm_token=registration.push_endpoint,
					title=notif['title'],
					body=notif['body'],
					route=notif.get('route')
				)

				if success:
					logger.info(f"FCM sent successfully to {client_key_id}")
					return True
				else:
					logger.warning(f"FCM failed for {client_key_id}")
					return

			# UnifiedPush HTTP endpoint - send poke to trigger fetch
			response = await client.post(
				registration.push_endpoint,
				json={
					"content": "activity_update",
					"encrypted": False
				},
				headers={"Content-Type": "application/json"}
			)

			if response.status_code == 200:
				logger.info(f"UnifiedPush sent successfully to {client_key_id}")
				return True
			else:
				logger.warning(f"UnifiedPush failed for {client_key_id}: {response.status_code}")
				return

		except Exception as e:
			logger.error(f"Error sending push to {client_key_id}: {e}")


async def send_broadcast_notification(
	db: AsyncSession,
	notification: NotificationDict
) -> Dict[str, int]:
	"""Send a notification to all users and all anonymous clients (not associated with any user).

	Returns dict with counts: {'user_notifications': int, 'client_notifications': int, 'total': int}
	"""
	user_count = 0
	client_count = 0

	# 1. Send to all active users
	users_query = select(User.id).where(User.is_active == True)
	users_result = await db.execute(users_query)
	user_ids = [row[0] for row in users_result.fetchall()]

	for user_id in user_ids:
		await create_notification_for_user(db, user_id, notification)
		user_count += 1

	# 2. Send to all anonymous clients (push registrations not associated with any user)
	anonymous_clients_query = select(PushRegistration.client_key_id).where(
		~PushRegistration.client_key_id.in_(select(UserPublicKey.key_id))
	)
	anonymous_result = await db.execute(anonymous_clients_query)
	anonymous_client_ids = [row[0] for row in anonymous_result.fetchall()]

	for client_key_id in anonymous_client_ids:
		try:
			await create_notification_for_client(db, client_key_id, notification)
			client_count += 1
		except ValueError as e:
			logger.warning(f"Failed to create notification for anonymous client {client_key_id}: {e}")

	total_count = user_count + client_count
	logger.info(f"Broadcast notification sent: {user_count} users, {client_count} anonymous clients, {total_count} total")

	return {
		'user_notifications': user_count,
		'client_notifications': client_count,
		'total': total_count
	}





async def send_activity_broadcast_notification(
	db: AsyncSession,
	activity_originator_user_id: str
):
	"""Send an activity broadcast notification to all users and all anonymous clients.
	Filters out users who got notified in the last 12 hours.
	Uses batch sending for FCM efficiency.
	"""
	notification = {
		'type': 'activity_broadcast',
		'title': 'New photos uploaded',
		'body': 'New photos have been uploaded to Hillview. Check them out!',
		'route': '/activity',
	}

	twelve_hours_ago = datetime.utcnow() - timedelta(hours=12)

	# Get eligible users with their push endpoints in one query
	user_endpoints_query = select(
		User.id,
		PushRegistration.push_endpoint
	).join(
		UserPublicKey, User.id == UserPublicKey.user_id
	).join(
		PushRegistration, UserPublicKey.key_id == PushRegistration.client_key_id
	).where(
		and_(
			User.is_active == True,
			UserPublicKey.is_active == True,
			User.id != activity_originator_user_id,
			~User.id.in_(
				select(Notification.user_id).where(
					Notification.type == 'activity_broadcast',
					Notification.created_at >= twelve_hours_ago
				)
			)
		)
	)
	user_endpoints_result = await db.execute(user_endpoints_query)
	user_endpoints = user_endpoints_result.fetchall()

	# Get anonymous client endpoints
	anon_endpoints_query = select(
		PushRegistration.client_key_id,
		PushRegistration.push_endpoint
	).where(
		and_(
			~PushRegistration.client_key_id.in_(select(UserPublicKey.key_id)),
			~PushRegistration.client_key_id.in_(
				select(Notification.client_key_id).where(
					Notification.type == 'activity_broadcast',
					Notification.created_at >= twelve_hours_ago
				)
			)
		)
	)
	anon_endpoints_result = await db.execute(anon_endpoints_query)
	anon_endpoints = anon_endpoints_result.fetchall()

	# Create notification records for users (deduplicate by user_id)
	seen_user_ids = set()
	for user_id, _ in user_endpoints:
		if user_id not in seen_user_ids:
			seen_user_ids.add(user_id)
			db.add(Notification(
				user_id=user_id,
				type=notification['type'],
				title=notification['title'],
				body=notification['body'],
				action_data=notification.get('route'),
			))

	# Create notification records for anonymous clients
	for client_key_id, _ in anon_endpoints:
		db.add(Notification(
			client_key_id=client_key_id,
			type=notification['type'],
			title=notification['title'],
			body=notification['body'],
			action_data=notification.get('route'),
		))

	await db.commit()

	# Separate FCM and UnifiedPush endpoints
	fcm_tokens = []
	unified_push_endpoints = []

	for _, endpoint in user_endpoints:
		if endpoint.startswith('fcm:'):
			fcm_tokens.append(endpoint)
		else:
			unified_push_endpoints.append(endpoint)

	for _, endpoint in anon_endpoints:
		if endpoint.startswith('fcm:'):
			fcm_tokens.append(endpoint)
		else:
			unified_push_endpoints.append(endpoint)

	# Batch send FCM
	fcm_result = {'success': 0, 'failure': 0}
	if fcm_tokens:
		fcm_result = await send_fcm_batch(
			fcm_tokens,
			title=notification['title'],
			body=notification['body'],
			route=notification.get('route')
		)

	# Send UnifiedPush concurrently
	unified_push_results = await send_unified_push_batch(unified_push_endpoints)

	logger.info(
		f"Broadcast sent: {len(seen_user_ids)} users, {len(anon_endpoints)} clients | "
		f"FCM: {fcm_result['success']}/{len(fcm_tokens)} | "
		f"UnifiedPush: {unified_push_results['success']}/{len(unified_push_endpoints)}"
	)


async def send_unified_push_batch(endpoints: List[str]) -> Dict[str, int]:
	"""Send UnifiedPush pokes to multiple endpoints concurrently."""
	if not endpoints:
		return {'success': 0, 'failure': 0}

	async def send_one(endpoint: str) -> bool:
		try:
			async with httpx.AsyncClient(timeout=10.0) as client:
				response = await client.post(
					endpoint,
					json={"content": "activity_update", "encrypted": False},
					headers={"Content-Type": "application/json"}
				)
				return response.status_code == 200
		except Exception as e:
			logger.warning(f"UnifiedPush failed for {endpoint[:30]}...: {e}")
			return False

	results = await asyncio.gather(*[send_one(ep) for ep in endpoints], return_exceptions=True)
	success = sum(1 for r in results if r is True)
	return {'success': success, 'failure': len(endpoints) - success}
