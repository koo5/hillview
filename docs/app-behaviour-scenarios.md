# App behaviour, as the test suites define it

Extracted from the Appium suite (`frontend/tests-appium/specs/`, 27 specs)
and the map/capture half of the Playwright suite
(`frontend/tests-playwright/`).
Where the source tells you *how* the app works, these tell you what it is
*supposed to do* — including rules that only exist as an assertion plus a
comment explaining which bug it was written for. Companion to
`docs/tauri-map-ui-contract.md`, which covers the map UI's structure.

Written while porting to frontend2; the last section lists where the port
currently disagrees.

## Capture

- Opening the camera asks for **location permission first**, then shows an
  in-app gate (`allow-camera-btn`) whose tap triggers the **system camera
  prompt**. Reopening later shows the shutter directly, no prompts.
- The camera button is a **toggle**; capturing must not navigate away or
  unmount the shutter.
- The shutter **disables itself while a capture is in flight** and re-enables
  when the pipeline is free — the burst test clicks 50 times, each blocking
  on that, at roughly 4 s per round trip.
- Closing the camera **must not lose in-flight captures**.
- After the first capture an auto-upload prompt appears in the camera view
  (`configure-auto-upload`) leading to upload settings, where the
  auto-upload radios stay **inert until the licence is accepted**. Choosing
  "Disabled (never prompt)" suppresses the overlay entirely, *"so the
  capture-then-prompt overlay doesn't block rapid-fire clicks"*.
- Every capture must reach the device photo DB: 50 captures ⇒ 50 rows
  within 30 s.

### Storage preference is a hint, not a promise

The spec asserts the saved path matches *one of* the three shapes, not the
chosen one, and says so outright: *"Which method actually wins depends on
the Android API level and the app's runtime state, and a given preference
won't always land in its 'named' location — that's by design… What this
spec does NOT assert: that the preferred method is the one that actually
ran."* A save must never silently fail. Both `Hillview` and hidden
`.Hillview` are valid.

## Upload

- **Coalescing.** A burst of N captures must collapse to ~1 worker run, not
  N: *"a burst of N captures produced ~N workers each churning
  SystemForegroundService on the main thread, which froze the UI for minutes
  and could crash with ForegroundServiceDidNotStartInTimeException"*. The
  test bounds it at 1–3 runs for 20 captures, and asserts the UI stays
  responsive throughout.
- **Foreground drains stay silent.** Promotion to a foreground service — and
  therefore the "Uploading Photos" notification — happens **only while the
  app is backgrounded**. Zero promotions during a foreground burst is an
  assertion, not an accident.
- **Offline.** Capture must succeed with no network; nothing reaches the
  server; on reconnect the queue drains within 90 s.
- **Worker down (503).** The photo stays pending — not dropped, not marked
  done — and uploads once the fault clears.
- **Counting rule:** `authorize-upload` creates placeholder rows *before* any
  bytes arrive, so "uploaded" counts must filter to fully-processed photos.

## Map and bearing

- Required gestures: pan, pinch zoom, and **two-finger rotate**. No
  combination of them may wedge the map.
- `bearing-arrow-hitarea` exposes the current bearing through
  **`aria-valuenow`** — the only externally readable bearing in the app.
- **Long-press the compass button (≥500 ms)** opens the mode menu, and
  picking a mode **turns tracking on as a side effect**
  (*"selectBearingMode() inside bearingTracking.ts turns gps orientation ON"*).
- Car mode: driving the emulator east must move the indicator to within 45°
  of east. The filter needs speed > **1.5 m/s**, movement > **10 m**, and
  fixes spaced ≥ **1 s**; tolerance is loose because *"FusedLocation mixes in
  its own smoothing"*.
- **Bearing must survive backgrounding** — byte-identical `aria-valuenow`
  after a 5 s background.
- Markers are `photo-marker-<id>` carrying `data-photo-id`,
  `data-is-placeholder` and `data-source`.

## Location tracking

The three-state button, asserted through its CSS class:

| From | Trigger | To |
|---|---|---|
| OFF | click | ACTIVE (`active`) |
| ACTIVE | **manual map pan**, not a click | BACKGROUND (`background`) |
| BACKGROUND | click | OFF |
| OFF | click | ACTIVE — *"the cycle is restored, not stuck"* |

In BACKGROUND, GPS stays subscribed and fixes keep being logged tagged
`-background` so they lose the photo-pairing lookup, while the map stops
following.

**Entering capture must re-arm a clean ACTIVE**, and there is a regression
comment saying why: previously it left the background flag set, *"leaving
the button stuck half-blue, GPS still logging '-background', and captures
recording the live fix only as alt_location"*.

Geo export writes `hillview_orientations_<ts>.csv` and
`hillview_locations_<ts>.csv`; auto-export fires on backgrounding and again
at plugin init; the CSV's source column must show both tagged and untagged
rows.

## Auth and session

- **Transient failures must not log out.** A refresh that times out (native
  read timeout ~10 s) or returns **5xx** keeps the session; only a **401**
  clears it. The client proactively refreshes with a **2-minute** buffer.
- **Genuine expiry logs out in lockstep**: native clears the session, the
  WebView is told, and the UI lands on `/login` within 30 s.
- **And it survives process death**: the session-expired flag is
  deliberately *not* cleared by the token clear, so a kill between death and
  delivery still surfaces at next launch as a **persistent** in-app alert
  (duration 0) reading "session has expired".
- A 401 on any authenticated call forces logout within seconds.

## Notifications

- "Login Required" — channel `auth_notifications`, id 1001, within 30 s of
  the worker hitting a 401 it cannot refresh past.
- "Uploading Photos" — id 2001, ongoing for the whole drain, backgrounded
  only.
- Push: foreground delivery posts our own notification; **backgrounded
  delivery must stay silent** because Android already auto-displays it;
  killed-from-recents posts ours again. Force-stopped is explicitly out of
  scope: *"Android refuses to deliver any intent … That's a legitimate
  Android guarantee, not something to test for delivery against."*

## Resilience

Must survive: backgrounding (auth, bearing, controls), orientation flips
(no control may be lost in landscape), restarts (permissions, prefs, DB,
session-expired flag). Must not survive: a genuinely 401'd session. An API
failure on the photo list shows an inline error and recovers on remount.

## From the web suite

The Playwright specs cover the same product through the browser, and add
rules the Android suite does not exercise.

### Map controls the port is missing entirely

- **Rotate buttons**, titled "Rotate view 15° counterclockwise/clockwise" —
  the step is exactly **15°** per click (the same step the `x`/`b` keys use
  on Android).
- **Move forward / backward**, which step the view along the current bearing.
- **Turn to the photo on the left / right**.
- **Two-finger rotation** is expected to work alongside these.

### Selection is a first-class concept

- Exactly one marker is the front photo and carries `.bearing-circle
  .selected`; the gallery shows it. The choice is *"the bearing-closest
  in-range photo (uid tiebreak)"*.
- The current selection is **pinned**: with `maxPhotosInArea = 3` and four
  photos where the other three are featured, the selected non-featured photo
  must still be visible after an area refresh, because *"the picked photo
  (non-featured) would be dropped WITHOUT picks support"*.
- Clicking a greyed (filtered-out) marker auto-enables hunter mode and
  un-greys it.
- Arriving at a URL whose photo is featured leaves hunter mode **off**; a
  non-featured one turns it **on**.

### Filters affect markers by greying, never by removing

With "show unanalyzed" **off**, every marker gains `.grayed` — the count of
greyed circles equals the marker count — and re-checking returns it to zero.
The timeline, by contrast, *hard-excludes* them. The modal also disables
"clear filters" and "show unanalyzed" while no filter is active, and the
button label carries the active count as `(n)`.

### Capture gating

The shutter becomes enabled only once **both** the preview is ready **and**
a location fix exists (*"implies cameraReady && locationData"*), and it is
disabled again while an upload is in flight — *"If you fire the next
capture immediately, its page reload interrupts the previous upload and the
queue wedges"*. Captured photos take their position and bearing from app
state, not from the image: *"a canvas frame carries no EXIF GPS/bearing, so
the map-centre location and compass bearing we set per capture are
authoritative"* — with the same 141° default bearing seen elsewhere.

### Robustness expectations

Arbitrary pan/zoom/rotate sequences, including five rapid pans 100 ms apart
and continuous circular drags, must leave the map visible with tiles
present. Malformed URL parameters must never crash it. A long list of
console errors is explicitly forbidden (`spatialState`, `bearingState`,
`turn_to_photo_to`, `photosInArea`, …), which is really a statement that
those code paths must not throw under gesture load.

---

## Where frontend2 disagrees today

Found by reading the above against the port; unfixed unless noted.

1. ~~Bearing is not persisted.~~ **Fixed**: a `MapStateStore` seam restores
   camera and bearing (including the intent timestamp) at open and saves on
   change, with tests.
2. ~~Picking a bearing mode does not enable tracking.~~ **Fixed**: choosing
   a mode now stops the old tracker and starts the new one.
3. ~~No `aria-valuenow` on the arrow.~~ **Fixed**: the arrow publishes its
   bearing through Compose semantics (`ProgressBarRangeInfo` plus a spoken
   description).
4. ~~Markers carry no identity.~~ **Fixed**: each photo emits a
   `photo-marker-<id>` semantics node at its drawn position (rose members
   anchor on their own tick); selection state rides along as
   `stateDescription`.
5. ~~Entering capture does not re-arm location tracking.~~ **Fixed**:
   tracking state moved to a process-wide MapSession; entering capture arms
   a clean ACTIVE, leaving stands bearing tracking down. Emulator-verified.
6. ~~No auto-upload prompt, no licence gate.~~ **Fixed**: licence is null
   until accepted (the shared stack refuses uploads without one), the
   auto-upload switch stays inert until then, and the after-capture
   `configure-auto-upload` prompt has Set up / Not now / Never ask with the
   never flag persisted. Emulator-verified.
7. ~~No two-finger map rotation.~~ **Fixed**: RotationSyncOverlay +
   orientation in SpatialState (persisted); an ↑N badge resets north.
   Device-tested with real two-pointer MotionEvents.
8. ~~Session-expired notice not persistent, wrong wording.~~ **Fixed**:
   the persisted flag now survives until the user dismisses it or signs
   back in, and the text contains the asserted "session has expired".
9. ~~The location button exposes no state.~~ **Fixed**: off/active/
   background published as semantics stateDescription.
10. ~~No rotate/move/turn-to-photo controls.~~ **Resolved by observation**:
    in the current Tauri app those actions are keyboard-only (`x`/`b`,
    `c`/`v`, `z`/`k`) and the on-map buttons for them are documented dead
    code (unreachable from markup — see the contract's "Do not port").
    A phone has no keyboard, so there is nothing to port; two-finger
    rotation covers the rotate case.
11. ~~No photo selection at all.~~ **Fixed**: frontPhoto() picks the
    bearing-closest in-range photo (id tiebreak), taps select via
    markerAtTap() with the selection pinned against the photo limit, and
    marker_click bearings carry the photo uid. Emulator-verified.
12. ~~Filters dialog lacks clear/show-unanalyzed.~~ **Fixed**: both exist
    with the disabled-until-a-filter-is-active gating, desktop-tested;
    greying by filters still awaits the backend photo query.
13. ~~The shutter does not require a location fix.~~ **Decided and fixed**
    (user, 2026-08-07): the requirement is protection for first-time
    users, so it gates by default — and is deliberately liftable
    ("capture at the map position instead") for cases like starting the
    app underground with a hand-positioned map. Lifted captures carry
    location_source "manual"; a fresh fix always wins back.
