# The Tauri map UI, as observed

Written while reimplementing the map screen in frontend2. The point is
fidelity: this file records what the Svelte app actually does, control by
control, so the Compose version can match it instead of inventing something
adjacent. Line references are to `frontend/src/lib/...` at the time of
writing.

## Screen layout

Two separate absolutely-positioned clusters over the Leaflet map
(`Map.svelte:1934+`):

- **top-right** `.location-button-container` (`top:16px; right:54px`,
  z-index 30000): the location button, then the compass button.
- **bottom-right** `.hunter-controls` (`bottom:4px+safe-area;
  right:6px+safe-area`, z-index 30000): a 2×2 grid —
  ```
  .            right-panel      <- source toggles (vertical)
  bottom-panel toggle           <- filters/provider/timeline, then the toggle
  ```
  The panels are only `visible` while `$hunterMode` is on; the toggle button
  itself is always there, in the corner.
- Zoom in/out are Leaflet's own control, re-created so the order is right
  (`Map.svelte:406,412`, testids `zoom-in-btn` / `zoom-out-btn`).
- A `.bottom-gesture-guard` strip covers the bottom safe-area inset with
  `touch-action:none` so the system back-gesture doesn't fight the map.
- Attribution collapses to an ⓘ button + popup when the screen is narrow.

## Map layers, bottom to top

1. `TileLayer`, re-created via `{#key $currentTileProvider}` so a provider
   switch rebuilds the layer. Options come from `tileProviders.ts`
   (`maxNativeZoom` from the provider, `maxZoom` 23-24 so it upscales past
   the provider's depth, `updateInterval:100` to throttle tile updates,
   `preferCanvas:true` on the map for performance).
2. **Range circle** — only when `$app.activity != 'capture'`: centred on
   `$spatialState.center` with radius `$spatialState.range`, colour
   `#4AE092`, white fill, `weight 8.8`, `dashArray [5,15]`.
3. **Photo markers** (see the marker section).
4. **`BearingStateArrow`** in an SVG overlay, hidden while
   `$app.activity === 'terrain'`. Gets `fullCircleHitArea` when
   `$bearingMode === 'car' && $gpsOrientationEnabled`.

## Compass button (top-right, `CompassButton.svelte`)

The richest control on the screen.

- **Short tap** → `toggleTracking()`: if `$compassEnabled || $gpsOrientationEnabled`
  then `disableBearingTracking()` (which disables BOTH), else
  `enableBearingTracking()` — which starts the compass in walking mode and
  GPS orientation in car mode (`bearingTracking.ts:10-24`).
- **Long press, 500 ms** → opens `CompassModeMenu` (walking / car); picking a
  mode runs `selectBearingMode()` = set mode, disable both, re-enable
  (`bearingTracking.ts:26-30`). On non-touch there is a separate
  `.dropdown-trigger` chevron that opens the same menu; the main area still
  toggles.
- **Visual state is split between intent and reality** — worth copying
  exactly (`CompassButton.svelte:157-186`):
  - `active` ⇐ *user intent*: `(walking && compassEnabled) || (car && gpsOrientationEnabled)`
  - `loading` ⇐ the mode's state machine is `starting`
  - `error` ⇐ that state machine is `error`
  - `unavailable`/disabled ⇐ `walking && !compassAvailable` (car mode is
    never disabled this way)
  - plus `car-mode`/`walking-mode` and `dropdown-open` classes.
- Icon: a compass, with a person/car glyph indicating the mode, and a small
  chevron hinting the menu (a dropdown affordance on desktop, a long-press
  hint on touch) (`CompassButtonInner.svelte`).

## Location button (top-right, left of the compass)

- Click → `handleButtonClick('location', …)`.
- Classes: `active` while `$locationTracking`; `background` while
  `$backgroundLocationTracking`; `flash` briefly on a location API event.
- A **leaf badge** appears when `$powerSavingActive`, and the tooltip then
  reads "power saving: map catches up after each capture".
- Shows a spinner while `$locationTrackingLoading`.
- **Map drag while tracking** calls `enterBackgroundTracking()`
  (`Map.svelte:1944`) — panning away doesn't stop tracking, it demotes it.

## Hunter panel controls (bottom-right, only when `$hunterMode`)

- **Source toggles**, one per `$sources` entry: label = source name, `active`
  class when enabled, an inline spinner while
  `$sourceLoadingStatus[id].is_loading`. Click → `toggleSourceVisibility(id)`.
- **Filters button**: short press opens the filters modal, **long press
  toggles `$overrideFilters`**; `active` when `$activeFilterCount > 0`; label
  shows the count; an `overridden` style when the override is on. Tooltip
  switches between "Filters (long-press to override)" and "Filters
  overridden (long-press to restore)".
- **Tile provider selector**: opens a dropdown listing
  `getAvailableProviders()` (dev-only entries filtered out unless dev mode),
  current one marked selected (`TileProviderSelector.svelte`).
- **Timeline toggle**: `$timelineActive`, keyboard shortcut `t`.
- **Hunter mode toggle** itself: bow icon plus two carets that flip direction
  with the state.

## Map events

`moveend`, `zoomend`, `dragend` → `mapStateUserEvent`; `dragstart` →
`enterBackgroundTracking()` when location tracking is on (`Map.svelte:1941-1944`).

## Bearing tracking: the state machine behind the compass button

Three separate things, deliberately not collapsed (`compass.svelte.ts`):

- `compassEnabled` — what the **user asked for**. Not persisted.
- `compassInternallyActive` — whether the sensor is actually running.
- `compassState` — `inactive | starting | active | error`, with the inline
  gloss: *"'starting' // User enabled, trying to start (permissions, sensor
  init)"*.

Enable: `starting` → clear error → start the sensor → `active`, or on
failure `error`, then **revert the user preference** (`compassEnabled=false`,
back to `inactive`) behind a `revertingUserPreference` recursion guard.
So a failed start un-presses the button by itself.

Persistence, which is easy to get wrong: `bearingMode` and `bearingState`
**are** persisted (`bearingState` debounced 500 ms, default bearing 141);
`compassEnabled`, `gpsOrientationEnabled`, the sensor mode and the car mount
offset are **not** — every session starts with tracking off.

Walking mode pumps the heading into the map bearing only when all of these
hold (`compass.svelte.ts:694-720`): mode is walking, `compassState` is
`active`, the heading is a number, and it moved more than **1°**. It prefers
`true_heading` over `magnetic_heading`, tagging the source accordingly.

Turning the compass **off does not reset the bearing** — the last value
stays and becomes user-controlled again. Only the smoothing state is reset.

Smoothing is deliberately off in the frontend (`SMOOTHING_FACTOR = 0`):
*"smoothing happens in EnhancedSensorService.kt already (and also it only
fires on changes), so smoothing on the frontend would only be useful if we
need to smoothen web compass api"*.

### Car mode

Not "the compass, but different" — a different source entirely. GPS
positions go through a heading filter that rejects speed < 1.5 m/s and
displacement < 10 m (no smoothing, bearing straight from reference →
current). In the Tauri app **Kotlin owns that filter** and emits an already
composed `travel + mountOffset` absolute bearing; the browser path instead
applies only the **diff**, preserving whatever base angle the user set.

The mount offset is the camera's angle relative to travel. Dragging the
arrow in car mode does not set a bearing — it feeds `adjustMountOffset(diff)`,
because *"a jump on first touch would swing the mount offset by however far
from the arrow the grab happened to land"*. That is also why the whole
range circle is grabbable in car mode.

### What disables tracking

Deliberate, and worth reproducing: turn/rotate buttons, arrow drag
(compass only — **not** GPS orientation), photo navigation, the `x`/`b`
keys, and leaving capture activity. Entering capture activity enables it.

### Calibration

`needsCalibration` = walking-mode compass active **and** magnetometer
accuracy != 3 (Android's 0-3 scale). Shows the figure-8 overlay, auto
dismissing 1.5 s after it is no longer needed. Never shown in car mode.

### Do not port

The reading turned up machinery that only looks alive: `sensorAccuracy`,
`compassLag`, accuracy polling and lag monitoring are declared but never
written or called; the Tauri sensor listener is intentionally never
unregistered; `absoluteReadingsCount` is never reset (a latent web-path
bug); `SensorMode.WEB_DEVICE_ORIENTATION` (5) has no native equivalent.
Also: changing the sensor mode while the compass is **active** currently
does nothing, because the state machine only acts from `inactive` — the
Compose port should restart the sensor instead of inheriting that.

## Map state: who owns what

`spatialState = {center, zoom, bounds, range, source: 'gps'|'map', ts?}`
(persisted, written **synchronously** on every change) and `bearingState`
(persisted, **500 ms debounced**). The app is the source of truth for centre
and zoom; the map view is the authority for `bounds` and `range`, which are
always read back from it rather than computed.

`range` is not a setting: it is the distance in metres from the centre to a
point 70 px to its right — i.e. a fixed *screen* radius, so it changes with
zoom. That is what the dashed green circle draws, and what decides which
photos count as "in range".

`ts` marks the last **intentional** update — *"Undefined on a true first
visit — used to decide whether the featured-photo auto-navigation should
kick in"*. A blank first visit lets the featured photo steer the map; any
prior user intent blocks it forever.

### The feedback-loop guards

Store→map and map→store both exist, so every guard matters:

- `programmaticMove` (1 s window) blocks store→map `setView` while a fly
  animation runs.
- `updateSpatialState` dedups by JSON **ignoring `ts`** — the terminal break
  of map→store→map ping-pong. `updateBearing` has **no** dedup.
- `setView` only when centre/zoom actually differ; the upward path diffs
  seven fields (centre×2, zoom, bounds×4) before writing.
- `isZoomButtonEvent` (500 ms) so zoom-button moves are not mistaken for
  user pans: *"Only react to genuine user pans, not programmatic
  zoom-button moves."*
- The photo re-cull watches only `center` and `range` — zoom and bounds
  changes deliberately do not re-cull.

### Bearing writers

There is **no priority table — last writer wins**, and precedence is
enforced upstream by switching the automatic producers off first. Sources
seen in the wild: `url`, `featured`, `arrow_drag`, `photo_navigation`,
`marker_click`, `timeline_step`, `gps-kalman`, `<sensor>-compass-true|
-magnetic`, and plain `map`.

Two behaviours to copy exactly:
- `updateBearing` **clears** `photoUid`/`accuracy_level` when they are not
  passed (this is how a compass tick drops the photo selection), while
  `updateBearingByDiff` preserves them and the current source.
- Bearings that came **from** the native sensor are not pushed back down to
  it: `!source.startsWith('android')` is the echo guard.

### Location tracking is a tri-state

OFF / ACTIVE / BACKGROUND, mutually exclusive. Panning while ACTIVE demotes
to BACKGROUND and deliberately does **not** stop the GPS: *"the GPS
subscription stays up so pulses continue and fixes keep logging (now tagged
background). The map stops following because locationTracking is false"*.
Power saving behaves like BACKGROUND after one initial sync, so entering
capture doesn't leave the map parked somewhere unrelated.

There is even an ordering guarantee around it: a pending ACTIVE→BACKGROUND
logging switch must land before the manual `map` location is written,
*"otherwise a late foreground GPS row could beat the manual location in the
external-photo 'latest non-bg entry wins' pairing"*.

### Hunter mode

`hunterMode = override ?? preference`. The preference is persisted; the
override is a session-only one-shot set when arriving via a `?photo=` URL
(on for a non-featured photo, off for a featured one). Clicking a marker
flips it the same way — except during a timeline walk, where *"the timeline
owns hunter mode … or stepping onto a featured photo would drop us back to
tourist mode and break the next non-featured step"*.

## What a photo marker is

Not a dot. Three stacked pieces per photo (`optimizedMarkers.ts`):

1. a 5×5 px **cross** marking the true GPS point;
2. a **bearing circle**, 19.2 px (32 px when selected);
3. a **direction arrow** sprite, 32 px, white with a black outline, taken
   from an atlas of 24 pre-rendered orientations — so bearings are quantised
   to 15°.

The whole thing is pushed **7 px forward along the photo's bearing**, and
the cross counter-translates by the same amount so it stays exactly on the
coordinate. The circle sits ahead of where the photographer stood.

### Colour carries meaning

- **Fill = how closely the photo's bearing matches the current view
  bearing**: `hsla(120, 100%, 70%, 1/step)` with `step = round(diff/28.57)`.
  Same direction → opaque green; pointing away → fading toward transparent.
  Featured photos are **gold** and never recoloured.
- **Border = the source**: hillview black, mapillary grey, panoramax teal,
  device green.
- **Greyed** (`grayscale(1) contrast(20%)`, container opacity 0.45) when the
  photo is filtered out and override is off, **or** when featured photos
  exist and this non-featured one is *inside the range circle* — outside it,
  non-featured photos are not greyed.
- **Stacking is explicit** because markers are pooled: filtered −100000 <
  regular 0 < featured 500000 < selected 1000000.

### The two cullers

- **CullingGrid** decides what is drawn: a 10×10 grid over the viewport,
  round-robin one photo per cell per source, until `maxPhotosInArea` (100 by
  default) is reached — *"prevents visual clustering and ensures good screen
  coverage"*. Device photos are sorted newest-first so an over-full cell
  keeps the recent ones, and `picks` (the selected photo, timeline pins)
  always survive.
- **AngularRangeCuller** decides what is *navigable*: 36 buckets of 10°, by
  the photo's **own** bearing, among photos inside `range`, so that "you can
  look in all directions". Its output is sorted by bearing, which is what
  makes left/right stepping angular.

### Update cadence

Three separate paths, deliberately not one:

- full rebuild only when the photo list changes (`visiblePhotos` snapshots
  the bearing non-reactively, so bearing changes never rebuild markers);
- **colour-only** repaint on bearing change, leading-edge throttled to
  **300 ms** (3000 ms during capture) and batched into one animation frame,
  with CSS transitions deliberately disabled: *"No transitions for instant
  color updates - prevents UI freeze"*;
- selection-only and greying-only passes that touch just the affected
  markers.

### Tapping a marker

Event delegation on the container, 10 px tap threshold. Then: flip hunter
mode by the photo's featured-ness (unless a timeline walk owns it), turn on
`overrideFilters` if a filtered photo was tapped, and — if the photo is
already in range — only turn the view to it; otherwise fly the map there
(duration capped at 250 ms, instant if a programmatic move is already in
flight).

### Capture mode differs

Range circle hidden, no marker drawn as selected, bearing recolouring off.

## Gestures, and the guards around them

- **Edge-drag guard**: a touch starting within **40 px of any container
  edge** disables map dragging until that touch ends — *"Prevent drags from
  touch events starting near screen edges (accidental touches while holding
  phone)"*. Plus the inert `bottom-gesture-guard` strip over the safe-area
  inset so the system back-swipe doesn't pan the map.
- **Wheel zoom is hand-rolled on Android** (Leaflet's is disabled there):
  ±0.5 zoom steps anchored at the cursor, with dragging temporarily disabled
  for 100 ms to stop the wheel from panning.
- **Zoom buttons are not user pans**: pressing one sets `isZoomButtonEvent`
  for 500 ms so the move doesn't demote location tracking to background, and
  re-arms tracking 200 ms later.
- Tap vs drag on markers is a **10 px** threshold, and the touch handler
  deliberately does not `stopPropagation` — *"Leaflet's document-level
  touchend handler must fire so it cleans up its drag state. Otherwise its
  stale document-level touchmove handler intercepts subsequent swipes in the
  gallery and pans the map."*

## The arrow, exactly

- Tip is the **range-circle edge projected along the bearing**, at
  `range × 1.3`, computed geographically then projected to screen — *"This
  accounts for Mercator distortion so the arrow always touches the circle
  regardless of direction"* — and it uses the map's **live** centre during a
  drag, because the stored centre only settles on `moveend`.
- Grab area is a transparent 30 px-wide stroke over the **outer third** of
  the arrow; in car mode an additional 36 px-wide invisible **ring** on the
  range circle, with `pointer-events: stroke` so the disc inside stays free
  for panning and marker taps.
- It is `role="slider"` with `aria-valuenow` — worth keeping for
  accessibility parity.

## Keyboard (lives in Main.svelte, not the map)

`z`/`k` turn to the photo left/right, `x`/`b` rotate ∓15° and `X`/`B` ∓1°
(each disabling bearing tracking first), `c`/`v` step the view forward and
back by 70 px along the bearing, `t` toggles the timeline, `,`/`.` walk it
older/newer, `Esc` closes it, `i` toggles the info window, `d` cycles debug,
`s`/`m` toggle sources. All bail out when focus is in a text field.

## Do not port

`Map.svelte` carries a dead slideshow (timer, long-press handlers, styles)
and a `handleButtonClick` whose `left/right/rotate/forward/backward` actions
are unreachable from its own markup — those actions now arrive via the
keyboard. There are also several unused imports and a
`removeEventListener('orientationchange', () => {})` that passes a fresh
closure and therefore removes nothing. The `spatialState.subscribe` in the
map is never unsubscribed on destroy, so a remount adds another one — scope
it to the screen's lifecycle in the port rather than copying it.

## Filters (the modal)

Max photos in area (10–1000, default 100, stepper — not part of the filter
count), then single-select chip groups: time of day, location type, minimum
view distance, maximum close-object distance, scenic score, visibility
distance, tallest building; a multi-select feature list (OR logic, ~40
features in 7 categories); "show unanalyzed photos" (default on, disabled
until some filter is active); and clear-all. Chips are toggles — tapping the
selected value clears it.

The badge counts the chip groups only. Filtered photos are **not removed by
the backend** — they come back flagged and sorted into tiers (featured,
passing, unanalyzed, filtered-out), which is what makes the grey-out and the
long-press override possible client-side.

