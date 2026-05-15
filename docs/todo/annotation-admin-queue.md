# Annotation admin-approval queue (stopgap moderation)

## Context

`PhotoAnnotation` is currently free-for-all: anyone logged in can create, edit, or
supersede annotations on any photo, and they appear publicly immediately. The model's
own docstring (`backend/common/models.py`) acknowledges this is intentional v1 and
that the long-term vision is a web-of-trust / RDF-based moderation graph.

We are not building that long-term vision yet. As contributors start arriving (first
ones have already shown up), the free-for-all becomes too exposed: a single bad-faith
or low-quality contributor can degrade the corpus that the project's strategic value
rests on, and the only current defence is DB backups + reactive cleanup.

This task introduces the smallest possible gatekeeping mechanism that buys time
until a real trust system is needed.

## Design intent

Not a moderation platform. A two-state trust model with a queue:

- **Untrusted contributor**: every write (new annotation or edit) lands in a
  `pending` state, invisible to the public, visible to the author and to admins.
  Admin approves or rejects.
- **Trusted contributor**: free-for-all (current behaviour). Writes go live
  immediately, no review row produced.
- **Auto-promotion**: after N distinct approved annotation chains (default 5),
  an untrusted user is promoted to trusted. Configurable.

Explicit non-goals (v1): branching, ACLs per-photo, fine-grained roles, dispute
resolution between trusted users, appeal flows, structured-data schema changes.

## Key data-model insight

The moderation *decision* is the thing that's new. The annotation *content* is
not — it already has a perfectly good home in `photo_annotations`. So:

- All annotation rows (pending or approved, by trusted or untrusted authors) live
  in `photo_annotations` as today.
- A new tiny side table `annotation_reviews` records the moderation decision per
  row. It only exists for rows authored by untrusted users.
- Pending rows do not participate in chain supersession (`is_current` /
  `superseded_by`) until an admin approves them. They live as detached children
  of the chain, identified by `root_id`.

This keeps `photo_annotations`'s chain semantics unchanged: a row is in the
public version chain iff a trusted user wrote it directly, or iff an admin
approved an untrusted user's submission. Approval is the only moment outside of
trusted writes when chain pointers move.

## Data model changes

### `users` table

Add:
- `is_trusted: bool default false` — separate from `role`. A USER with
  `is_trusted=true` behaves as today (free-for-all). MODERATOR / ADMIN are
  implicitly trusted regardless of this flag.

Existing user accounts: backfill `is_trusted=true` for the project owner and any
already-active known contributors (manual SQL during migration). Everyone else
defaults to false.

### `photo_annotations` table

Add:
- `root_id: str` — id of the first row in the chain. For a brand-new annotation,
  `root_id == id`. For any subsequent row in the chain (edit, supersession),
  inherits the existing chain's `root_id`. Indexed.

  Enables: "find this chain's tip," "list distinct chains by author," and
  "associate a pending edit with its target chain without setting `superseded_by`
  prematurely."

Backfill on migration: recursive CTE walking each existing row backward through
`superseded_by` (find the row whose `superseded_by = mine`, repeat) to find the
chain root. For rows that are themselves roots, `root_id = id`.

### `annotation_reviews` table (new)

```
annotation_id  pk, fk photo_annotations.id, on delete cascade
author_id      fk users (denormalized — saves a join on the hot promotion / cap queries)
status         str  -- 'pending' | 'approved'
created_at     datetime
reviewed_by    fk users, nullable
reviewed_at    datetime, nullable
review_note    text, nullable  -- shown to author if rejected
```

Rejection is **hard-delete**: a rejected submission removes both the
`photo_annotations` row and (via cascade) the `annotation_reviews` row. The
review row never lives in a `rejected` state. If audit of rejections is wanted
later, add a separate `annotation_rejection_log` table; not v1.

A row exists in `annotation_reviews` **iff** the corresponding row in
`photo_annotations` was authored by an untrusted user and has not yet been
approved or rejected. Trusted-authored rows produce no review row, ever.

## Write paths

### Trusted author (USER with is_trusted=true, MODERATOR, ADMIN)

Unchanged from today. INSERT into `photo_annotations`, run existing
supersession logic (set prior tip's `is_current=false`, `superseded_by=new.id`;
new row's `is_current=true`). No review row.

### Untrusted author, creating a new annotation

INSERT into `photo_annotations` with `root_id = self.id`, `is_current = false`,
`superseded_by = NULL`. INSERT into `annotation_reviews` with `status='pending'`.

The row is **not** in the visible chain yet — it hangs off as a pending
proposal of a new chain.

### Untrusted author, editing an existing chain (their own or someone else's)

The chain's current tip C is found via `SELECT id FROM photo_annotations WHERE
root_id=<chain> AND is_current=true`.

If the author already has a pending row in this chain (look up via
`annotation_reviews` joined to `photo_annotations` on `root_id`):
- **Mutate that row in place**. UPDATE its `body` / `target`. Do not create a
  new row. Update the review row's `created_at` so the admin queue sorts
  sensibly.

Otherwise:
- INSERT a new row into `photo_annotations` with `root_id` inherited from C,
  `is_current=false`, `superseded_by=NULL`. INSERT review row, `status=pending`.

Either way: enforce per-user pending-chain cap (default 20). Count is `SELECT
COUNT(DISTINCT pa.root_id) FROM annotation_reviews ar JOIN photo_annotations pa
ON pa.id=ar.annotation_id WHERE ar.author_id=U AND ar.status='pending'`. Exceeding
the cap returns a clear error.

### Untrusted author withdrawing their pending row

`DELETE FROM photo_annotations WHERE id=B AND user_id=U` provided
`annotation_reviews.status='pending'`. The review row cascades.

Withdraw of an already-approved row is not supported in v1 (the row's content
is in the public chain history and removing it would tear the chain). If the
user wants to "delete" an approved annotation, they submit a pending edit
blanking its content; admin approves. Could add a proper delete-event later.

## Approve / reject

### Approve B

Atomic transaction:

1. Find current tip of chain: `SELECT id FROM photo_annotations WHERE
   root_id=B.root_id AND is_current=true` → C. (May be NULL if B is the first
   approved row in a brand-new chain; that's fine.)
2. If C exists: `C.is_current=false, C.superseded_by=B.id`.
3. `B.is_current=true`.
4. `annotation_reviews[B]: status='approved', reviewed_by, reviewed_at`.
5. Auto-promotion check (below).

If the chain's tip moved between the time B was submitted and the time it's
approved (a trusted user edited in the meantime), B still supersedes the
*current* tip. Admin uses judgement at review time — they see the chain and
can reject B if it conflicts substantively with intervening edits.

### Reject B

Atomic: `DELETE FROM photo_annotations WHERE id=B`. Cascades the review row.
The `review_note` is read off the request and sent to the author as a
notification before the delete (since the row is going away). If we want
persistent rejection audit later, add `annotation_rejection_log`.

## Read path

Public read filter, applied wherever `photo_annotations` is queried:

```sql
LEFT JOIN annotation_reviews r ON r.annotation_id = photo_annotations.id
WHERE photo_annotations.is_current = true
  AND r.annotation_id IS NULL
```

Trusted-authored rows have no review row → visible. Untrusted-authored rows
that have been approved had their review row updated to `status='approved'`,
but the LEFT JOIN above filters them out too — so the filter as written is
wrong. Correct version:

```sql
LEFT JOIN annotation_reviews r ON r.annotation_id = photo_annotations.id
WHERE photo_annotations.is_current = true
  AND (r.annotation_id IS NULL OR r.status = 'approved')
```

The visibility predicate is mechanical enough that we should encode it in one
place: a SQLAlchemy hybrid / helper function `visible_annotations_query()` or a
DB view `visible_photo_annotations`. Every callsite that today queries
`photo_annotations` either:
- uses the helper (preferred), or
- is explicitly flagged as needing all rows (admin endpoints, author-self
  views).

Audit grep target: anywhere `photo_annotations` is queried directly. Smaller
surface than putting `moderation_status` on the row itself (because pending
rows are not `is_current=true`, so existing `is_current=true` filters already
hide most of them — the visibility join is only load-bearing for the case of an
*approved* annotation that should be visible).

Author-self endpoint (`GET /api/me/annotations/pending` or similar) returns
their own pending rows so the UI can render "pending review" badges.

## Admin queue endpoint + UI

Backend:
- `GET /api/admin/annotations/pending?limit=N&offset=M` — paginated list of
  pending submissions. `SELECT ... FROM annotation_reviews WHERE status='pending'
  ORDER BY created_at`. Joined with photo and author info needed for review.
  Restricted to ADMIN / MODERATOR.
- `POST /api/admin/annotations/{id}/approve` — runs the approve flow above.
- `POST /api/admin/annotations/{id}/reject` — optional `review_note` body
  field; runs the reject flow above.

Frontend:
- Simple `/admin/annotations` page. List view, photo thumbnail with the
  pending annotation overlaid, body text, author, created_at, two buttons.
- If the pending row is an edit (i.e. there is an approved row in the same
  chain), show the current approved version alongside for diff context.
- Does not need to be beautiful. Keyboard shortcuts (`a` approve, `r` reject)
  would be nice but optional.
- Visible only to ADMIN / MODERATOR.

A simple queue-count badge in the admin's profile menu is enough — no email,
no push, no FCM. Admin checks the queue when they think to.

## Auto-promotion

After each approve action:

```
approved_chains = SELECT COUNT(DISTINCT pa.root_id)
    FROM annotation_reviews ar
    JOIN photo_annotations pa ON pa.id = ar.annotation_id
    WHERE ar.author_id = author AND ar.status = 'approved'

if approved_chains >= PROMOTION_THRESHOLD and not author.is_trusted:
    author.is_trusted = true
    (optional: notify the author "you're now a trusted annotator")
```

Counting distinct chains via `root_id` prevents the obvious gaming path (edit
your one good annotation five times to hit the threshold).

`PROMOTION_THRESHOLD` is a config constant. Default 5. Tune as we learn.

## Author-facing UX

- On submitting any write while untrusted: clear toast / inline message
  saying "Submitted for review. It will appear publicly once approved."
- The author's own view shows their pending rows with a "pending" indicator,
  using the author-self endpoint. Pending edits of an existing chain show
  alongside the chain's current approved version.
- On rejection: notification with `review_note` if present. The pending row
  was hard-deleted; the author can submit a fresh edit.
- An untrusted user editing their own already-approved annotation goes through
  the pending flow like any other untrusted write. There is no "frozen until
  promoted" message — the freedom to *edit* is unchanged, only the freedom to
  publish immediately is gated.

## Anti-flood

Per-user pending-chain cap (default 20 distinct chains in pending state). When
exceeded, the API returns a clear error. The cap is per chain (not per pending
row), so repeated edits within one draft do not consume budget — mutate-in-place
sees to that anyway.

Cap does not apply to trusted users (they don't produce review rows).

## What this is *not* solving (and is fine to defer)

- Reverting trusted users who later turn problematic. The `root_id` + version
  chain make this tractable (SQL-able "revert chains whose current tip is
  authored by H to the last pre-H version"), but no UI in v1.
- Persistent audit of rejections. Hard-delete is good enough until it isn't.
- Disagreement between two trusted users editing the same annotation. They
  both win until last-writer; same as today.
- Annotation deletion for *trusted* users beyond what today's `event_type`
  hints at. Out of scope.
- Distinguishing "low quality but well-intentioned" from "bad faith." Admin
  uses judgement; no signal field needed.
- Bulk approve. Single-item review is fine at expected volumes.

## Definition of done

- [ ] Migration: `users.is_trusted`, `photo_annotations.root_id`, new
      `annotation_reviews` table. Existing `photo_annotations` rows backfilled
      with `root_id` walked from `superseded_by` chains.
- [ ] Write path: trusted authors unchanged; untrusted authors produce a
      pending row + review row; untrusted edits hang off the chain (don't move
      `is_current` / `superseded_by`); per-user pending-chain cap enforced;
      mutate-in-place when the same author edits a chain they already have
      pending in.
- [ ] Approve flow moves the chain pointers atomically (current tip's
      `is_current=false` + `superseded_by`, new row's `is_current=true`,
      review row → approved).
- [ ] Reject flow hard-deletes the pending row (cascades review row);
      `review_note` delivered to author as notification before delete.
- [ ] Read path: visibility helper (`visible_annotations_query()` or SQL view)
      added; existing callsites migrated to it or explicitly flagged as
      admin/author-self. Audit grep covered.
- [ ] Author-self endpoint for listing own pending rows.
- [ ] Admin endpoints (`/api/admin/annotations/pending`, approve, reject) with
      role check; pending edits shown alongside their current approved
      counterpart for diff context.
- [ ] Admin UI page at `/admin/annotations`.
- [ ] Auto-promotion at `PROMOTION_THRESHOLD` distinct approved chains.
- [ ] Anti-flood pending-chain cap.
- [ ] Author-facing "pending review" indicator.
- [ ] Tests:
      - untrusted user creates an annotation → pending row + review row;
        public reads omit it; author sees it
      - admin approves → row is_current, visible publicly
      - untrusted user submits a pending edit of an existing approved chain →
        new row exists, but chain's `is_current` did not move; public still
        sees prior approved version
      - admin approves the edit → chain pointers move, new row visible, prior
        approved row becomes history
      - untrusted user edits their own pending row → mutates in place, no new
        row, review row's `created_at` updated
      - admin rejects → row hard-deleted, review row cascades, author
        notification delivered
      - trusted user edits a chain while untrusted user has pending edit on it
        → trusted edit goes live as new tip; on subsequent approve, untrusted
        row supersedes the trusted edit as the new tip
      - after N distinct approved chains by user → promoted → subsequent
        writes are immediately approved, no review rows produced

## Test plan

### Source files that need visibility-filter retrofit

Beyond `annotation_routes.py` itself, two non-obvious read sites count
annotations and would be polluted by pending rows if not retrofitted:

- `backend/api/app/featured_routes.py` — `_annotated_count_subquery()` counts
  current non-deleted annotations to rank "well-annotated" photos for the
  Featured endpoint. If pending rows leak in, an untrusted user can boost a
  photo's featured ranking by submitting unapproved content. Must apply the
  visibility filter (or use `visible_annotations_query()`).
- `backend/api/app/annotation_routes.py` — `effective_annotation_count_subquery()`
  is used by `bestof_routes.py` for the global photo ranking. Same problem,
  same fix.

Other endpoints in `annotation_routes.py` (`GET /api/annotations/photos/{id}`,
PUT, DELETE) all need either visibility filtering on read, or trust-aware
routing on write, per the rules above.

### Existing tests — trust posture for fixture users

The whole `backend/tests/integration/test_annotations.py` suite assumes
free-for-all today. Cleanest path:

- Backfill **fixture users** (`test`, `testuser`, `admin`) as `is_trusted=true`
  during test setup. Existing assertions then continue to hold — those tests
  become the "trusted-author flow" coverage with no rewrites needed. Confirm
  this is done in `tests/utils/` (probably wherever `BaseUserManagementTest`
  sets up users).
- One existing test (`TestAnnotationHiddenUserFiltering`) tests hidden-user
  filtering on the read path; verify it still passes once the read path also
  applies the visibility join — these two filters compose, they don't conflict.

### Existing tests — likely small adjustments

- `test_update_annotation_supersedes`, `test_delete_annotation_creates_tombstone`
  — should pass unchanged once test users are trusted. But add an explicit
  assertion that no row appears in `annotation_reviews` after each operation
  (sanity-check that trusted writes don't accidentally produce review rows).
- Any test that inspects the raw rowset of `photo_annotations` should be
  audited for whether it expects every row to be publicly visible — that
  invariant changes once any untrusted user is in the picture.

### New tests — trusted user flow regressions

- New: trusted user creates → no review row exists for that annotation.
- New: trusted user edits another trusted user's chain → standard supersession,
  no review row at any point.

### New tests — untrusted author write paths

- Untrusted user creates an annotation → `photo_annotations` row exists with
  `is_current=false`, `superseded_by=NULL`, `root_id=id`. `annotation_reviews`
  row exists with `status='pending'`. Public `GET /api/annotations/photos/{id}`
  does not return it. Author-self endpoint does.
- Untrusted user edits their own pending row → the same row is mutated in
  place; no new `photo_annotations` row created; review row's `created_at`
  updated to reflect resubmission.
- Untrusted user submits a pending edit of an existing approved chain →
  new `photo_annotations` row with `root_id` inherited, `is_current=false`,
  `superseded_by=NULL`. Chain tip's `is_current` did **not** move. Public read
  still returns the previous approved version.
- Untrusted user submits a pending edit of someone else's approved chain —
  same behaviour as editing one's own (allowed; just queues a review).
- Untrusted user attempts a second pending edit on a chain they already have
  pending in → API mutates their existing pending row, does not create a new
  one.
- Untrusted user withdraws (DELETE) their pending row → `photo_annotations` row
  gone, `annotation_reviews` row cascaded.
- Untrusted user attempts to DELETE an approved row of their own → 4xx (not
  supported in v1; document the response code in the test).
- Untrusted user attempts to edit/delete *while suspended/admin-disabled* —
  consistent with existing auth rules.
- Pending-chain cap: untrusted user creates 20 distinct pending chains; the
  21st attempt returns the cap-exceeded error.

### New tests — admin approve / reject

- Admin approves a pending new annotation → chain tip moves: row's
  `is_current=true`. Public read now returns it. Review row's `status='approved'`,
  `reviewed_by`/`reviewed_at` filled.
- Admin approves a pending edit → previous tip's `is_current=false`,
  `superseded_by` set to the approved row's id; approved row becomes new
  tip. Public read returns the edited version.
- Admin approves a pending edit *after* a trusted user has independently
  edited the same chain → approved row supersedes the trusted user's edit
  (the *current* tip at approval time). Earlier history preserved in the
  chain via `superseded_by` walk.
- Admin rejects → `photo_annotations` row hard-deleted, `annotation_reviews`
  cascaded, author receives a notification with `review_note` if supplied.
- Auth: non-admin GET / POST on `/api/admin/annotations/...` → 403.

### New tests — auto-promotion

- Untrusted user gets `PROMOTION_THRESHOLD` distinct approved chains → flips to
  `is_trusted=true` on the final approve. Subsequent annotation create returns
  immediately visible, no review row produced.
- Untrusted user gets `PROMOTION_THRESHOLD` approved *edits to the same chain*
  → does **not** promote (single chain, count is 1).
- Promotion counting query: untrusted user has 4 approved chains; submits a
  pending edit to one of them; admin approves the edit. Chain count remains 4,
  no promotion yet.

### New tests — read-path visibility composition

- An untrusted user's pending row is invisible to *every* public read path:
  `GET /api/annotations/photos/{id}`, Featured (`/api/featured/nearest`),
  Best-of ranking. The featured/best-of tests should assert that pending rows
  do not boost annotation counts.
- An approved annotation's visibility composes correctly with hidden-user
  filtering: a user who hides the author still doesn't see it.

### Frontend tests

- `frontend/src/lib/annotationApi.test.ts` — extend with cases for the new
  fields in the create/list response (review status), and for the author-self
  pending endpoint.
- `frontend/src/lib/utils/annotationBody.test.ts` and `labelLayout.test.ts`
  appear to be pure utilities; likely unaffected. Verify on a quick read.
- New: a small unit test ensuring the "pending review" badge renders for
  pending rows in author-self view and does not render for trusted-authored
  approved rows.

### Migration test

- Apply migration on a fixture DB containing existing annotation chains
  (root + several supersessions). Assert `root_id` is correctly walked to the
  chain root for every row. Assert no `annotation_reviews` rows are created
  for existing data (everything grandfathered as approved-by-trust).

## Future evolution (not this task)

When the queue genuinely outgrows one admin:
- A second tier of moderator who can approve but not promote.
- Per-photo / per-region delegated trust (the photo owner can pre-approve
  annotations on their own photos).
- Endorsement / dispute counts that feed back into `is_trusted`.
- Persistent rejection audit table.
- Eventually the web-of-trust model described in `PhotoAnnotation`'s docstring.

None of this needs to be designed now. The current task should make those
transitions easy but not prejudge them.
