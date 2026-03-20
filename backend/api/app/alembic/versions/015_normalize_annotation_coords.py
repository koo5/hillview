"""Normalize annotation coordinates from pixel space to [0,1] relative space.

Annotations were stored in absolute pixel coordinates (relative to the
full-size/pyramid image dimensions).  This breaks when the original image
dimensions are unavailable (e.g. Android photo worker strips pyramid metadata).

After this migration, selector coordinates are in [0,1] space where (0,0) is
top-left and (1,1) is bottom-right of the image.

Revision ID: 015_normalize_annotation_coords
Revises: 9d3532cfd1cf
Create Date: 2026-03-20 12:00:00.000000

"""
from typing import Sequence, Union
import json
import logging
import re

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = '015_normalize_annotation_coords'
down_revision: Union[str, None] = '9d3532cfd1cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_image_dims(sizes_json, photo_width, photo_height):
    """Extract the authoritative image dimensions for annotation mapping.

    Priority: pyramid dims > sizes.full dims > photo.width/height columns.
    Returns (width, height) or (None, None) if unavailable.
    """
    if sizes_json:
        sizes = sizes_json if isinstance(sizes_json, dict) else json.loads(sizes_json)
        full = sizes.get('full')
        if full:
            pyramid = full.get('pyramid')
            if pyramid and pyramid.get('width') and pyramid.get('height'):
                return pyramid['width'], pyramid['height']
            if full.get('width') and full.get('height'):
                return full['width'], full['height']
    if photo_width and photo_height:
        return photo_width, photo_height
    return None, None


def _transform_target(target, img_w, img_h, normalize=True):
    """Transform annotation target coordinates.

    If normalize=True: divide by image dims (pixel → [0,1])
    If normalize=False: multiply by image dims ([0,1] → pixel)

    Returns modified target dict (mutates in place for efficiency).
    """
    if not target or not img_w or not img_h:
        return target

    selector = target.get('selector')
    if not selector:
        return target

    # Handle array of selectors
    selectors = selector if isinstance(selector, list) else [selector]

    for sel in selectors:
        if sel.get('type') == 'RECTANGLE' and sel.get('geometry'):
            g = sel['geometry']
            if normalize:
                g['x'] = g['x'] / img_w
                g['y'] = g['y'] / img_h
                g['w'] = g['w'] / img_w
                g['h'] = g['h'] / img_h
            else:
                g['x'] = g['x'] * img_w
                g['y'] = g['y'] * img_h
                g['w'] = g['w'] * img_w
                g['h'] = g['h'] * img_h

        elif sel.get('type') == 'FragmentSelector' or (isinstance(sel.get('value'), str) and 'xywh=' in sel.get('value', '')):
            value = sel.get('value', '')
            match = re.match(r'xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)', value)
            if match:
                x, y, w, h = float(match[1]), float(match[2]), float(match[3]), float(match[4])
                if normalize:
                    x, y, w, h = x / img_w, y / img_h, w / img_w, h / img_h
                else:
                    x, y, w, h = x * img_w, y * img_h, w * img_w, h * img_h
                sel['value'] = f'xywh=pixel:{x},{y},{w},{h}'

    # If selector was not a list, put the single item back
    if not isinstance(selector, list):
        target['selector'] = selectors[0]

    return target


def _migrate_annotations(normalize=True):
    """Shared logic for upgrade (normalize) and downgrade (denormalize)."""
    conn = op.get_bind()

    # Fetch all annotations with their photo's dimension info
    rows = conn.execute(sa.text("""
        SELECT pa.id, pa.target, p.sizes, p.width, p.height
        FROM photo_annotations pa
        JOIN photos p ON pa.photo_id = p.id
        WHERE pa.target IS NOT NULL
    """)).fetchall()

    direction = "normalizing" if normalize else "denormalizing"
    logger.info(f"{direction} {len(rows)} annotation(s)")

    transformed = 0
    skipped = 0
    for row in rows:
        ann_id = row[0]
        target = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else None
        sizes = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else None
        photo_w = row[3]
        photo_h = row[4]

        if not target:
            continue

        img_w, img_h = _get_image_dims(sizes, photo_w, photo_h)
        if not img_w or not img_h:
            logger.warning(f"Skipping annotation {ann_id}: no image dimensions available")
            skipped += 1
            continue

        _transform_target(target, img_w, img_h, normalize=normalize)

        conn.execute(
            sa.text("UPDATE photo_annotations SET target = :target WHERE id = :id"),
            {"target": json.dumps(target), "id": ann_id}
        )
        transformed += 1

    logger.info(f"{direction} complete: {transformed} transformed, {skipped} skipped")


def upgrade() -> None:
    _migrate_annotations(normalize=True)


def downgrade() -> None:
    _migrate_annotations(normalize=False)
