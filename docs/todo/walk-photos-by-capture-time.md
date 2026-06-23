# Walk photos by capture time (timeline navigation)

## Goal

From the combined gallery/map view, let the user step through a user's photos in
capture-time order with the keyboard, jumping across space as needed. The client
only ever holds a spatial subset of photos, so the ordering must come from the
server, indexed by `captured_at`.

v1 walks **one** user's photos — the owner of the photo you start on. The query
path and UI are shaped so that a future "merge several users into one timeline"
is an additive change, not a rewrite.

## Scope

In scope (v1):

- Server endpoint returning N photos before/after an anchor in capture-time
  order, for one or more owners.
- Composite index keeping that query fast.
- Client timeline store holding the loaded window + a cursor.
- Keyboard walk (`,` older / `.` newer) reusing the existing marker-click
  "pan-or-just-select" behavior.
- Pinning the current photo so dense-area server culling can't drop it.
- Slide-in timeline panel showing the actual ordered list (also our debug
  surface) plus tracked-users management (add/remove → merged timeline).
- A polyline connecting the loaded timeline photos in time order — the cheap
  "see the route".

Not in scope (v1), noted for later:

- Variable window size (constants are fixed).
- Walking Mapillary / Panoramax sequences (only our DB photos carry
  `owner_id` / `captured_at`).
- Route direction gradient / arrowheads; timeline persistence across reloads.

## Constraints found in the code (why the design is shaped this way)

- Combined view: gallery + Leaflet map always both visible (`Main.svelte`); no
  separate "gallery mode" vs "map mode".
- `handleMarkerClick` (`Map.svelte:762-810`) already implements "in range →
  select; off-screen → `flyTo` then select." Walking reuses this exactly.
- `picks` are filtered to the current viewport **server-side**
  (`query_picked_photos`, `hillview_routes.py:289-327`) and capped at 200
  (`MAX_HILLVIEW_PICKS`). So `picks` is useful only to pin in-view photos, never
  to carry the whole timeline. The client holds the full window from the
  timeline response instead.
- `captured_at` / `owner_id` live only on our `Photo` table
  (`backend/common/models.py:74,120`); Mapillary/Panoramax photos are not in it
  → timeline is hillview-only.
- Keyset/cursor-by-timestamp is already the house pattern
  (`activity_routes.py`, `photo_routes.py`). There is a `captured_at` index but
  no `(owner_id, captured_at)` composite yet.
- Keys `,` and `.` are free (`handleKeyDown`, `Main.svelte:316-382`).

## Backend

New endpoint `GET /api/photos/timeline`.

Params:

- `user_ids` — comma-separated owner ids (v1 client sends one: the anchor's
  owner).
- `anchor_id` — photo to center on; server reads its `(captured_at, id)`.
- `before`, `after` — counts, default 100, hard cap (e.g. 250).
- auth token optional (enables own-private inclusion + hidden-content filtering).

Query:

- Order/anchor by `eff = effective_at` — a **stored column** (capture time, else
  upload time as naive UTC) kept current by a DB trigger (migration 022). A real
  column, so the keyset stays index-backed.
- Resolve anchor `(eff, id)` from `anchor_id` (must be visible; else 404).
- Before: `owner_id IN (user_ids) AND (eff, id) < (anchor) AND <filters>
  ORDER BY eff DESC, id DESC LIMIT before+1`, then reverse to ascending.
- After: `... AND (eff, id) > (anchor) ... ORDER BY eff ASC, id ASC LIMIT after+1`.
- Filters on every query: `geometry IS NOT NULL`, `deleted = false`,
  `processing_status = 'completed'`, `(is_public = true OR owner_id =
  current_user_id)`, plus `apply_hidden_content_filters()`. (No `captured_at IS
  NOT NULL` — un-timed photos fall back to upload time; only missing *location*
  excludes a photo.)
- `(eff, id)` keyset tiebreaker → stable ordering, no skips/dupes when timestamps
  tie (bursts).

Response:

- `{ photos: [...ascending by effective time], anchor_index,
  has_more_before, has_more_after }`.
- Each entry is a lightweight **navigation index** — `{id, lat, lng, bearing,
  captured_at, uploaded_at, thumb_url, owner_id, owner_username}` — not a full
  photo feed. `captured_at` may be null; the client displays/sorts by
  `captured_at ?? uploaded_at` and marks upload-time entries. The gallery still
  renders the worker-loaded copy of the selected photo (heavy fields omitted).

Index + migration:

- `effective_at` — a stored column = `captured_at`, else upload time (naive UTC)
  — kept current by a DB trigger (`photos_effective_at_trg`, BEFORE INSERT OR
  UPDATE). A trigger, **not** a `GENERATED` column, because the tz cast isn't
  `IMMUTABLE` (which generated columns require). BEFORE INSERT sees the
  `server_default`-applied `uploaded_at`, so new uploads are covered.
- Migration **022** adds the column + trigger, backfills existing rows, creates
  `(owner_id, effective_at, id)`, and drops the `(owner_id, captured_at, id)`
  index that revision 021 had added (now superseded).
- Indexing a real column (not a `COALESCE(...)` expression) keeps the keyset walk
  index-backed: `owner_id = X ORDER BY effective_at, id` is an index scan; the
  multi-owner IN-list merges per-owner runs.
- Non-partial: must also serve own-private rows (`is_public = false`), so a
  partial index on `is_public` would miss them.

Latency: an indexed keyset of ~200 rows is sub-100ms; the panel still shows a
loading state for honesty on slow links.

## Frontend

New `lib/timeline.ts`:

- Stores: `timelineActive`, `timelinePhotos: PhotoData[]`, `timelineCursor`,
  `timelineUsers` ({id, username}), `timelineLoading`, `timelineHasMoreBefore/After`.
- `startTimeline(anchorPhoto)` — guard (Hillview source + known owner); set
  `userIds = [owner]`; fetch; map index rows → minimal `PhotoData`; set list +
  `cursor = anchor_index`;
  activate; then select the neighbor in the pressed direction.
- `stepTimeline(dir)` — move cursor ±1; at a loaded end with `hasMore`,
  `extendTimeline`; else clamp; then `selectPhoto(target)` + pin.
- `extendTimeline(end)` — fetch more using the first/last loaded photo as the
  new anchor; prepend/append (dedup the repeated anchor by uid); keep the cursor
  pointing at the same photo.
- Prefetch: `jumpToIndex` fires `extendTimeline` (non-blocking) once the cursor is
  within `TIMELINE_PREFETCH_MARGIN` (20) of a loaded end, so the next chunk is
  usually present before you reach the edge; the blocking extend in `stepTimeline`
  is the fallback for jumping straight to an end.
- `stopTimeline()` — clear, `active = false`, remove polyline, close panel.

`selectPhoto` refactor:

- Extract the "in range → select : `flyTo` then select" body of
  `handleMarkerClick` into a shared `selectPhoto(photo)`; `handleMarkerClick`
  calls it. Because `flyTo` needs the Leaflet instance (owned by `Map.svelte`),
  route timeline selection to the map via a small store action
  (`requestSelectPhoto`) that `Map.svelte` fulfills — one code path for clicks
  and walking.

Keyboard (`Main.svelte` `handleKeyDown`):

- `,` → walk older, `.` → walk newer (skip when typing in input/textarea or with
  Ctrl/Alt/Meta, matching the existing guard).
- inactive → `startTimeline(photoInFront)`; active → `stepTimeline(dir)`.
- `Escape` closes the panel / stops the timeline.
- no `photoInFront` → toast "select a photo to start a timeline".

Picks pinning:

- On each step add the target `uid` to the existing `picks` set (optionally the
  immediate next/prev too, for prefetch) so the server doesn't cull it after
  `flyTo`. Union with the current front-photo auto-pick; don't disturb existing
  pick clearing.

Panel `lib/components/TimelinePanel.svelte` (NavigationMenu-style drawer):

- Header + close.
- Tracked users: `{id, username}` list (anchor owner + any added), each with a
  remove ✕; "+ add user" opens a picker (searches `GET /users/`, filters, excludes
  already-tracked) → adds to the merged timeline (re-fetch around the cursor).
  Usernames render directly from the store — no scanning loaded photos (which
  failed for users with no photo in the window, and even showed the raw UID in the
  single-user case because the each-block wasn't re-run when photos arrived).
- Ordered list: a row per photo (thumb + formatted `captured_at`), current
  cursor highlighted and auto-scrolled into view; click a row → jump
  (`selectPhoto` + set cursor). Doubles as the debug view.
- Position "n / total" + loading spinner.
- `data-testid` on the panel, rows, user list, and add-user button.

Route polyline (in `Map.svelte`):

- One `L.polyline` over `timelinePhotos` coords in order; add on activate,
  update on list change, remove on stop. Single color for v1. (Two-tone
  past/future split at the cursor is easy later but adds a per-step update —
  deferred.)
- No separate per-photo timeline dots: the spatial pipeline already draws
  markers for in-view photos, so dots would double up and reintroduce the
  off-bbox marker clutter. The line carries the overall shape; the panel lists
  the rest.

## Edge cases / decisions

- Anchor is not a hillview photo → can't build a timeline; toast + no-op.
- Photos with no `captured_at` fall back to `uploaded_at` for ordering and
  display (marked as upload-time in the panel); only photos with no *location*
  are excluded.
- A fetch is in flight → ignore further steps until it resolves (or coalesce).
- End of the loaded window → extend if `hasMore`, else clamp (no wrap-around).
- Switching anchor user (walk after selecting a different user's photo) →
  restart the timeline for the new user.
- Window constants fixed (`TIMELINE_BEFORE` / `TIMELINE_AFTER` = 100). "See the
  whole route" later = raise the constants; intentionally not user-variable now.

## Testing

- Backend pytest: ordering + keyset around the anchor; before/after counts and
  `has_more`; visibility (public / own-private / blocked-user / hidden-photo);
  null geometry excluded (null `captured_at` falls back to upload time);
  multi-owner IN-list; anchor missing or invisible.
- Frontend Playwright: `,`/`.` walks; off-screen target pans, in-range target
  does not; panel shows the ordered list, highlights and auto-scrolls to
  current; row click jumps; polyline appears on activate and clears on stop. Use
  the `data-testid`s above.

## Future

- Mapillary / Panoramax timelines (separate per-source ordering).
- Route direction styling (gradient / arrows), timeline persistence across
  reloads, variable window size.
