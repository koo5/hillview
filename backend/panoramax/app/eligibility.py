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

A fix the receiver itself put more than MAX_LOCATION_ACCURACY_M off excludes
the photo too: the selection places one photo per few-metre cell, and Panoramax
readers take the position as given. An unknown radius passes, since no photo
captured before 2026-09-13 carries one. The radius is photos.location_accuracy_m
(migration 039), and exif_data changes don't bump the sequence either, so a
change reaches the catalog on the sequencer's cadence like the ratings above.
"""

MAX_LOCATION_ACCURACY_M = 5

# Each gate by name, so a pass can record which ones a photo failed
# (panoramax.photo_status) from the same conditions that decide it. The names
# are an API: the photo page words them (PANORAMAX_GATE_TEXT in the frontend).
GATES: list[tuple[str, str]] = [
	('grant', "p.legal_rights = ANY(:scope_legal_rights)"),
	('owner_share', "p.panoramax_owner_share"),
	('moderator_approval', "p.panoramax_moderator_approved"),
	('contributor', "u.panoramax_contributor"),
	('detections', "p.detected_objects IS NOT NULL AND json_typeof(p.detected_objects) = 'object'"),
	('manual_anonymization', "COALESCE((p.detected_objects->>'manual')::boolean, false) = false"),
	('doodles', """NOT EXISTS (
		SELECT 1 FROM json_array_elements(COALESCE(p.detected_objects->'objects', '[]'::json)) o
		WHERE (o->>'blurred')::boolean
	)"""),
	('deleted', "p.deleted = false"),
	('private', "p.is_public = true"),
	('processing', "p.processing_status = 'completed'"),
	('location', "p.geometry IS NOT NULL"),
	('capture_time', "p.effective_at IS NOT NULL AND p.captured_at IS NOT NULL"),
	('renditions', "p.sizes IS NOT NULL"),
	('location_accuracy', f"COALESCE(p.location_accuracy_m, 0) <= {MAX_LOCATION_ACCURACY_M}"),
	('owner_inactive', "u.is_active = true"),
	('test_user', "u.is_test = false"),
	('thumbs_down', """NOT EXISTS (
		SELECT 1 FROM photo_ratings pr
		WHERE pr.photo_source = 'hillview'
		  AND pr.photo_id = p.id
		  AND pr.rating = 'THUMBS_DOWN'
	)"""),
	('unresolved_flag', """NOT EXISTS (
		SELECT 1 FROM flagged_photos fp
		WHERE fp.photo_source = 'hillview'
		  AND fp.photo_id = p.id
		  AND fp.resolved = false
	)"""),
]

ELIGIBLE_PHOTO_WHERE = '\n\tAND '.join(f'({condition})' for _, condition in GATES)

# Every photo with whether it passes each gate. A NULL (an unset flag, say)
# counts as failing, as it does in a WHERE clause.
GATE_RESULTS_SQL = f"""
	SELECT p.id, {', '.join(f'COALESCE(({condition}), false) AS "{name}"' for name, condition in GATES)}
	FROM photos p JOIN users u ON u.id = p.owner_id
"""

# Deterministic capture order within an owner — same tiebreak as the timeline
# walk (burst shots sharing a 1-second captured_at order by original filename).
PHOTO_ORDER_BY = "p.effective_at, COALESCE(p.original_filename, ''), p.id"
