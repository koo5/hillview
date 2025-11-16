from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import httpx, logging

from common.models import PushRegistration, Notification, User, UserPublicKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, and_, update, delete
from fcm_push import send_fcm_push, is_fcm_configured

logger = logging.getLogger(__name__)

# Core notification functions (for use by other parts of the app)
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

	logger.info(f"Created notification for user {user_id}: {title}")
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

	logger.info(f"Created notification for client {client_key_id}: {title}")
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
		logger.info(f"No active client keys found for user {user_id}")
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
		logger.info(f"No push registration found for client {client_key_id}")
		return

	# Send "smart poke" to the registered endpoint
	async with httpx.AsyncClient(timeout=30.0) as client:
		try:
			# Check if this is an FCM token or UnifiedPush URL
			if registration.push_endpoint.startswith('fcm:'):
				# FCM token - use Firebase Cloud Messaging
				logger.info(f"FCM token detected for {client_key_id}: {registration.push_endpoint[:20]}...")

				if not is_fcm_configured():
					logger.warning(f"FCM not configured - skipping FCM token {client_key_id}")
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
				logger.info(f"Push sent successfully to {client_key_id}")
			else:
				logger.warning(f"Push failed for {client_key_id}: {response.status_code}")

		except Exception as e:
			logger.error(f"Error sending push to {client_key_id}: {e}")

