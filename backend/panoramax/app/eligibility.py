"""The single definition of which photos this instance serves.

Used by BOTH the sequencer (deciding membership) and the read API (filtering
items at serve time). The serve-time filter matters: when a photo flips out of
scope (soft-delete, is_public off, license change), the photos trigger bumps
the sequence's updated_at so the harvester re-crawls, but until the sequencer
prunes membership the item must already be gone from /items responses.

Requires `photos p JOIN users u ON u.id = p.owner_id` in the enclosing query
and a :scope_legal_rights bind param.

Moderation signals also exclude a photo from federation: any thumbs-down
rating, or an unresolved flag (resolved flags don't exclude — an admin looked
and left the photo up; flags resolved by deletion are covered by p.deleted).
Note ratings/flags don't touch the photos row, so they propagate to the
catalog on the sequencer's cadence (membership prune bumps updated_at), while
serve-time filtering hides the item immediately.
"""

ELIGIBLE_PHOTO_WHERE = """
	p.legal_rights = :scope_legal_rights
	AND p.deleted = false
	AND p.is_public = true
	AND p.processing_status = 'completed'
	AND p.geometry IS NOT NULL
	AND p.effective_at IS NOT NULL
	AND p.sizes IS NOT NULL
	AND u.is_active = true
	AND u.is_test = false
	AND NOT EXISTS (
		SELECT 1 FROM photo_ratings pr
		WHERE pr.photo_source = 'hillview'
		  AND pr.photo_id = p.id
		  AND pr.rating = 'THUMBS_DOWN'
	)
	AND NOT EXISTS (
		SELECT 1 FROM flagged_photos fp
		WHERE fp.photo_source = 'hillview'
		  AND fp.photo_id = p.id
		  AND fp.resolved = false
	)
"""

# Deterministic capture order within an owner — same tiebreak as the timeline
# walk (burst shots sharing a 1-second captured_at order by original filename).
PHOTO_ORDER_BY = "p.effective_at, COALESCE(p.original_filename, ''), p.id"
