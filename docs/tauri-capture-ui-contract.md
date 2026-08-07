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
