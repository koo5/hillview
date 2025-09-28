"""API routes for flagging photos for moderation."""
import logging
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import FlaggedPhoto, User
from auth import get_current_active_user
from rate_limiter import rate_limit_photo_operations

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flagged", tags=["flagged"])

# Request models
class FlagPhotoRequest(BaseModel):
	photo_source: str  # 'mapillary' or 'hillview'
	photo_id: str
	reason: Optional[str] = None
	extra_data: Optional[Dict] = None

class UnflagPhotoRequest(BaseModel):
	photo_source: str  # 'mapillary' or 'hillview'
	photo_id: str

class ResolveFlagRequest(BaseModel):
	flag_id: str  # The ID of the flagged photo record

# Response models
class FlagResponse(BaseModel):
	success: bool
	message: str
	already_flagged: bool = False

@router.post("/photos", response_model=FlagResponse)
async def flag_photo(
	request: Request,
	flag_request: FlagPhotoRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Flag a specific photo for moderation."""
	await rate_limit_photo_operations(request, current_user.id)

	# Validate photo_source
	if flag_request.photo_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="photo_source must be 'mapillary' or 'hillview'"
		)

	try:
		# Check if already flagged by this user
		existing_query = select(FlaggedPhoto).where(
			and_(
				FlaggedPhoto.flagging_user_id == current_user.id,
				FlaggedPhoto.photo_source == flag_request.photo_source,
				FlaggedPhoto.photo_id == flag_request.photo_id
			)
		)
		result = await db.execute(existing_query)
		existing = result.scalars().first()

		if existing:
			return FlagResponse(
				success=True,
				message="Photo was already flagged by you",
				already_flagged=True
			)

		# Create new flagged photo record
		flagged_photo = FlaggedPhoto(
			flagging_user_id=current_user.id,
			photo_source=flag_request.photo_source,
			photo_id=flag_request.photo_id,
			reason=flag_request.reason,
			extra_data=flag_request.extra_data
		)

		db.add(flagged_photo)
		await db.commit()

		log.info(f"User {current_user.id} flagged {flag_request.photo_source} photo {flag_request.photo_id}")

		return FlagResponse(
			success=True,
			message="Photo flagged successfully"
		)

	except Exception as e:
		log.error(f"Error flagging photo: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to flag photo"
		)

@router.delete("/photos", response_model=FlagResponse)
async def unflag_photo(
	request: Request,
	unflag_request: UnflagPhotoRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Remove a flag from a specific photo (only your own flag)."""
	await rate_limit_photo_operations(request, current_user.id)

	# Validate photo_source
	if unflag_request.photo_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="photo_source must be 'mapillary' or 'hillview'"
		)

	try:
		# Find the flagged photo record by this user
		query = select(FlaggedPhoto).where(
			and_(
				FlaggedPhoto.flagging_user_id == current_user.id,
				FlaggedPhoto.photo_source == unflag_request.photo_source,
				FlaggedPhoto.photo_id == unflag_request.photo_id
			)
		)
		result = await db.execute(query)
		flagged_photo = result.scalars().first()

		if not flagged_photo:
			return FlagResponse(
				success=True,
				message="Photo was not flagged by you",
				already_flagged=False
			)

		# Delete the flagged photo record
		await db.delete(flagged_photo)
		await db.commit()

		log.info(f"User {current_user.id} unflagged {unflag_request.photo_source} photo {unflag_request.photo_id}")

		return FlagResponse(
			success=True,
			message="Photo unflagged successfully"
		)

	except Exception as e:
		log.error(f"Error unflagging photo: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to unflag photo"
		)

@router.get("/photos")
async def list_flagged_photos(
	request: Request,
	photo_source: Optional[str] = None,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List photos flagged by the current user."""
	await rate_limit_photo_operations(request, current_user.id)

	try:
		query = select(FlaggedPhoto).where(FlaggedPhoto.flagging_user_id == current_user.id)

		if photo_source:
			if photo_source not in ['mapillary', 'hillview']:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="photo_source must be 'mapillary' or 'hillview'"
				)
			query = query.where(FlaggedPhoto.photo_source == photo_source)

		result = await db.execute(query.order_by(FlaggedPhoto.flagged_at.desc()))
		flagged_photos = result.scalars().all()

		return [{
			"photo_source": photo.photo_source,
			"photo_id": photo.photo_id,
			"flagged_at": photo.flagged_at,
			"reason": photo.reason,
			"resolved": photo.resolved,
			"resolved_at": photo.resolved_at
		} for photo in flagged_photos]

	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error listing flagged photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to list flagged photos"
		)

# Admin/moderator endpoint to see all flagged photos
@router.get("/photos/all")
async def list_all_flagged_photos(
	request: Request,
	photo_source: Optional[str] = None,
	limit: int = 50,
	offset: int = 0,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List all flagged photos (admin/moderator only)."""
	# Check if user has admin/moderator permissions
	if current_user.role not in ['ADMIN', 'MODERATOR']:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Insufficient permissions. Admin or moderator access required."
		)

	await rate_limit_photo_operations(request, current_user.id)

	try:
		query = select(FlaggedPhoto)

		if photo_source:
			if photo_source not in ['mapillary', 'hillview']:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="photo_source must be 'mapillary' or 'hillview'"
				)
			query = query.where(FlaggedPhoto.photo_source == photo_source)

		query = query.order_by(FlaggedPhoto.flagged_at.desc()).limit(limit).offset(offset)
		result = await db.execute(query)
		flagged_photos = result.scalars().all()

		return [{
			"id": photo.id,
			"flagging_user_id": photo.flagging_user_id,
			"photo_source": photo.photo_source,
			"photo_id": photo.photo_id,
			"flagged_at": photo.flagged_at,
			"reason": photo.reason,
			"extra_data": photo.extra_data,
			"resolved": photo.resolved,
			"resolved_at": photo.resolved_at,
			"resolved_by": photo.resolved_by
		} for photo in flagged_photos]

	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error listing all flagged photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to list flagged photos"
		)

@router.post("/resolve", response_model=FlagResponse)
async def resolve_flag(
	request: Request,
	resolve_request: ResolveFlagRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Mark a flagged photo as resolved (admin/moderator only)."""
	# Check if user has admin/moderator permissions
	if current_user.role not in ['ADMIN', 'MODERATOR']:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Insufficient permissions. Admin or moderator access required."
		)

	await rate_limit_photo_operations(request, current_user.id)

	try:
		# Find the flagged photo record
		query = select(FlaggedPhoto).where(FlaggedPhoto.id == resolve_request.flag_id)
		result = await db.execute(query)
		flagged_photo = result.scalars().first()

		if not flagged_photo:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Flagged photo not found"
			)

		if flagged_photo.resolved:
			return FlagResponse(
				success=True,
				message="Flag was already resolved"
			)

		# Mark as resolved
		flagged_photo.resolved = True
		flagged_photo.resolved_at = func.now()
		flagged_photo.resolved_by = current_user.id

		await db.commit()

		log.info(f"Admin {current_user.id} resolved flag {resolve_request.flag_id}")

		return FlagResponse(
			success=True,
			message="Flag resolved successfully"
		)

	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error resolving flag: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to resolve flag"
		)