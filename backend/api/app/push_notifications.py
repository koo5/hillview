from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import httpx, logging

from common.models import PushRegistration, Notification, User, UserPublicKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, and_, update, delete
from fcm_push import send_fcm_push, is_fcm_configured

logger = logging.getLogger(__name__)

# Core notification functions (for use by other parts of the app)

async def create_notification_for_any(
	db: AsyncSession,
	id: dict,
	notification_type: str,
	title: str,
	body: str,
	action_type: Optional[str] = None,
	action_data: Optional[Dict[str, Any]] = None,
	expires_at: Optional[datetime] = None
) -> int:
	if id['type'] == 'user':
		return await create_notification_for_user(
			db=db,
			user_id=id['id'],
			notification_type=notification_type,
			title=title,
			body=body,
			action_type=action_type,
			action_data=action_data,
			expires_at=expires_at
		)
	elif id['type'] == 'client':
		return await create_notification_for_client(
			db=db,
			client_key_id=id['id'],
			notification_type=notification_type,
			title=title,
			body=body,
			action_type=action_type,
			action_data=action_data,
			expires_at=expires_at
		)
	else:
		raise ValueError(f"Unknown id type: {id['type']}")



async def create_notification_for_user(
	db: AsyncSession,
	user_id: str,
	notification_type: str,
	title: str,
	body: str,
	action_type: Optional[str] = None,
	action_data: Optional[Dict[str, Any]] = None,
	expires_at: Optional[datetime] = None
) -> int:
	"""Create a notification for a user and send push. Returns notification ID."""
	# Create notification
	notification = Notification(
		user_id=user_id,
		type=notification_type,
		title=title,
		body=body,
		action_type=action_type,
		action_data=action_data,
		expires_at=expires_at
	)

	db.add(notification)
	await db.commit()
	await db.refresh(notification)

	# Send push notification to user's registered devices
	await send_push_to_user(user_id, db)

	#logger.debug(f"Created notification for user {user_id}: {title}")
	return notification.id


async def create_notification_for_client(
	db: AsyncSession,
	client_key_id: str,
	notification_type: str,
	title: str,
	body: str,
	action_type: Optional[str] = None,
	action_data: Optional[Dict[str, Any]] = None,
	expires_at: Optional[datetime] = None
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

	# Create notification
	notification = Notification(
		client_key_id=client_key_id,
		type=notification_type,
		title=title,
		body=body,
		action_type=action_type,
		action_data=action_data,
		expires_at=expires_at
	)

	db.add(notification)
	await db.commit()
	await db.refresh(notification)

	# Send push notification to this specific client
	await send_push_to_client(client_key_id, db)

	#logger.debug(f"Created notification for client {client_key_id}: {title}")
	return notification.id


async def send_push_to_user(user_id: str, db: AsyncSession):
	"""Send push notification poke to all registered devices for a user."""
	# Get all client_key_ids for the user
	user_keys_query = select(UserPublicKey.key_id).where(
		UserPublicKey.user_id == user_id,
		UserPublicKey.is_active == True
	)
	user_keys_result = await db.execute(user_keys_query)
	client_key_ids = [row[0] for row in user_keys_result.fetchall()]

	if not client_key_ids:
		#logger.debug(f"No active client keys found for user {user_id}")
		return

	# Send push to each client_key_id (reuse existing logic)
	for client_key_id in client_key_ids:
		await send_push_to_client(client_key_id, db)


async def send_push_to_client(client_key_id: str, db: AsyncSession):
	"""Send push notification poke to a specific client device."""
	# Get push registration for this client key
	registration_query = select(PushRegistration).where(
		PushRegistration.client_key_id == client_key_id
	)
	result = await db.execute(registration_query)
	registration = result.scalar_one_or_none()

	if not registration:
		#logger.info(f"No push registration found for client {client_key_id}")
		return

	# Send "smart poke" to the registered endpoint
	async with httpx.AsyncClient(timeout=30.0) as client:
		try:
			# Check if this is an FCM token or UnifiedPush URL
			if registration.push_endpoint.startswith('fcm:'):
				# FCM token - use Firebase Cloud Messaging
				#logger.info(f"FCM token detected for {client_key_id}: {registration.push_endpoint[:20]}...")

				if not is_fcm_configured():
					logger.warning(f"FCM not configured")
					return

				# Send via FCM
				success = await send_fcm_push(
					fcm_token=registration.push_endpoint,
					title="Hillview",
					body="New activity",
					data={
						'type': 'activity_update',
						'content': 'activity_update'
					}
				)

				if success:
					logger.info(f"FCM sent successfully to {client_key_id}")
					return True
				else:
					logger.warning(f"FCM failed for {client_key_id}")
					return


			# UnifiedPush HTTP endpoint
			response = await client.post(
				registration.push_endpoint,
				json={
					"content": "activity_update",  # Generic wake-up signal
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
	notification_type: str,
	title: str,
	body: str,
	action_type: Optional[str] = None,
	action_data: Optional[Dict[str, Any]] = None,
	expires_at: Optional[datetime] = None
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
		await create_notification_for_user(
			db=db,
			user_id=user_id,
			notification_type=notification_type,
			title=title,
			body=body,
			action_type=action_type,
			action_data=action_data,
			expires_at=expires_at
		)
		user_count += 1

	# 2. Send to all anonymous clients (push registrations not associated with any user)
	# Find client_key_ids that exist in push_registrations but not in user_public_keys
	anonymous_clients_query = select(PushRegistration.client_key_id).where(
		~PushRegistration.client_key_id.in_(select(UserPublicKey.key_id))
	)
	anonymous_result = await db.execute(anonymous_clients_query)
	anonymous_client_ids = [row[0] for row in anonymous_result.fetchall()]

	for client_key_id in anonymous_client_ids:
		try:
			await create_notification_for_client(
				db=db,
				client_key_id=client_key_id,
				notification_type=notification_type,
				title=title,
				body=body,
				action_type=action_type,
				action_data=action_data,
				expires_at=expires_at
			)
			client_count += 1
		except ValueError as e:
			# Client might have been unregistered between query and notification creation
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
	"""Send an activity broadcast notification to all users and all anonymous clients (not associated with any user).
	filter out users who got notified in the last 12 hours.
	"""
	args = dict(
		notification_type = 'activity_broadcast',
		title = 'New photos uploaded',
		body = 'New photos have been uploaded to Hillview. Check them out!',
		action_type = 'open_activity',
		action_data = None,
		expires_at = None
	)

	user_count = 0
	client_count = 0

	# get all active users who have not been notified in the last 12 hours
	twelve_hours_ago = datetime.utcnow() - timedelta(hours=12)
	activity_users_query = select(User.id).where(
		and_(
			User.is_active == True,
			~User.id.in_(
				select(Notification.user_id).where(
					Notification.type == 'activity_broadcast',
					Notification.created_at >= twelve_hours_ago
				)
			)
		)
	)
	activity_users_result = await db.execute(activity_users_query)

	user_ids = [{'type':'user', 'id': row[0]} for row in activity_users_result.fetchall() if row[0] != activity_originator_user_id]
	user_count = len(user_ids)

	# 2. Send to all anonymous clients (push registrations not associated with any user)
	anonymous_clients_query = select(PushRegistration.client_key_id).where(
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
	anonymous_result = await db.execute(anonymous_clients_query)
	anonymous_ids = [{'type':'client', 'id': row[0]} for row in anonymous_result.fetchall()]
	client_count = len(anonymous_ids)

	ids = user_ids + anonymous_ids

	sent_count = 0
	for aid in ids:
		try:
			await create_notification_for_any(
				db=db,
				id=aid,
				**args
			)
			sent_count += 1
		except ValueError as e:
			# Client might have been unregistered between query and notification creation
			logger.warning(f"Failed to create notification for {str(aid)}: {e}")

	logger.info(f"Broadcast notification sent: {sent_count}/{len(ids)} total ({user_count} users, {client_count} anonymous clients)")
