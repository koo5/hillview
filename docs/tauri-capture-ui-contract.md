# Tauri capture UI, as observed — the spec for frontend2's ports

Companion to `tauri-map-ui-contract.md`, same rules: this file records what
the Svelte capture screen actually does, control by control, read out of
the working code. Port from here, not from memory.

## CameraOverlay (`CameraOverlay.svelte`, mounted by CameraCapture)

The glass info panel over the preview. Mounted only while the camera has
no error.

### Placement and material

Absolutely positioned at `top: 60px + safe-area-inset-top, left: 60px`,
max-width 90%, monospace at 0.85rem, radius 8. The panel is a backdrop:
white-tinted background + 1px white border + blur, in six levels.

### Tap cycles the backdrop, never the content

Tapping anywhere on the panel runs `next = current + 2; if (next > 5)
next = 0` over `cameraOverlayOpacity` (persisted, default 3). From the
default the walk is 3 → 5 → 0 → 2 → 4 → 0 → …, i.e. it settles into the
{0, 2, 4} cycle; 0 is fully transparent (no background, border or blur).
The rows themselves stay visible at every level — the cycle only trades
legibility against how much preview the glass eats.

### Content, by priority

1. **Post-open hint**, 4 s: `doCalibrationHint()` fires on a
   requestAnimationFrame right after the camera stream starts; a repeat
   call restarts the 4 s timer. Suppressed while the bearing- or
   location-tracking hints are showing (those outrank it). Content by
   bearing mode:
   - car: a `BearingStateArrow` graphic + "Adjust the bearing arrow." +
     "Verify location."
   - walking: the `CalibrationFigure` figure-8 + "Calibrate compass." +
     "Verify orientation." + "Verify location."
2. **Location error**: ⚠️ + the message.
3. **Location rows** (when `locationData` exists):
   - row 1: `🧭 <bearing.toFixed(1)>°` (only when bearing non-null), then
     `📍 <lat.toFixed(6)>°, <lon.toFixed(6)>°`
   - row 2 (if altitude non-null): `⛰️ <altitude.toFixed(1)>m`
   - row 3 (if accuracy truthy): `🎯 ±<accuracy.toFixed(0)>m`
4. **Fallback**: spinner + "Getting location...".

### Where the numbers come from (and the honesty note)

In Tauri, `locationData` is fed from **bearingState + spatialState** — the
map state — so the displayed position is the *pairing* position: the fix
under ACTIVE tracking, the map position when parked. Altitude/accuracy are
null on that path and only appear when a capture-time GPS path fills them.
frontend2 should show the **effective capture position** (the claimed
manual position when `manualLocationWins`, else the fix) — same semantics,
honestly labelled.

### Dead code — do not port

Commented-out blocks for per-sensor accuracy (mag/acc/gyro), compass
accuracy label, and compass lag (`getLagColorClass`: ≤200 good, ≤400
medium, ≤600 poor, else bad). `sensorAccuracy`/`compassLag` imports are
alive only for these corpses.

### testids

`location-overlay` (the panel, role=button), `calibration-hint`.

## Camera & resolution selector (`CameraCapture.svelte` lower-left 📷)

A 📷 button (lower-left of the camera view) toggles a dropdown;
click-outside closes it. Inside:

- Every enumerated camera as a row: facing emoji (🤳 front / 📷 back /
  📹 unknown), label, ⭐ on the preferred back camera. Tapping selects the
  camera — and **clears the stored resolution** (per-camera choices don't
  transfer).
- Under the *selected* camera only: its resolution options, with a
  per-camera loading spinner and empty/error states. The punchline the
  machinery hides: `getCameraSupportedResolutions` returns a **hardcoded
  list** — 4K (3840×2160), 1440p (2560×1440), 1080p (1920×1080),
  720p (1280×720) — because the web cannot enumerate sensor modes.
- Selection is persisted (`selectedResolution`, matched by width for the
  highlight; `selectedCameraId` likewise) and applied by restarting the
  camera with a `width: {ideal}` constraint; default is 1440p when nothing
  is saved; a resolution that makes the camera fail to start is cleared.
- testids: `camera-option-<deviceId>`, `resolution-option-<w>x<h>`.

**frontend2 divergence (deliberate)**: CameraX can enumerate the real JPEG
output sizes (StreamConfigurationMap), so the port offers actual sensor
modes instead of the hardcoded four, plus an explicit "Auto" (CameraX's
own choice under MAXIMIZE_QUALITY). Camera *enumeration/selection* (the
front/back/multi-lens rows) is not ported yet — the menu structure leaves
room for it.

## Capture pane layout — the video IS the pane

`CameraCapture.svelte`'s structural rule: `.camera-content` fills the pane
and every control is `position: absolute` **over the video**. There is no
control row below the stream, no scrolling, and no dialog anywhere:

- **Video**: `.camera-view` takes the whole pane (`flex: 1`). frontend2
  uses `PreviewView.ScaleType.FILL_CENTER` (centre-crop) so the stream
  fills the pane at any split ratio — round-4 phone feedback; the saved
  photo keeps the full sensor frame, only the preview crops.
- **Pill** (CameraOverlay): `top: 60px; left: 60px` — clear of Main's
  floating hamburger/camera row.
- **Shutter**: `.shutter-container` absolute `bottom: 6px`, centred — a
  dark pill (`rgba(0,0,0,0.5)`, radius 40) holding a 70px blue circle
  (`DualCaptureButton`). Plain tap = one shot. **300 ms long-press expands
  extra mode controls in place** (slow 10 s / fast 2 s continuous; release
  over one starts it, tap again stops); a run shows a blue count badge and
  a "Stop" label, and pulses green/red by mode.
- **📷 selector**: absolute lower-left; dropdown opens upward.
- **Power saving** (Leaf): a 38px translucent circle, absolute top-right
  at `top: 52px` (the very corner belongs to debug toggles).
- **Calibrate Compass**: red button, absolute, centred above the shutter.
- **Auto-upload prompt** (`AutoUploadPrompt.svelte`): an absolute floating
  card top-left (`top: 80px; left: 1rem`), dark translucent — one red
  "⚙️ Configure auto-upload" button + an × dismiss. **Never a dialog.**
  Auto-hides after 12 s in the app (the × alone sets the session
  dismissal); `neverAskAgain()` exists in the source but no button renders
  it — the settings screen owns that switch.

- **Queue indicator** (`CaptureQueueIndicator.svelte`): absolute
  `bottom: 6px; right: 0` — a dark pill with 💾 + queue size + spinner
  while saves are pending, and `(totalCaptured)`, the session total (its
  stats live in a module singleton = webview-session lifetime). Two
  counters, two meanings: the badge on the capture button counts the
  CURRENT run; the corner counts the whole session.

**frontend2 divergences (deliberate, round 4)**: the slow/fast pair is a
continuous 0–60 s vertical interval slider driven by the ORIGINAL's
one-finger grammar — hold 300 ms and it unfolds beside the still-held
thumb, slide onto it to pick the interval live, release there to start
the run (release back over the button cancels, tap stops a run); the manual
shutter-speed ladder (no original equivalent; added for crisp car shots)
collapses behind
a ⚡ button lower-right, expanding upward like the 📷 selector; the
status/upload-stats lines (no original equivalent) ride under the pill as
dark glass strips.

## Fix freshness — a frontend2 divergence (15 s), not a port

The original has NO fix-age concept. Its capture location is `locationData`
← spatialState: under ACTIVE tracking that is "the last fix ever received",
however old — walk into a tunnel and photos keep geotagging from the
pre-tunnel fix, still labelled `location_source: 'gps'`, with nothing
recorded about its age. The gate is merely "some location exists". The only
staleness handling is structural: power-saving stamps the live fix instead
of the parked map, and BACKGROUND rides the live fix along as
`alt_location` in UserComment.

frontend2 added `FIX_FRESH_MS = 15 s` (judged at capture time, from the
fix's elapsedRealtimeNanos). Effects — deliberately narrow:

1. the location GATE opens only on a fix ≤15 s old (a stale fused seed
   cannot open it; the map-position lift is the escape hatch);
2. an armed manual position beats a fix older than 15 s (fresh fixes beat
   fallback manual; a claimed position beats everything);
3. the shutter tone degrades past 15 s, and `locationAgeMs` is recorded.

A photo captured after signal loss (fix once fresh, now old, no manual
armed) still geotags from that last fix — same as the original — just
audibly degraded and with the age written down.

Why 15: at the 1 Hz update cadence, 15 missed updates means the signal is
genuinely gone rather than jittering; and at walking pace 15 s ≈ 20 m —
the same order as GPS accuracy, so a fix that age still means "here".
The log-and-pair design (capture backlog) supersedes point-in-time
freshness eventually: post-hoc interpolation over the GeoTrackingManager
table dates each photo's position properly.

## /device-photos route, as observed (for the frontend2 port)

Data: `cmd.get_device_photos {page, page_size: 50}` — the shared Room DB,
newest first, paginated. Structure:

- Header "<platform> Photos" + a Refresh button (`refresh-button`).
- DevicePhotoStats: counts by upload status.
- `photos-grid` of `photo-card`s: thumbnail (`photo-thumbnail`, the actual
  file) with a colored status overlay — Completed #10b981 / "upload
  Pending" #f59e0b / Uploading #3b82f6 / "upload Failed" #ef4444, else
  gray; file name + a per-photo ⋮ menu (`photo-menu-button` — the
  anonymization menu); detail rows: Size (B/KB/MB/GB, toFixed(2) with
  trailing zeros stripped), Date, Time (locale), Location (only when not
  0,0; 6 decimals), Bearing (1 decimal, only when non-null), Dimensions,
  Retries (only when >0); the file path (Tauri only); a RetryUploadsButton
  per card — shown when the photo isn't completed, actually a GLOBAL
  retry: `cmd.retry_uploads` → PhotoUploadManager.startAutomaticUpload
  ("retry_button") (bypasses wifi-only). When auto-upload is off or logged
  out it degrades to the hint "Enable auto-upload in settings to retry
  failed uploads."
- `load-more-button` while has_more; `no-data` empty state; `error-message`.

frontend2 divergences (deliberate): the anonymization ⋮ menu is NOT
ported yet (server-side flow, its own phase); date/time use the device
locale via java.text; the screen is reached from the hamburger menu
directly (`menu-device-photos`) — the original nests it under /photos.
