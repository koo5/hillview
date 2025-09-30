"""Contact form routes for user messages."""
import logging
from typing import Optional
from pydantic import BaseModel, validator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import ContactMessage, User, UserRole
from auth import get_current_user_optional
from rate_limiter import general_rate_limiter, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact"])

# Request/Response models
class ContactMessageRequest(BaseModel):
    contact: str  # Email or other contact method
    message: str

    @validator('contact')
    def validate_contact(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError('Contact information must be at least 3 characters long')
        if len(v.strip()) > 500:
            raise ValueError('Contact information must be less than 500 characters')
        return v.strip()

    @validator('message')
    def validate_message(cls, v):
        if not v or len(v.strip()) < 10:
            raise ValueError('Message must be at least 10 characters long')
        if len(v.strip()) > 5000:
            raise ValueError('Message must be less than 5000 characters')
        return v.strip()

class ContactMessageResponse(BaseModel):
    success: bool
    message: str
    id: Optional[int] = None

def get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", "unknown")[:1000]  # Limit to 1000 chars

@router.post("/contact", response_model=ContactMessageResponse)
async def submit_contact_message(
    message_data: ContactMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Submit a contact message."""
    # Apply rate limiting
    await general_rate_limiter.enforce_rate_limit(request, 'general_api', current_user)

    try:
        # Get client information
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)

        # Create contact message
        contact_message = ContactMessage(
            contact_info=message_data.contact,
            message=message_data.message,
            user_id=current_user.id if current_user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            status='new'
        )

        db.add(contact_message)
        await db.commit()
        await db.refresh(contact_message)

        logger.info(f"Contact message submitted: ID={contact_message.id}, "
                   f"User={'logged_in' if current_user else 'guest'}, IP={ip_address}")

        return ContactMessageResponse(
            success=True,
            message="Your message has been sent successfully. We'll get back to you soon!",
            id=contact_message.id
        )

    except Exception as e:
        logger.error(f"Error submitting contact message: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit message. Please try again later."
        )

# Admin endpoint to view contact messages (for future use)
@router.get("/admin/contact/messages")
async def get_contact_messages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None
):
    """Get contact messages (admin only)."""
    # For now, just return empty - this would be implemented when admin interface is needed
    if not current_user or current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    query = select(ContactMessage).order_by(desc(ContactMessage.created_at))

    if status_filter:
        query = query.where(ContactMessage.status == status_filter)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    messages = result.scalars().all()

    return {
        "messages": [
            {
                "id": msg.id,
                "contact_info": msg.contact_info,
                "message": msg.message[:200] + "..." if len(msg.message) > 200 else msg.message,
                "user_id": msg.user_id,
                "created_at": msg.created_at,
                "status": msg.status,
                "ip_address": msg.ip_address
            }
            for msg in messages
        ],
        "total": len(messages)
    }