# frontend2 capture backlog — the widgets and the camera question

What the Tauri capture screen has that frontend2 does not yet, so none of
it slips (source components named for the eventual port; observe them
before reimplementing, per the contract method).

## Widgets to port

- **Camera overlay** (`CameraOverlay.svelte`, 396 lines): the
  bearing/location/hint layer drawn over the preview — live bearing
  readout, fix state, and the capture hints. Port it the way the map went:
  read the component, write the contract section, then implement.
- **Compass calibration overlay** (`CompassCalibration.svelte` +
  `CalibrationFigure.svelte`): the figure-8 sheet. The trigger rule is
  already in docs/tauri-map-ui-contract.md — walking-mode compass active
  and magnetometer accuracy != 3, auto-dismiss 1.5 s after it stops being
  needed, never in car mode. The map side already receives accuracy from
  EnhancedSensorService, so the signal exists; only the overlay is missing.
- **Eco / power-saving mode**: the green badge on the location button is
  drawn already (`powerSaving` flag in MapOverlayUi) but nothing sets it.
  Contract: power saving behaves like BACKGROUND after one initial sync —
  "map catches up after each capture"; tooltip text "power saving: map
  catches up after each capture".
- **Resolution menu**: the Tauri app enumerates per-camera supported
  resolutions (`getCameraSupportedResolutions`, cached, with a loading set
  per camera) and persists `selectedResolution`. frontend2's CameraX path
  currently takes the default. CameraX offers `ResolutionSelector`; the
  menu should show real sensor modes, not a hardcoded list.
- **Capture queue indicator** (`CaptureQueueIndicator/Status.svelte`):
  upload-queue depth on the capture screen.

## The camera-control question — research findings (2026-08-06)

Researched (agent report, primary sources). The short version: **stay on
CameraX, skip OpenCamera entirely, mine two Apache-2.0 apps for code.**

- **OpenCamera is GPL-3.0-or-later** — linking it (or porting its code)
  would relicense the app. It is a monolith, not a library, and there is no
  permissively-licensed fork. Reference-reading only, never copy.
- **CameraX 1.6.1 stable covers everything hillview actually needs**:
  tap-to-focus (`FocusMeteringAction`), exposure compensation, AE/AWB lock,
  `ResolutionSelector`, torch strength, video incl. HDR/slow-motion,
  RAW/DNG (`OUTPUT_FORMAT_RAW_JPEG`, since 1.5). `camera-compose` is stable
  (a `CameraXViewfinder` composable), and **1.7.0-alpha02 ships built-in
  tap-to-focus + pinch-zoom gestures** on it.
- What CameraX cannot do natively: manual ISO / shutter / focus distance /
  white balance — those need experimental `Camera2Interop` per-feature, the
  recommended pattern over raw Camera2. Exposure/focus **bracketing** and
  **panorama** have no permissive library at all (DIY on Camera2
  `captureBurst` + NDK stitching) — not on hillview's roadmap anyway.
- **Code to mine (both Apache-2.0, both alive)**:
  - `google/jetpack-camera-app` — Google's full CameraX+Compose reference
    app; the architectural template for the capture screen.
  - `LineageOS Aperture` — production CameraX camera app; liftable
    `LevelerView`, grid, lens selector, countdown, QR (views not Compose —
    take the logic).
- **KMP options** if iOS ever matters: Kamera (CameraK) 1.1 and Camposer
  1.0.3, both Apache-2.0, both CameraX-backed on Android — so dropping down
  for pro features stays possible.
- **Dead, do not adopt**: CameraView, Fotoapparat, google/cameraview,
  CameraKit, EasyCamera, peekaboo.

Still in flight: a second report on PiP/ForegroundService constraints
(Android 14+ `foregroundServiceType=camera`), video with per-frame
metadata, and Compose tap-to-focus sample specifics.

## The camera-control question (original framing)

Users expect native-camera behaviours: tap to focus/expose, exposure
slider, and eventually a video mode. Options under research (see the
research report when it lands):

1. **Stay on CameraX**, add `FocusMeteringAction` for tap-to-focus,
   exposure compensation API, `ResolutionSelector`, `VideoCapture` for
   video; drop to `Camera2Interop` per-feature when CameraX has no knob.
2. **Raw Camera2** for full manual control (ISO/shutter/focus distance) at
   the price of device-quirk hell.
3. **Base on / borrow from OpenCamera** — GPLv3, so linking it in would
   relicense the app; likely only useful as a reference implementation,
   not a dependency. To be confirmed.
4. **PiP / ForegroundService route**: hillview shows the orientation map
   as a floating window while the *native* camera app records. Sidesteps
   camera control entirely for video; needs
   `foregroundServiceType=camera` rules and PiP constraints checked
   (Android 14+ tightened both). Already on the roadmap as the eventual
   fallback.

Known constraint from the clock-video work: the KMP recorder
(frontend2 clockvideo) already does CameraX `VideoCapture` +
per-frame-ish timestamps and was emulator-verified — whatever the video
mode becomes, it should share that stack rather than grow a second one.

Known CameraX hazard, twice confirmed on API 31 + CameraX 1.6: the
camera-pipe backend loses still-capture callbacks (watchdog in
`PhotoCapture.capture()` guards it; capture e2e needs API 34+).
