"""Photo annotation routes – simple free-for-all CRUD with versioned edits."""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geoalchemy2.functions import ST_X, ST_Y

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoAnnotation, User, HiddenUser
from auth import get_current_active_user, get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


# Bodies that carry no real information: '?' is the default for a freshly drawn
# annotation, 'oops' marks accidental ones. Kept in sync with frontend
# firstAnnotationText() in photoDisplay.ts.
PLACEHOLDER_BODIES = ('', '?', 'oops')


def effective_annotation_count_subquery():
    """Return a subquery giving the count of effective annotations per photo.

    Effective = current, non-deleted, and carrying real text (NULL, empty and
    placeholder bodies are excluded).

    Columns: photo_id, annotation_count.
    """
    return (
        select(
            PhotoAnnotation.photo_id,
            func.count(PhotoAnnotation.id).label('annotation_count')
        )
        .where(
            and_(
                PhotoAnnotation.is_current == True,
                PhotoAnnotation.event_type != 'deleted',
                func.lower(func.trim(func.coalesce(PhotoAnnotation.body, ''))).notin_(PLACEHOLDER_BODIES),
            )
        )
        .group_by(PhotoAnnotation.photo_id)
        .subquery('effective_annotations')
    )


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


@router.get("/contributions")
async def my_contributions(
    limit: int = 500,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's own annotation contributions, one row per chain, collapsed to
    the chain's CURRENT tip.

    This is the non-privileged, user-facing counterpart of the moderator
    /admin/annotation-events log. It is deliberately *judicious*: it never
    exposes an intermediate version of a chain, only the final surviving one.
    When someone else has edited or removed the caller's annotation, showing the
    replacer's text would be unsafe (it could itself be spam that was later
    reverted), so we surface only the current tip's body — the same text that is
    live and public on the photo — and we do NOT reveal who changed it.

    Chains are reconstructed by walking superseded_by forward from every event
    the caller authored (create / edit / delete) to the tip. This is the seed of
    a broader contributions dashboard and, eventually, payout logic: `standing`
    counts the chains whose current live version is still the caller's own work.
    """
    me = current_user.id
    PA = PhotoAnnotation

    # Recursive walk: seed from every event I authored, then follow superseded_by
    # forward hop-by-hop to the chain tip (the row with superseded_by IS NULL).
    # Carrying seed_event_type through the walk lets us report which roles I
    # played in each chain (created / updated / deleted) once grouped by tip.
    seed = (
        select(
            PA.id.label('seed_id'),
            PA.event_type.label('seed_event_type'),
            PA.id.label('cur_id'),
            PA.superseded_by.label('superseded_by'),
        )
        .where(PA.user_id == me)
        .cte(name='contrib_walk', recursive=True)
    )
    nxt = aliased(PA)
    walk = seed.union_all(
        select(
            seed.c.seed_id,
            seed.c.seed_event_type,
            nxt.id,
            nxt.superseded_by,
        ).select_from(seed.join(nxt, nxt.id == seed.c.superseded_by))
    )

    # Collapse to one row per chain tip, gathering the distinct roles I played.
    tips = (
        select(
            walk.c.cur_id.label('tip_id'),
            func.array_agg(walk.c.seed_event_type.distinct()).label('my_roles'),
        )
        .where(walk.c.superseded_by.is_(None))
        .group_by(walk.c.cur_id)
        .subquery('contrib_tips')
    )

    Tip = aliased(PA)
    query = (
        select(
            Tip,
            tips.c.my_roles,
            ST_Y(Photo.geometry).label('lat'),
            ST_X(Photo.geometry).label('lon'),
            Photo.compass_angle.label('bearing'),
            Photo.width.label('width'),
        )
        .join(tips, tips.c.tip_id == Tip.id)
        .join(Photo, Tip.photo_id == Photo.id, isouter=True)
        # Drop still-live placeholders (unfinished '?' boxes carry no contribution);
        # keep removed chains, which tell the "your annotation was deleted" story.
        .where(
            or_(
                Tip.event_type == 'deleted',
                func.lower(func.trim(func.coalesce(Tip.body, ''))).notin_(PLACEHOLDER_BODIES),
            )
        )
        .order_by(desc(Tip.created_at))
        .limit(max(1, min(limit, 1000)))
    )
    rows = (await db.execute(query)).all()

    contributions = []
    standing = changed = removed = 0
    photo_ids = set()
    for tip, my_roles, lat, lon, bearing, width in rows:
        is_removed = tip.event_type == 'deleted'
        mine_is_current = tip.user_id == me
        if is_removed:
            removed += 1
        elif mine_is_current:
            standing += 1
        else:
            changed += 1
        photo_ids.add(tip.photo_id)
        contributions.append({
            "chain_tip_id": tip.id,
            "photo_id": tip.photo_id,
            "my_roles": sorted(my_roles) if my_roles else [],
            "status": "removed" if is_removed else "live",
            # Whether the current live version is still my own work — the signal a
            # future payout would credit.
            "mine_is_current": mine_is_current,
            # The final surviving version's body: safe to show (it is the public,
            # live text). Null when the chain now ends in a deletion.
            "current_body": None if is_removed else tip.body,
            "created_at": tip.created_at,
            # Photo context for a zoom-to-spot deep link (null if the photo is gone).
            "photo_lat": lat,
            "photo_lon": lon,
            "photo_bearing": bearing,
            "photo_width": width,
            "target": None if is_removed else tip.target,
        })

    return {
        "contributions": contributions,
        "summary": {
            "total": len(contributions),
            "standing": standing,          # live, and still my own work
            "changed_by_others": changed,  # live, but someone else's edit now holds
            "removed": removed,            # chain ends in a deletion
            "photos": len(photo_ids),
        },
        "truncated": len(rows) >= min(limit, 1000),
    }


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
