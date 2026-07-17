"""Admin: review and apply enrichment graduation packages.

Mounted at /api/admin/graduation, gated by require_admin(). Reads packages the
enrichment workbench dropped into the incoming dir; previews each op with three
bodies — what the workbench expected (precondition), what Hillview currently has,
and what it proposes — alongside the annotation's photo for OSD review; applies
selected ops by superseding the current annotation head under the admin account.

Conflicts (the annotation changed since export) are NOT auto-skipped: the UI
warns and shows all three versions, and the operator may still apply — the
workbench body then supersedes the current head, preserving its latest geometry.
"""
import logging
import os
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import Photo, PhotoAnnotation, User
from auth import require_admin
import graduation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/graduation", tags=["admin", "graduation"])

MAX_CHAIN = 64  # supersede-chain follow cap (cycle/runaway guard)


async def _resolve_head(db: AsyncSession, ann_id: str):
    """Follow the supersede chain from ann_id to the current head.
    → (head_row | None, found). found=False when the id doesn't exist at all."""
    row = await db.get(PhotoAnnotation, ann_id)
    if row is None:
        return None, False
    seen = 0
    while not row.is_current and row.superseded_by and seen < MAX_CHAIN:
        nxt = await db.get(PhotoAnnotation, row.superseded_by)
        if nxt is None:
            break
        row, seen = nxt, seen + 1
    return row, True


@router.get("/packages")
async def list_packages(current_user: User = Depends(require_admin())):
    return {"packages": graduation.list_packages()}


@router.get("/packages/{filename}")
async def preview_package(filename: str,
                          current_user: User = Depends(require_admin()),
                          db: AsyncSession = Depends(get_db)):
    try:
        pkg = graduation.read_package(filename)
    except FileNotFoundError:
        raise HTTPException(404, "package not found")
    except Exception as e:
        raise HTTPException(422, f"invalid package: {e}")

    prov = graduation.parse_provenance(pkg.get("provenance_trig"))
    ops_out = []
    for op in pkg.get("ops", []):
        ann_id = op.get("annotation_id")
        precondition = (op.get("precondition") or {}).get("body")
        suggested = op.get("body")
        head, found = await _resolve_head(db, ann_id)
        deleted = bool(found and head and head.event_type == 'deleted')
        current_body = head.body if (found and head and not deleted) else None
        status = ("deleted" if deleted
                  else graduation.classify(precondition, current_body, suggested, found))

        photo_osd = target = None
        if found and head and not deleted:
            target = head.target
            photo = await db.get(Photo, head.photo_id)
            if photo:
                photo_osd = graduation.photo_osd(photo)

        ops_out.append({
            "annotation_id": ann_id,
            "current_annotation_id": head.id if (found and head) else None,
            "photo_id": op.get("photo_id"),
            "precondition_body": precondition,
            "current_body": current_body,
            "suggested_body": suggested,
            "summary": op.get("summary"),
            "status": status,
            "target": target,
            "photo": photo_osd,
            "facts": [{"iri": f, **prov.get(f, {})} for f in op.get("facts", [])],
        })

    return {
        "filename": filename,
        "package": pkg.get("package"),
        "source": pkg.get("source"),
        "created_at": pkg.get("created_at"),
        "counts": pkg.get("counts"),
        "provenance_available": bool(prov),
        "ops": ops_out,
    }


class ApplyRequest(BaseModel):
    annotation_ids: list[str]  # the op annotation_ids the operator chose to apply


@router.post("/packages/{filename}/apply")
async def apply_package(filename: str, req: ApplyRequest,
                        current_user: User = Depends(require_admin()),
                        db: AsyncSession = Depends(get_db)):
    try:
        pkg = graduation.read_package(filename)
    except FileNotFoundError:
        raise HTTPException(404, "package not found")
    except Exception as e:
        raise HTTPException(422, f"invalid package: {e}")

    wanted = set(req.annotation_ids)
    results = []
    for op in pkg.get("ops", []):
        ann_id = op.get("annotation_id")
        if ann_id not in wanted:
            continue
        suggested = op.get("body")
        precondition = (op.get("precondition") or {}).get("body")
        head, found = await _resolve_head(db, ann_id)
        if not found or head is None or head.event_type == 'deleted':
            results.append({"annotation_id": ann_id, "applied": False, "reason": "missing"})
            continue
        if head.body == suggested:
            results.append({"annotation_id": ann_id, "applied": False,
                            "reason": "already_applied", "current_annotation_id": head.id})
            continue
        # supersede the current head with a new version (body-only op: keep the
        # head's latest geometry). Conflicts already surfaced in the preview —
        # the operator chose to apply, so we do, over the current state.
        was_conflict = precondition != head.body
        new_ann = PhotoAnnotation(
            photo_id=head.photo_id,
            user_id=current_user.id,
            body=suggested,
            target=head.target,
            is_current=True,
            event_type='updated',
        )
        db.add(new_ann)
        await db.flush()  # populate new_ann.id
        head.is_current = False
        head.superseded_by = new_ann.id
        results.append({"annotation_id": ann_id, "applied": True,
                        "new_annotation_id": new_ann.id, "superseded": head.id,
                        "was_conflict": was_conflict})
    await db.commit()

    # archive the file once every op in it is reflected in the current bodies
    all_done = True
    for op in pkg.get("ops", []):
        head, found = await _resolve_head(db, op.get("annotation_id"))
        if not (found and head and head.body == op.get("body")):
            all_done = False
            break
    archived = False
    if all_done:
        try:
            graduation.move_to_applied(filename)
            archived = True
        except OSError as e:
            logger.warning("graduation: could not archive %s: %s", filename, e)

    n_applied = sum(1 for r in results if r["applied"])
    logger.info("graduation apply %s: %d applied by user %s (archived=%s)",
                filename, n_applied, current_user.id, archived)
    return {"results": results, "applied": n_applied, "archived": archived}
