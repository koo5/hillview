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
from common.models import PushRegistration, Notification, User
from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["push"])

# Request/Response models
class PushRegistrationRequest(BaseModel):
    client_key_id: str = Field(..., min_length=1, max_length=255)
    push_endpoint: str = Field(..., min_length=10, pattern=r'^https?://')
    distributor_package: Optional[str] = None

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
    # Get all push registrations for the user
    query = select(PushRegistration).where(PushRegistration.user_id == user_id)
    result = await db.execute(query)
    registrations = result.scalars().all()

    if not registrations:
        logger.info(f"No push registrations found for user {user_id}")
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register a push endpoint for the current user's client."""
    # Check if registration already exists for this client_key_id
    existing_query = select(PushRegistration).where(
        PushRegistration.client_key_id == request.client_key_id
    )
    result = await db.execute(existing_query)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing registration
        existing.user_id = current_user.id
        existing.push_endpoint = request.push_endpoint
        existing.distributor_package = request.distributor_package
        existing.updated_at = datetime.utcnow()
        message = "Push registration updated"
    else:
        # Create new registration
        registration = PushRegistration(
            client_key_id=request.client_key_id,
            user_id=current_user.id,
            push_endpoint=request.push_endpoint,
            distributor_package=request.distributor_package
        )
        db.add(registration)
        message = "Push registration created"

    await db.commit()
    logger.info(f"Push registration for client {request.client_key_id}, user {current_user.id}: {message}")
    return PushRegistrationResponse(success=True, message=message)


@router.delete("/push/unregister/{client_key_id}", response_model=PushRegistrationResponse)
async def unregister_push(
    client_key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unregister a push endpoint for the specified client."""
    query = select(PushRegistration).where(
        and_(
            PushRegistration.client_key_id == client_key_id,
            PushRegistration.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    registration = result.scalar_one_or_none()

    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push registration not found"
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