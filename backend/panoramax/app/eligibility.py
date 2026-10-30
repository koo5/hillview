"""Eligibility gates for federation candidates and selected members.

Used by BOTH the sequencer (before grid/bearing selection) and the read API
(filtering persisted member photos at serve time). Passing these gates does
not itself promise publication: selection.py chooses representatives.
The serve-time filter matters: when a photo flips out of
scope (soft-delete, is_public off, license change), the photos trigger bumps
the sequence's updated_at so the harvester re-crawls, but until the sequencer
prunes membership the item must already be gone from /items responses.

Requires `photos p JOIN users u ON u.id = p.owner_id` in the enclosing query
and a list-valued :scope_legal_rights bind param.

Only full1/panoramax_in grants can qualify, with owner consent and both
moderation gates. Skip and manual anonymization cannot establish that the
detector found no doodles, so only detector records without blurred objects
qualify. The data migration already made every blurred flag explicit.

Moderation signals also exclude a photo from federation: any thumbs-down
rating, or an unresolved flag (resolved flags don't exclude — an admin looked
and left the photo up; flags resolved by deletion are covered by p.deleted).
Note ratings/flags don't touch the photos row, so they propagate to the
catalog on the sequencer's cadence (membership prune bumps updated_at), while
serve-time filtering hides the item immediately.
"""

ELIGIBLE_PHOTO_WHERE = """
	p.legal_rights = ANY(:scope_legal_rights)
	AND p.panoramax_owner_share
	AND p.panoramax_moderator_approved
	AND u.panoramax_contributor
	AND p.detected_objects IS NOT NULL
	AND json_typeof(p.detected_objects) = 'object'
	AND COALESCE((p.detected_objects->>'manual')::boolean, false) = false
	AND NOT EXISTS (
		SELECT 1 FROM json_array_elements(COALESCE(p.detected_objects->'objects', '[]'::json)) o
		WHERE (o->>'blurred')::boolean
	)
	AND p.deleted = false
	AND p.is_public = true
	AND p.processing_status = 'completed'
	AND p.geometry IS NOT NULL
	AND p.effective_at IS NOT NULL
	AND p.captured_at IS NOT NULL
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
