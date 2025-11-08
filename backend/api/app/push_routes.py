"""Push notification routes for client registration and notification management."""
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import httpx

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, and_, update, delete

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import PushRegistration, Notification, User, UserPublicKey
from common.security_utils import verify_ecdsa_signature, generate_client_key_id
from auth import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["push"])

# Helper functions
async def validate_client_key_ownership(
	client_key_id: str,
	current_user: User,
	db: AsyncSession
) -> None:
	"""
	Validate that the client_key_id belongs to the current user.
	Raises HTTPException if key belongs to different user or is not found.

	Returns special error code CLIENT_KEY_CONFLICT (409) if key belongs to different user,
	which tells the client to generate a new key.
	"""
	# Check if this client_key_id is registered to any user
	result = await db.execute(
		select(UserPublicKey).where(
			UserPublicKey.key_id == client_key_id,
			UserPublicKey.is_active == True
		)
	)
	existing_key = result.scalar_one_or_none()

	if existing_key:
		if existing_key.user_id != current_user.id:
			# Key belongs to different user - client needs to generate new key
			logger.warning(f"Client key {client_key_id} belongs to user {existing_key.user_id}, "
						  f"but used by user {current_user.id}")
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="CLIENT_KEY_CONFLICT: This client key belongs to a different user. "
					   "Please generate a new client key."
			)
	# If key not found, that's OK - user just hasn't registered it yet

# Request/Response models
class PushRegistrationRequest(BaseModel):
	push_endpoint: str = Field(..., min_length=10)  # Allow FCM endpoints (fcm:token) and HTTP URLs
	distributor_package: Optional[str] = None
	timestamp: int = Field(...)  # Unix timestamp for replay protection
	client_signature: str = Field(..., min_length=1)  # Base64 ECDSA signature
	public_key_pem: str = Field(..., min_length=100)  # PEM-formatted ECDSA public key
	key_created_at: str = Field(...)  # ISO timestamp when key was created

class PushRegistrationResponse(BaseModel):
	success: bool
	message: str

class NotificationRequest(BaseModel):
	user_id: str
	type: str = Field(..., max_length=50)
	title: str
	body: str
	action_type: Optional[str] = Field(None, max_length=50)
	action_data: Optional[Dict[str, Any]] = None
	expires_at: Optional[datetime] = None

class NotificationCreationResponse(BaseModel):
	success: bool
	message: str
	id: int

class MarkNotificationsReadRequest(BaseModel):
	notification_ids: List[int]

class NotificationResponse(BaseModel):
	id: int
	type: str
	title: str
	body: str
	action_type: Optional[str]
	action_data: Optional[Dict[str, Any]]
	read_at: Optional[datetime]
	created_at: datetime
	expires_at: Optional[datetime]

class NotificationListResponse(BaseModel):
	notifications: List[NotificationResponse]
	total_count: int
	unread_count: int

class UnreadCountResponse(BaseModel):
	unread_count: int


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


async def send_push_to_user(user_id: str, db: AsyncSession):
	"""Send push notification poke to all registered devices for a user."""
	# Get all client_key_ids for the user, then find push registrations for those keys
	user_keys_query = select(UserPublicKey.key_id).where(
		UserPublicKey.user_id == user_id,
		UserPublicKey.is_active == True
	)
	user_keys_result = await db.execute(user_keys_query)
	client_key_ids = [row[0] for row in user_keys_result.fetchall()]

	if not client_key_ids:
		logger.info(f"No active client keys found for user {user_id}")
		return

	# Get push registrations for all user's client keys
	registrations_query = select(PushRegistration).where(
		PushRegistration.client_key_id.in_(client_key_ids)
	)
	registrations_result = await db.execute(registrations_query)
	registrations = registrations_result.scalars().all()

	if not registrations:
		logger.info(f"No push registrations found for user {user_id} (checked {len(client_key_ids)} client keys)")
		return

	# Send "smart poke" to each registered endpoint
	async with httpx.AsyncClient(timeout=30.0) as client:
		for registration in registrations:
			try:
				response = await client.post(
					registration.push_endpoint,
					json={
						"content": "activity_update",  # Generic wake-up signal
						"encrypted": False
					},
					headers={"Content-Type": "application/json"}
				)

				if response.status_code == 200:
					logger.info(f"Push sent successfully to {registration.client_key_id}")
				else:
					logger.warning(f"Push failed for {registration.client_key_id}: {response.status_code}")

			except Exception as e:
				logger.error(f"Error sending push to {registration.client_key_id}: {e}")


# API Routes
@router.post("/push/register", response_model=PushRegistrationResponse)
async def register_push(
	request: PushRegistrationRequest,
	db: AsyncSession = Depends(get_db),
	current_user: Optional[User] = Depends(get_current_user_optional)
):
	"""Register a push endpoint for a client (authentication optional for rate limiting)."""
	# Calculate client_key_id from public key (prevents impersonation)
	client_key_id = generate_client_key_id(request.public_key_pem)

	logger.info(f"📨 Push registration request received:")
	logger.info(f"  calculated_client_key_id: {client_key_id}")
	logger.info(f"  push_endpoint: {request.push_endpoint[:50]}...")
	logger.info(f"  distributor_package: {request.distributor_package}")
	logger.info(f"  timestamp: {request.timestamp}")
	logger.info(f"  key_created_at: {request.key_created_at}")
	logger.info(f"  current_user: {current_user.id if current_user else 'None'}")

	# Check timestamp for replay protection (allow 5 minute window)
	current_time = datetime.utcnow().timestamp() * 1000  # Convert to milliseconds
	time_diff = abs(current_time - request.timestamp)
	logger.info(f"⏰ Timestamp validation: current={current_time}, request={request.timestamp}, diff={time_diff}ms")

	if time_diff > 300000:  # 5 minutes in milliseconds
		logger.error(f"❌ Timestamp validation failed: difference {time_diff}ms > 300000ms")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Request timestamp too old or too far in future"
		)

	# Verify client signature
	message_data = {
		"push_endpoint": request.push_endpoint,
		"timestamp": request.timestamp
	}
	if request.distributor_package:
		message_data["distributor_package"] = request.distributor_package

	logger.info(f"🔐 Verifying client signature:")
	logger.info(f"  message_data: {message_data}")
	logger.info(f"  signature (first 50 chars): {request.client_signature[:50]}...")
	logger.info(f"  public_key_pem (first 100 chars): {request.public_key_pem[:100]}...")

	signature_valid = verify_ecdsa_signature(request.client_signature, request.public_key_pem, message_data)
	logger.info(f"🔐 Signature verification result: {signature_valid}")

	if not signature_valid:
		logger.error(f"❌ Client signature verification failed for client_key_id: {client_key_id}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Invalid client signature"
		)

	# If user is authenticated, validate that the client_key_id belongs to them
	if current_user:
		await validate_client_key_ownership(client_key_id, current_user, db)

	# Apply rate limiting with optional user context (better limits for authenticated users)
	# TODO: Implement actual rate limiting based on current_user presence

	# Check if registration already exists for this client_key_id
	logger.info(f"💾 Checking for existing registration for client_key_id: {client_key_id}")
	existing_query = select(PushRegistration).where(
		PushRegistration.client_key_id == client_key_id
	)
	result = await db.execute(existing_query)
	existing = result.scalar_one_or_none()

	if existing:
		logger.info(f"💾 Found existing registration, updating...")
		# Update existing registration
		existing.push_endpoint = request.push_endpoint
		existing.distributor_package = request.distributor_package
		existing.updated_at = datetime.utcnow()
		message = "Push registration updated"
	else:
		logger.info(f"💾 Creating new registration...")
		# Create new registration
		registration = PushRegistration(
			client_key_id=client_key_id,
			push_endpoint=request.push_endpoint,
			distributor_package=request.distributor_package
		)
		db.add(registration)
		message = "Push registration created"

	logger.info(f"💾 Committing to database...")
	await db.commit()
	user_info = f", user {current_user.id}" if current_user else " (anonymous)"
	logger.info(f"✅ Push registration for client {client_key_id}{user_info}: {message}")
	return PushRegistrationResponse(success=True, message=message)


@router.delete("/push/unregister/{client_key_id}", response_model=PushRegistrationResponse)
async def unregister_push(
	client_key_id: str,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""Unregister a push endpoint for the specified client."""
	# Validate that the client_key_id belongs to the current user
	await validate_client_key_ownership(client_key_id, current_user, db)

	# Find the push registration for this client key
	query = select(PushRegistration).where(
		PushRegistration.client_key_id == client_key_id
	)
	result = await db.execute(query)
	registration = result.scalar_one_or_none()

	if not registration:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Push registration not found for this client key"
		)

	await db.delete(registration)
	await db.commit()

	logger.info(f"Unregistered push endpoint for client {client_key_id}, user {current_user.id}")
	return PushRegistrationResponse(success=True, message="Push registration removed")


@router.get("/notifications/recent", response_model=NotificationListResponse)
async def get_recent_notifications(
	limit: int = 20,
	offset: int = 0,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""Get recent notifications for the current user."""
	# Get notifications
	notifications_query = select(Notification).where(
		Notification.user_id == current_user.id
	).order_by(desc(Notification.created_at)).limit(limit).offset(offset)

	result = await db.execute(notifications_query)
	notifications = result.scalars().all()

	# Get total count
	total_query = select(func.count(Notification.id)).where(
		Notification.user_id == current_user.id
	)
	total_result = await db.execute(total_query)
	total_count = total_result.scalar()

	# Get unread count
	unread_query = select(func.count(Notification.id)).where(
		and_(
			Notification.user_id == current_user.id,
			Notification.read_at.is_(None)
		)
	)
	unread_result = await db.execute(unread_query)
	unread_count = unread_result.scalar()

	# Convert to response format
	notification_responses = [
		NotificationResponse(
			id=n.id,
			type=n.type,
			title=n.title,
			body=n.body,
			action_type=n.action_type,
			action_data=n.action_data,
			read_at=n.read_at,
			created_at=n.created_at,
			expires_at=n.expires_at
		)
		for n in notifications
	]

	return NotificationListResponse(
		notifications=notification_responses,
		total_count=total_count,
		unread_count=unread_count
	)


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""Get unread notification count for the current user."""
	query = select(func.count(Notification.id)).where(
		and_(
			Notification.user_id == current_user.id,
			Notification.read_at.is_(None)
		)
	)
	result = await db.execute(query)
	count = result.scalar()
	return UnreadCountResponse(unread_count=count)


@router.put("/notifications/read", response_model=PushRegistrationResponse)
async def mark_notifications_read(
	request: MarkNotificationsReadRequest,
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	"""Mark specified notifications as read."""
	if not request.notification_ids:
		return PushRegistrationResponse(success=True, message="No notifications to mark as read")

	stmt = update(Notification).where(
		and_(
			Notification.id.in_(request.notification_ids),
			Notification.user_id == current_user.id,
			Notification.read_at.is_(None)  # Only update unread notifications
		)
	).values(read_at=datetime.utcnow())

	result = await db.execute(stmt)
	await db.commit()

	count = result.rowcount
	logger.info(f"Marked {count} notifications as read for user {current_user.id}")

	return PushRegistrationResponse(
		success=True,
		message=f"Marked {count} notifications as read"
	)


# Internal/admin endpoints
@router.post("/internal/notifications/create", response_model=NotificationCreationResponse)
async def create_notification(
	request: NotificationRequest,
	db: AsyncSession = Depends(get_db)
):
	"""Create a notification for a user (internal/admin use)."""
	# Use the core function
	notification_id = await create_notification_for_user(
		db=db,
		user_id=request.user_id,
		notification_type=request.type,
		title=request.title,
		body=request.body,
		action_type=request.action_type,
		action_data=request.action_data,
		expires_at=request.expires_at
	)

	return NotificationCreationResponse(
		success=True,
		message="Notification created",
		id=notification_id
	)


@router.post("/internal/notifications/cleanup", response_model=PushRegistrationResponse)
async def cleanup_expired_notifications(
	db: AsyncSession = Depends(get_db)
):
	"""Clean up expired notifications (internal/admin use)."""
	stmt = delete(Notification).where(
		and_(
			Notification.expires_at.is_not(None),
			Notification.expires_at < datetime.utcnow()
		)
	)

	result = await db.execute(stmt)
	await db.commit()

	count = result.rowcount
	logger.info(f"Cleaned up {count} expired notifications")

	return PushRegistrationResponse(
		success=True,
		message=f"Cleaned up {count} expired notifications"
	)
