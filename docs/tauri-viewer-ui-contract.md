# The Tauri viewer pane ("Gallery"), as observed

Written while reimplementing the top pane in frontend2. The point is
fidelity: this file records what the Svelte app actually does so the Compose
version can match it instead of inventing something adjacent. Line references
are to `frontend/src/lib/...` at the time of writing.

**The name is a misnomer and should not survive the port.** The component is
`Gallery.svelte` (imported as `PhotoGallery` in `Main.svelte:6`), but it is
not a gallery: there is no grid of everything, no scrolling list, no
browsing by recency. It is a **directional viewer** — you stand at the map's
position, face a bearing, and it shows the photo you are facing, with the
photos to your left, right, above and below one swipe away. Call it the view
pane, or the panorama pane.

## What it is, in one sentence

The map decides WHERE you stand; the bearing decides WHICH WAY you look; this
pane shows WHAT YOU SEE, and turning to another photo *is* turning the view.

That last clause is the whole design. Navigating in this pane does not select
a photo — it **writes the app's bearing** (`turn_to_photo_to` →
`updateBearingWithPhoto(photo, 'photo_navigation')`,
`data.svelte.ts:337-360`). The map's arrow, the marker fade and the capture
stamp all follow from the same value. In frontend2 that means the pane is a
writer into `MapStateHolder`, alongside the compass and car mode — never a
holder of its own bearing.

## The pipeline, outermost first

```
photosInArea              all loaded photos, any distance
  → cullPhotosInRange()   within `range` metres, angularly spread, ≤300
  → sortPhotosByBearing() bearing ascending, uid as tiebreak
  = photosInRange
  → filter               (filtered / featured, per hunter mode)
  = navigablePhotos       the ring you navigate
  → nearest bearing      = photoInFront
  → ring ±1              = photoToLeft / photoToRight
  → pitch within ±5°     = photoUp / photoDown
```

### `range` is a screen measurement, not a preference

`Map.svelte:650-667`. `get_range()` converts **70 screen pixels** into metres
at the current map centre and zoom: it takes the centre's container point,
adds `fov_circle_radius_px = 70` to x, converts back, and returns the
distance. Falls back to 1000 m before the map exists.

So the range circle is fixed on screen and elastic on the ground: zooming out
widens it in metres, and the pane's photo set changes as a consequence.
Nothing else sets it.

### `cullPhotosInRange` — uniform angular coverage, not nearest-N

`AngularRangeCuller.ts`. The problem it solves: if you took 200 photos facing
one landmark, a nearest-N cull would fill the ring with that landmark and you
could not turn anywhere else. So:

- **36 buckets of 10°**, indexed by the photo's own `bearing`
  (`getBucketIndex`, normalized).
- Photos are bucketed only if `distance <= range` (great-circle,
  `calculateDistance`), and each keeps `range_distance`.
- **Picks are exempt and come first**: any photo whose uid is in `picks` and
  is within range is included before bucketing and excluded from it. Picks
  are the front photo plus the timeline's pinned set
  (`mapState.ts:251-268`), which is what keeps the photo you are looking at
  from being culled out from under you.
- The rest are taken **round-robin across buckets**, one per bucket per
  round, exhausted buckets swapped off the end — so coverage is even in
  angle rather than dense where the photos are.
- Cap is `maxPhotos = 300` (`mapState.ts:191`), picks counting against it.

Recomputed only when the centre or the range actually changes
(`mapState.ts:178-197`), not on every bearing tick.

### `sortPhotosByBearing` — the ring's order

`AngularRangeCuller.ts:172`. Ascending `bearing`; ties broken by
`uid.localeCompare` so the order is stable across sources and reloads. The
whole left/right navigation is index arithmetic on this order, so the
tiebreak is load-bearing, not cosmetic.

### `navigablePhotos` — what hunter mode hides

`mapState.ts:147-153`:

- `overrideFilters` on → everything in range;
- otherwise drop `p.filtered`;
- and if hunter mode is OFF while any featured photo is in range, keep
  **only** featured ones.

The last rule is the surprising one: with hunter mode off, a single featured
photo in range collapses the navigable ring to the featured subset.

Note where "any featured" comes from: `anyFeatured` is
`featured === true && !filtered` over `photosInRange` (`:127-130`) — decided
over the in-range set, BEFORE the override, not over the list the override
produced. So a featured-but-filtered photo does not become a featured set
just because the user overrode the filters. Computing it from the
post-override list looks equivalent and is not.

### `photoInFront`

Two stores, not one. `newPhotoInFront` (`mapState.ts:208-245`) is the
derivation; `photoInFront` is a writable mirror updated **only when the uid
changes** (`:247-252`). That guard is not an optimisation — the same block
rewrites `picks` and fires analytics, so re-emitting an identical photo would
churn the map's highlight. Port the guard with the rule.

The derivation has two ways in:

1. **Explicit**: `bearingState.photoUid` names a photo AND its bearing
   differs from the current bearing by exactly 0 — i.e. we turned to it and
   have not moved since. This is what makes a chosen photo stick.
2. **Nearest bearing** otherwise: smallest `calculateAbsBearingDiff`, ties
   broken by smaller uid.

Null when the navigable ring is empty.

### `photoToLeft` / `photoToRight`

`mapState.ts:270-297`. Index of the front photo in `navigablePhotos`, ±1,
**modulo the length** — the ring wraps, so turning past north keeps going.
Null when the ring is empty, has one element, or no longer contains the front
photo.

Note the direction mapping in the UI: swiping LEFT goes to the photo on the
RIGHT (`Gallery.svelte:45-56`), as with any drag-the-content gesture.

### `photoUp` / `photoDown`

`mapState.ts:299-360`. Same view direction, different elevation:

- candidates are `navigablePhotos` within **5° of the front photo's
  bearing** (`bearingThreshold`), excluding the front photo itself;
- `up` wants strictly greater `pitch` (missing pitch = 0) and takes the
  **largest**; `down` wants strictly smaller and takes the **smallest**;
- and if the winner is already `photoToLeft` or `photoToRight`, it is
  **suppressed** (returns null) so a photo never occupies two slots.

## The layout

`Gallery.svelte:163-172`. Five slots in one grid, keyed and classed
`['up','left','front','right','down']`, each holding a `Photo` or nothing.

The geometry is the part that matters and is easy to get wrong. The grid is
**300% x 300%, offset `left:-100%; top:-100%`** (`:258-262`): nine cells, each
the size of the viewport, with `front` (col 2, row 2) sitting exactly over the
visible area and the four neighbours in the cells around it, off-screen.
`swipe2d` translates **the whole grid** (`transformTarget: photosGrid`, 0.3s
cubic-bezier on snap), so a drag physically pulls the neighbour into place.

The consequence for images: **neighbours are not thumbnails**. Every slot is
viewport-sized, so each `Photo` asks for the same width the front one does,
and a swipe reveals an image that is already loaded at display size. The
prefetch is a consequence of laying the neighbours out for real, not a
separate mechanism — and any port that renders neighbours small to "save
bandwidth" gets a visible pop on every swipe instead.

## Choosing an image

`Photo.svelte` is handed the WHOLE photo, not a URL, and picks per slot
(`updateSelectedUrl`, `:145-190`): of the numeric `sizes` keys ascending, the
first at least as wide as the container; else `full`; else the widest numeric;
else the bare `photo.url`. Device photos resolve through `getDevicePhotoUrl`.

It also swaps progressively (`handleImageChange`, `:203+`): the newly chosen
URL is loaded into an off-screen `Image` and `displayedUrl` only changes once
it is ready, so a resize or a size upgrade never blanks a slot that already
had something in it.

So the model has to carry every rendition. One chosen URL cannot work: the
same photo is a neighbour in one slot and the front photo in another, and the
container width is the slot's business, not the photo's.

- Gesture: `swipe2d` with `snapThreshold: 50`, `dampingFactor: 1.0`, and
  `canGoLeft/Right/Up/Down` gating from the four neighbour stores, so a drag
  toward an empty slot does not rubber-band.
- Chevron buttons duplicate all four directions (`gallery-nav-left`,
  `-right`, `-up`, `-down`), rendered only when that neighbour exists.
- Empty state (`:109-135`): a spinner while `anySourceLoading`, otherwise
  "No photos within the range circle" with a hint to zoom or pan, links to
  `/bestof` and `/activity`, and a button that opens the camera.
- Thumbnail strips exist but are **commented out** top and bottom
  (`:95-107`, `:179-190`), with a surviving click handler
  (`handleThumbnailClick` → `updateBearing(photo.bearing)`). **Disused —
  do not port.** Recorded only so the next reader of `Gallery.svelte` does
  not mistake the dead markup for something the port missed.
- `zoomViewData` is cleared on destroy (`:16-18`) — the zoom view's lifetime
  is tied to this pane being mounted.

## What this means for the port

**Half of it is already Kotlin.** `shared-kt/src/cz/hillview/plugin/
AngularRangeCuller.kt` is a faithful translation of the TS culler — same 36
buckets, same round-robin, same picks exemption — with `sortPhotosByBearing`
beside it (`:173`). It exists because the Tauri app's Kotlin photo worker
computes `photos_in_area` / `photos_in_range` and hands them to the WebView
(`KotlinPhotoWorker.ts:295`). frontend2 already compiles shared-kt, so the
culling and the ring order come for free, and the two apps cannot drift.

What is NOT in Kotlin is the **navigation layer** — everything from
`navigablePhotos` down: the filtered/featured rules, front selection, ring
±1, the pitch neighbours and their suppression. That lives only in
`mapState.ts` as Svelte stores. It is pure geometry over a photo list, so it
belongs in `commonMain` with host tests next to `MarkerRules.kt`, written
from THIS document rather than re-derived from Svelte.

Inputs frontend2 still needs: a photos-in-area set to feed the culler,
`range` as the 70-pixel measurement (`MapState.range` already documents the
same definition), the `filtered` / `featured` flags, `pitch`, and `picks`.

The one behaviour to get right before any pixels: navigation writes bearing
into the single funnel. Everything else is layout.
