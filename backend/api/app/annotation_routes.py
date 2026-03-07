"""Photo annotation routes – simple free-for-all CRUD with versioned edits."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoAnnotation, User, HiddenUser
from auth import get_current_active_user, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    body: Optional[str] = None      # Human-readable text
    target: Optional[Dict[str, Any]] = None  # Annotorious selector JSON


class AnnotationResponse(BaseModel):
    id: str
    photo_id: str
    user_id: str
    body: Optional[str]
    target: Optional[Dict[str, Any]]
    is_current: bool
    superseded_by: Optional[str]
    created_at: Optional[str]
    event_type: str  # 'created' | 'updated' | 'deleted'
    owner_username: Optional[str] = None


def _serialize(ann: PhotoAnnotation, username: Optional[str] = None) -> AnnotationResponse:
    return AnnotationResponse(
        id=ann.id,
        photo_id=ann.photo_id,
        user_id=ann.user_id,
        body=ann.body,
        target=ann.target,
        is_current=ann.is_current,
        superseded_by=ann.superseded_by,
        created_at=ann.created_at.isoformat() if ann.created_at else None,
        event_type=ann.event_type,
        owner_username=username,
    )


@router.get("/photos/{photo_id}", response_model=List[AnnotationResponse])
async def list_annotations(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Return all current (non-deleted) annotations for a photo."""
    query = (
        select(PhotoAnnotation, User.username)
        .join(User, PhotoAnnotation.user_id == User.id)
        .where(
            and_(
                PhotoAnnotation.photo_id == photo_id,
                PhotoAnnotation.is_current == True,
                PhotoAnnotation.event_type != 'deleted',
            )
        )
        .order_by(PhotoAnnotation.created_at)
    )

    # Filter out annotations by users the current user has hidden
    if current_user:
        hidden_user_ids = select(HiddenUser.target_user_id).where(
            and_(
                HiddenUser.hiding_user_id == current_user.id,
                HiddenUser.target_user_source == 'hillview',
            )
        )
        query = query.where(PhotoAnnotation.user_id.notin_(hidden_user_ids))

    result = await db.execute(query)
    rows = result.all()
    return [_serialize(ann, username) for ann, username in rows]


@router.post("/photos/{photo_id}", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def create_annotation(
    photo_id: str,
    data: AnnotationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new annotation on a photo."""
    # Verify photo exists
    photo = await db.get(Photo, photo_id)
    if not photo or photo.deleted:
        raise HTTPException(status_code=404, detail="Photo not found")

    ann = PhotoAnnotation(
        photo_id=photo_id,
        user_id=current_user.id,
        body=data.body,
        target=data.target,
        is_current=True,
        event_type='created',
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    logger.info(f"Annotation {ann.id} created on photo {photo_id} by user {current_user.id}")
    return _serialize(ann, current_user.username)


@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: str,
    data: AnnotationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an annotation by superseding it with a new version.

    This operation creates a new annotation row and marks the old one as superseded,
    preserving the full edit history.  Any authenticated user may update any annotation
    (free-for-all model).  Future versions should restrict editing based on trust scores.
    """
    old = await db.get(PhotoAnnotation, annotation_id)
    if not old or old.event_type == 'deleted':
        raise HTTPException(status_code=404, detail="Annotation not found")
    if not old.is_current:
        raise HTTPException(status_code=409, detail="Annotation has already been superseded")

    # Create new version
    new_ann = PhotoAnnotation(
        photo_id=old.photo_id,
        user_id=current_user.id,
        body=data.body,
        target=data.target,
        is_current=True,
        event_type='updated',
    )
    db.add(new_ann)
    await db.flush()  # populate new_ann.id

    # Mark old version as superseded
    old.is_current = False
    old.superseded_by = new_ann.id
    await db.commit()
    await db.refresh(new_ann)
    logger.info(f"Annotation {old.id} superseded by {new_ann.id} by user {current_user.id}")
    return _serialize(new_ann, current_user.username)


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an annotation by creating a tombstone row in the supersede chain.

    The tombstone records the deleting user's ID, enabling per-user undo.
    Any authenticated user can delete any annotation (free-for-all model).
    Future versions should restrict deletion based on ownership and trust scores.
    """
    old = await db.get(PhotoAnnotation, annotation_id)
    if not old or old.event_type == 'deleted':
        raise HTTPException(status_code=404, detail="Annotation not found")
    if not old.is_current:
        raise HTTPException(status_code=409, detail="Annotation has already been superseded")

    # Create tombstone row — records who deleted and when
    tombstone = PhotoAnnotation(
        photo_id=old.photo_id,
        user_id=current_user.id,  # the DELETING user, not the original author
        body=None,
        target=None,
        is_current=True,
        event_type='deleted',
    )
    db.add(tombstone)
    await db.flush()

    # Mark old row as superseded by the tombstone
    old.is_current = False
    old.superseded_by = tombstone.id
    await db.commit()
    logger.info(f"Annotation {annotation_id} deleted (tombstone {tombstone.id}) by user {current_user.id}")
