# Terrain mode — UX design & plan

Status: agreed 2026-07, branch `terrain-depth-panoramas` (5 commits: renderer +
worker + bench, shared viewer, datum/DTM split + mosaic builder, e2e golden
thread, whole-CZ downloader). This doc is the design record for integrating
terrain into the main app; the engine underneath is documented in
`enrich/terrain/README.md`.

Implementation status (2026-07-24): **v1 client slice landed** — viewport
rect + seam wrap in the shared viewer, mode button + marker states,
tap-to-select via the range circle, derived wedge, click-ray, long-press
enqueue (confirm popup; server policy still TBD), status polling, and
`tx1..ty2` rect URL sync, and worker-side progress-% emission (throttled
"rendering" pings on the existing callback, % riding in the meta jsonb
until the final result overwrites it; "rendering… N %" in the pane).
**v1 is complete end to end.** Next: v1.5 (partial artifacts reuse the
same plumbing), and the enqueue auth/quota policy.

## The mode

A new **mode button next to the Lines tool** switches the app into terrain
mode:

- The map stops showing photo markers and shows **terrain render markers**
  instead. Marker states: hollow/pulsing = queued, progress ring = rendering,
  solid = done, red = failed. In-progress renders are first-class citizens.
- The **range circle keeps its job** — it selects a render, spatially.
- **No next/prev buttons** in terrain mode. Navigation is tapping markers;
  next/prev would imply an ordering sparse viewpoints don't have.
- The **bearing arrow is hidden**. Renders are always 360°, so there is
  nothing to select by direction; the missing arrow itself signals
  "different rules here", reinforced by the mode button.

## Bearing vs. viewport: the settled question

Bearing is the **selector** — "which direction do I want" — and it never
moves except when the user explicitly drags it. Two proposals were
considered and **rejected**:

- live pano-pan → bearing sync (reselects content mid-pan);
- sync-on-exit, yaw → bearing when closing a 360 (reselects at the one
  moment — leaving — that must always be safe).

The accepted model: the app already separates "what I selected" from "where
I'm looking inside it" — that's the **zoom view's rect**, URL-synced, and it
has never fed selection. The terrain panorama is a flat texture, so the
viewport into it **is a rect**. Terrain mode = "the zoom view over a
synthetic 360° image":

- The terrain viewer's view transform serializes with the **same rect URL
  convention** as the zoom view. No new state concept, same muscle memory.
- The map shows a **view wedge** at the selected viewpoint, purely *derived*
  from the rect: center-x → azimuth, width → wedge FOV. One-directional,
  pane → map. (Wedge-dragging as an input is deferred sugar, maybe never.)
- **Pannellum stays untouched.** It's a minor feature with no map coupling
  today, and nothing here creates an expectation about it — the wedge
  belongs to terrain's rect, not to "360-ness". It can adopt the derived
  wedge later if it ever earns the attention.
- Seam: rects live on a cylinder. GL fix: `TEXTURE_WRAP_S = REPEAT` on both
  textures, viewport offset wraps modulo 1; URL rect x may leave [0, 1] and
  is normalized on parse.

## Interactions

- **Click a mountain** → geo coords (the depth click-back) AND a **ray on
  the map**: viewpoint → picked point with a distance label. This is the
  moment the feature explains itself.
- **Creation**: long-press on empty map in terrain mode → drop viewpoint →
  enqueue. Bridge from photo mode: "synthetic view from this photo" (uses
  photo lat/lon + GPS-altitude hint; the worker resolves the datum).
  Rendering is real compute: creation wants login + rate limit + dedupe by
  rounded (lat, lon, params); browsing stays open. Exact policy: TBD.
- **Selected render** (v1.5): faint coverage circle (max_distance — "what
  this can see").

## Streaming / progress

The horizon march is `maximum.accumulate` over distance, so the renderer is
already incremental in the perceptually right axis: checkpoints at distance
milestones (e.g. 10/25/50/100 km) each yield a **valid partial panorama** —
terrain grows outward, far ranges appearing behind ridges. No algorithm
change, just checkpointed emission.

Ship order: **progress-% first** (tiny JSON via the existing callback,
status `rendering`; marker ring + "rendering… N %" in the pane; client
polls), then partial artifacts as the flourish — same plumbing, throttled to
~4 milestones so mobile isn't re-downloading MBs per second. Renders are
seconds-to-tens-of-seconds, so % alone already carries most of the UX.

## Slices

**v1**: viewport refactor of `shared/terrain` (rect view + seam wrap + rect
URL serialization following the zoom view convention) → mode button + marker
swap with states → tap-to-select → derived wedge → click-ray → long-press
enqueue → progress polling. Bearing arrow untouched everywhere, hidden in
terrain mode.

**v1.5**: streamed partial panoramas, coverage circles, fog slider in the
main app, gzip depth transport (refinement 4).

**v2**: "photos that see this point" cross-linking, OSM `natural=peak`
labels drawn via the existing zoomview label layouter (refinement 7),
photo↔render registration for calibration refinement (refinement 6),
far-field anti-aliasing via max-pooled pyramid + crossing interpolation
(refinement 3).

## Open questions

- Auth/quota model for public enqueue.
- Graduation of artifact serving from the workbench API to the main backend
  (next to the photo pyramids) — prerequisite for the photo-pane bridge.
- ~~Whether `rect` for terrain lives in the same URL param as the zoom
  view's or a namespaced twin~~ — **settled while touching the URL code: a
  namespaced twin, `tx1..ty2`.** The zoom view's `x1..y2` doubles as an
  open-the-overlay signal at page load, so sharing the param would make a
  terrain deep link read as a photo zoom-view deep link; the twin keeps
  them unambiguous unconditionally. Parsed (and seam-normalized) at store
  module init, consumed by the pane's first viewer load.

## Operational notes for a fresh session

- Land/inspect the work: `git fetch hillview-terrain.bundle
  terrain-depth-panoramas:terrain-depth-panoramas` (bundle prerequisite:
  `enrich` head 7cfd77a), or clone the branch once pushed.
- Tests: `python -m pytest enrich/terrain -q` (25), `npm run test:e2e` in
  `enrich/web` (8, needs `npx playwright install chromium` once), shared
  viewer vitest via frontend config.
- Data: `download_cuzk.py` → `build_mosaic.py` → worker env
  (`TERRAIN_DSM_PATH` layered `path@radius:…`, `TERRAIN_DTM_PATH`,
  `TERRAIN_GEOID_OFFSET_M`).
