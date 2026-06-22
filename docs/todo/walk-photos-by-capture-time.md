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
  surface) plus a stubbed "add user" control.
- A polyline connecting the loaded timeline photos in time order — the cheap
  "see the route".

Not in scope (v1), noted for later:

- Multi-user merge UI ("add user" is a visible stub).
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

- Resolve anchor `(captured_at, id)` from `anchor_id` (must be visible to the
  requester; else 404 / empty result).
- Before: `owner_id IN (user_ids) AND (captured_at, id) < (anchor) AND <filters>
  ORDER BY captured_at DESC, id DESC LIMIT before+1`, then reverse to ascending.
- After: `... AND (captured_at, id) > (anchor) ... ORDER BY captured_at ASC,
  id ASC LIMIT after+1`.
- Filters on every query: `geometry IS NOT NULL`, `captured_at IS NOT NULL`,
  `deleted = false`, `processing_status = 'completed'`,
  `(is_public = true OR owner_id = current_user_id)`, plus
  `apply_hidden_content_filters()`.
- Row-value keyset via `tuple_(captured_at, id)` (Postgres supports it) → stable
  ordering with no skips/dupes when timestamps tie (bursts).

Response:

- `{ photos: [...ascending by (captured_at, id)], anchor_index,
  has_more_before, has_more_after }`.
- Each photo uses the **same serializer as the bounds query** so the client can
  treat timeline photos identically to spatially-loaded ones.

Index + migration:

- `CREATE INDEX idx_photos_owner_captured_id ON photos (owner_id, captured_at,
  id);` via the next Alembic revision after `020_add_place_parent`.
- Non-partial: it must also serve own-private rows (`is_public = false`), so a
  partial index on `is_public` would miss them. Serves the single-owner keyset
  directly; the multi-owner IN-list merges per-owner runs.

Latency: an indexed keyset of ~200 rows is sub-100ms; the panel still shows a
loading state for honesty on slow links.

## Frontend

New `lib/timeline.ts`:

- Stores: `timelineActive`, `timelinePhotos: PhotoData[]`, `timelineCursor`,
  `timelineUserIds`, `timelineLoading`, `timelineHasMoreBefore/After`.
- `startTimeline(anchorPhoto)` — guard (hillview source, non-null
  `captured_at`); set `userIds = [owner]`; fetch; map rows → `PhotoData`
  (shared mapper with `StreamSourceLoader`); set list + `cursor = anchor_index`;
  activate; then select the neighbor in the pressed direction.
- `stepTimeline(dir)` — move cursor ±1; at a loaded end with `hasMore`,
  `extendTimeline`; else clamp; then `selectPhoto(target)` + pin.
- `extendTimeline(end)` — fetch more using the first/last loaded photo as the
  new anchor; prepend/append; keep the cursor pointing at the same photo.
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
- Tracked users: list (v1: the single anchor owner's username) + disabled
  "add user" stub.
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
- Front photo has null `captured_at` → can't center; toast.
- A fetch is in flight → ignore further steps until it resolves (or coalesce).
- End of the loaded window → extend if `hasMore`, else clamp (no wrap-around).
- Switching anchor user (walk after selecting a different user's photo) →
  restart the timeline for the new user.
- Window constants fixed (`TIMELINE_BEFORE` / `TIMELINE_AFTER` = 100). "See the
  whole route" later = raise the constants; intentionally not user-variable now.

## Testing

- Backend pytest: ordering + keyset around the anchor; before/after counts and
  `has_more`; visibility (public / own-private / blocked-user / hidden-photo);
  null `captured_at` and null geometry excluded; multi-owner IN-list; anchor
  missing or invisible.
- Frontend Playwright: `,`/`.` walks; off-screen target pans, in-range target
  does not; panel shows the ordered list, highlights and auto-scrolls to
  current; row click jumps; polyline appears on activate and clears on stop. Use
  the `data-testid`s above.

## Future

- Multi-user merge: wire the "add user" stub to append owner ids to `user_ids`;
  the backend already accepts the list.
- Mapillary / Panoramax timelines (separate per-source ordering).
- Route direction styling (gradient / arrows), timeline persistence across
  reloads, variable window size.
