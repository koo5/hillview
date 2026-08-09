"""Contact form routes for user messages."""
import logging
from typing import Optional
from pydantic import BaseModel, field_validator

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import ContactMessage, User
from auth import get_current_user_optional
from rate_limiter import general_rate_limiter, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["contact"])

# Request/Response models
class ContactMessageRequest(BaseModel):
    contact: str  # Email or other contact method
    message: str

    @field_validator('contact')
    @classmethod
    def validate_contact(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError('Contact information must be at least 3 characters long')
        if len(v.strip()) > 500:
            raise ValueError('Contact information must be less than 500 characters')
        return v.strip()

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
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

# Admin listing/management of contact messages lives in admin_routes.py
# (GET/PATCH /api/admin/contact/messages), gated by the shared require_admin dep.