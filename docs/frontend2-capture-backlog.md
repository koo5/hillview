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

## PiP / ForegroundService — research findings (2026-08-06)

Second report, verified against primary sources (AOSP AppOps.md,
CameraService.cpp, behaviour-change docs) and grounded in this repo.

**The float-mode plan (map in PiP over the native camera app) is viable,
and easier than feared:**

- **PiP counts as a visible activity** — the process stays `PROCESS_STATE_TOP`
  with ALL capabilities. While the map floats, hillview keeps GPS + compass
  with **no foreground service at all**. The FGS machinery is only needed if
  we ever want sensors to outlive the PiP window (or record video with the
  screen off).
- Hillview must **release its own camera** in float mode (any TOP camera
  client evicts lower ones — that is the by-design eviction path in
  `CameraService`), which the plan already intended: the native app records.
- Guard `onPause()` with `isInPictureInPictureMode` — PiP pauses the
  activity but keeps rendering.

**If/when a camera-typed FGS is wanted (background video recording):**

- `foregroundServiceType="camera"` is the supported mechanism; **no timeout**
  through API 37 (unlike dataSync's 6 h/24 h).
- Hard rules: must be started **while an activity is visible** (API 34+
  throws `SecurityException` otherwise, and `checkSelfPermission()` lies —
  it returns granted even when the start would throw); **no auto-start after
  reboot** (Android 15 put `camera` on the `BOOT_COMPLETED` blocklist);
  runtime CAMERA permission must exist before `startForeground()`.
- CameraX must bind to a **`LifecycleService`**, not the Activity —
  ON_STOP suspends use cases. **Repo grounding: both of our camera paths
  (PhotoCapture.android.kt:179, ClockVideoRecorder.android.kt) currently
  bind to the Activity lifecycle**, so the camera closes at ON_STOP today.
- Build for eviction: `onDisconnected` → close → reopen on
  `onCameraAvailable`; segment recordings so eviction costs one segment.
- Users can kill the app from the Task Manager with **no callback**
  (detect post-hoc via `ApplicationExitInfo`); FGS notifications are
  dismissible since 14; indicators always show — covert capture is
  impossible by design.
- Play gates: FGS **declaration + demo video** required (TYPE_CAMERA has
  exactly one preset use case, "background camera streaming"); mandatory
  in-app prominent disclosure before the permission ask; battery-optimization
  exemption requests are policy-prohibited for recorders; **target API 36 by
  2026-08-31** (same deadline as the Tauri Play pass).
- Watch-items: Android 16 bucket-limits jobs running concurrently with an
  FGS (move uploads to user-initiated data-transfer jobs if they must ride
  along); Android 17 app **memory limits** are exactly the risk profile of a
  long-running video encoder.
- Repo corrections from the report: minSdk is **24** (not 26), targetSdk 36
  already — every Android 14/15 rule above applies now. Neither manifest
  declares a camera FGS type yet (only dataSync for WorkManager).

Still open (research agent hit the spend limit before covering it): video
recording with **per-frame metadata** — whether CameraX VideoCapture exposes
frame-timestamp callbacks or MediaCodec/Camera2 is needed. Partly moot: the
clockvideo recorder already burns per-frame QR timestamps via
OverlayEffect(VIDEO_CAPTURE) and is emulator-verified.

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
