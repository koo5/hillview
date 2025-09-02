"""API routes for hiding/unhiding photos and users."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import HiddenPhoto, HiddenUser, User
from auth import get_current_active_user
from rate_limiter import rate_limit_photo_operations

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hidden", tags=["hidden"])

# Request models
class HidePhotoRequest(BaseModel):
	photo_source: str  # 'mapillary' or 'hillview'
	photo_id: str
	reason: Optional[str] = None

class HideUserRequest(BaseModel):
	target_user_source: str  # 'mapillary' or 'hillview'
	target_user_id: str
	reason: Optional[str] = None

class UnhidePhotoRequest(BaseModel):
	photo_source: str  # 'mapillary' or 'hillview'
	photo_id: str

class UnhideUserRequest(BaseModel):
	target_user_source: str  # 'mapillary' or 'hillview'
	target_user_id: str

# Response models
class HideResponse(BaseModel):
	success: bool
	message: str
	already_hidden: bool = False

@router.post("/photos", response_model=HideResponse)
async def hide_photo(
	request: Request,
	hide_request: HidePhotoRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Hide a specific photo for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	# Validate photo_source
	if hide_request.photo_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="photo_source must be 'mapillary' or 'hillview'"
		)
	
	try:
		# Check if already hidden
		existing_query = select(HiddenPhoto).where(
			and_(
				HiddenPhoto.user_id == current_user.id,
				HiddenPhoto.photo_source == hide_request.photo_source,
				HiddenPhoto.photo_id == hide_request.photo_id
			)
		)
		result = await db.execute(existing_query)
		existing = result.scalars().first()
		
		if existing:
			return HideResponse(
				success=True,
				message="Photo was already hidden",
				already_hidden=True
			)
		
		# Create new hidden photo record
		hidden_photo = HiddenPhoto(
			user_id=current_user.id,
			photo_source=hide_request.photo_source,
			photo_id=hide_request.photo_id,
			reason=hide_request.reason
		)
		
		db.add(hidden_photo)
		await db.commit()
		
		log.info(f"User {current_user.id} hid {hide_request.photo_source} photo {hide_request.photo_id}")
		
		return HideResponse(
			success=True,
			message="Photo hidden successfully"
		)
		
	except Exception as e:
		log.error(f"Error hiding photo: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to hide photo"
		)

@router.post("/users", response_model=HideResponse)
async def hide_user(
	request: Request,
	hide_request: HideUserRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Hide all photos by a specific user for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	# Validate target_user_source
	if hide_request.target_user_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="target_user_source must be 'mapillary' or 'hillview'"
		)
	
	try:
		# Check if already hidden
		existing_query = select(HiddenUser).where(
			and_(
				HiddenUser.hiding_user_id == current_user.id,
				HiddenUser.target_user_source == hide_request.target_user_source,
				HiddenUser.target_user_id == hide_request.target_user_id
			)
		)
		result = await db.execute(existing_query)
		existing = result.scalars().first()
		
		if existing:
			return HideResponse(
				success=True,
				message="User was already hidden",
				already_hidden=True
			)
		
		# Create new hidden user record
		hidden_user = HiddenUser(
			hiding_user_id=current_user.id,
			target_user_source=hide_request.target_user_source,
			target_user_id=hide_request.target_user_id,
			reason=hide_request.reason
		)
		
		db.add(hidden_user)
		await db.commit()
		
		log.info(f"User {current_user.id} hid {hide_request.target_user_source} user {hide_request.target_user_id}")
		
		return HideResponse(
			success=True,
			message="User hidden successfully"
		)
		
	except Exception as e:
		log.error(f"Error hiding user: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to hide user"
		)

@router.delete("/photos", response_model=HideResponse)
async def unhide_photo(
	request: Request,
	unhide_request: UnhidePhotoRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Unhide a specific photo for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	# Validate photo_source
	if unhide_request.photo_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="photo_source must be 'mapillary' or 'hillview'"
		)
	
	try:
		# Find the hidden photo record
		query = select(HiddenPhoto).where(
			and_(
				HiddenPhoto.user_id == current_user.id,
				HiddenPhoto.photo_source == unhide_request.photo_source,
				HiddenPhoto.photo_id == unhide_request.photo_id
			)
		)
		result = await db.execute(query)
		hidden_photo = result.scalars().first()
		
		if not hidden_photo:
			return HideResponse(
				success=True,
				message="Photo was not hidden",
				already_hidden=False
			)
		
		# Delete the hidden photo record
		await db.delete(hidden_photo)
		await db.commit()
		
		log.info(f"User {current_user.id} unhid {unhide_request.photo_source} photo {unhide_request.photo_id}")
		
		return HideResponse(
			success=True,
			message="Photo unhidden successfully"
		)
		
	except Exception as e:
		log.error(f"Error unhiding photo: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to unhide photo"
		)

@router.delete("/users", response_model=HideResponse)
async def unhide_user(
	request: Request,
	unhide_request: UnhideUserRequest,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""Unhide all photos by a specific user for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	# Validate target_user_source
	if unhide_request.target_user_source not in ['mapillary', 'hillview']:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="target_user_source must be 'mapillary' or 'hillview'"
		)
	
	try:
		# Find the hidden user record
		query = select(HiddenUser).where(
			and_(
				HiddenUser.hiding_user_id == current_user.id,
				HiddenUser.target_user_source == unhide_request.target_user_source,
				HiddenUser.target_user_id == unhide_request.target_user_id
			)
		)
		result = await db.execute(query)
		hidden_user = result.scalars().first()
		
		if not hidden_user:
			return HideResponse(
				success=True,
				message="User was not hidden",
				already_hidden=False
			)
		
		# Delete the hidden user record
		await db.delete(hidden_user)
		await db.commit()
		
		log.info(f"User {current_user.id} unhid {unhide_request.target_user_source} user {unhide_request.target_user_id}")
		
		return HideResponse(
			success=True,
			message="User unhidden successfully"
		)
		
	except Exception as e:
		log.error(f"Error unhiding user: {str(e)}", exc_info=True)
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to unhide user"
		)

@router.get("/photos")
async def list_hidden_photos(
	request: Request,
	photo_source: Optional[str] = None,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List hidden photos for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	try:
		query = select(HiddenPhoto).where(HiddenPhoto.user_id == current_user.id)
		
		if photo_source:
			if photo_source not in ['mapillary', 'hillview']:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="photo_source must be 'mapillary' or 'hillview'"
				)
			query = query.where(HiddenPhoto.photo_source == photo_source)
		
		result = await db.execute(query.order_by(HiddenPhoto.hidden_at.desc()))
		hidden_photos = result.scalars().all()
		
		return [{
			"photo_source": photo.photo_source,
			"photo_id": photo.photo_id,
			"hidden_at": photo.hidden_at,
			"reason": photo.reason
		} for photo in hidden_photos]
		
	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error listing hidden photos: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to list hidden photos"
		)

@router.get("/users")
async def list_hidden_users(
	request: Request,
	target_user_source: Optional[str] = None,
	current_user: User = Depends(get_current_active_user),
	db: AsyncSession = Depends(get_db)
):
	"""List hidden users for the current user."""
	await rate_limit_photo_operations(request, current_user.id)
	
	try:
		query = select(HiddenUser).where(HiddenUser.hiding_user_id == current_user.id)
		
		if target_user_source:
			if target_user_source not in ['mapillary', 'hillview']:
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="target_user_source must be 'mapillary' or 'hillview'"
				)
			query = query.where(HiddenUser.target_user_source == target_user_source)
		
		result = await db.execute(query.order_by(HiddenUser.hidden_at.desc()))
		hidden_users = result.scalars().all()
		
		return [{
			"target_user_source": user.target_user_source,
			"target_user_id": user.target_user_id,
			"hidden_at": user.hidden_at,
			"reason": user.reason
		} for user in hidden_users]
		
	except HTTPException:
		raise
	except Exception as e:
		log.error(f"Error listing hidden users: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to list hidden users"
		)