# frontend2 capture backlog — the widgets and the camera question

What the Tauri capture screen has that frontend2 does not yet, so none of
it slips (source components named for the eventual port; observe them
before reimplementing, per the contract method).

## Widgets to port

- ~~Camera overlay~~ **DONE 2026-08-07**: observed into
  docs/tauri-capture-ui-contract.md, then ported — glass panel with the
  six-level tap-cycled backdrop (persisted), 4 s post-open hint per
  bearing mode, bearing/lat/lon/altitude/accuracy rows showing the
  *effective* capture position (claimed manual position marked as such).
  Dead code (sensor accuracy, compass lag) not ported.
- ~~Compass calibration overlay~~ **DONE 2026-08-07**: trigger rule +
  figure-8 sheet + live accuracy + auto-dismiss + car-mode escape hatch;
  desktop-tested, trigger rules commonTest'd.
- ~~Eco / power-saving mode~~ **DONE 2026-08-07**: Leaf toggle on capture
  (persisted), 15 fps preview cap, map catches up per capture instead of
  following live; emulator-verified at the persisted-state level. Map badge
  shows the armed pref.
- **Resolution menu**: the Tauri app enumerates per-camera supported
  resolutions (`getCameraSupportedResolutions`, cached, with a loading set
  per camera) and persists `selectedResolution`. frontend2's CameraX path
  currently takes the default. CameraX offers `ResolutionSelector`; the
  menu should show real sensor modes, not a hardcoded list.
- ~~Capture queue indicator~~ **resolved 2026-08-07**: the Tauri component
  watches its webview-side capture queue (max 50, slow/fast modes) — a
  structure frontend2 does not have; upload depth is already on the
  capture-upload-stats line.
- ~~Shutter-time control~~ **DONE 2026-08-07**: shutter-priority ladder
  (1/125…1/2000) on the capture screen, ISO auto-scaled to preserve the
  metered exposure product; Camera2Interop, gated on MANUAL_SENSOR.
  Emulator-verified at the CaptureResult level (the emulator's JPEG EXIF
  is canned — do not trust it).

## The camera-control question — research findings (2026-08-06)

Researched (agent report, primary sources). The short version: **stay on
CameraX, skip OpenCamera entirely, mine two Apache-2.0 apps for code.**

- **OpenCamera is GPL-3.0-or-later** — linking it (or porting its code)
  would commit the whole app to GPLv3. Per the user that is not out of the
  question, just a hassle to commit to — and since it is a monolith, not a
  library, with no permissively-licensed fork, the cost/benefit says:
  reference-reading unless something genuinely unobtainable turns up.
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

## Video with per-frame metadata — research findings (2026-08-07)

Third report, primary-source-verified. **CameraX suffices; no MediaCodec
drop needed.** For pairing video frames with GPS/compass samples:

- Best route: `Camera2Interop.Extender.setSessionCaptureCallback` on the
  `VideoCapture` builder — per-frame `CaptureResult.SENSOR_TIMESTAMP`
  (identical on every output buffer of the capture), zero extra streams.
  Alternative: `OverlayEffect.Frame.getTimestampNanos()` — documented to
  equal `ImageInfo.getTimestamp()` for the same sensor frame; **this is the
  path our clockvideo recorder already rides.**
- Clock domains: check `SENSOR_INFO_TIMESTAMP_SOURCE` once. `REALTIME` →
  camera timestamps share `SensorEvent.timestamp`'s clock
  (elapsedRealtimeNanos) — pair nearest-neighbour directly. `UNKNOWN` →
  roughly uptime-based; add a measured boottime−uptime offset (constant
  while recording; they only diverge in deep sleep).
- **Log timestamps at capture time — the mp4 cannot carry them.**
  MPEG4Writer rebases PTS to ~0, and CameraX's VideoTimebaseConverter
  rewrites REALTIME→UPTIME before the encoder. Post-hoc,
  `MediaExtractor.getSampleTime()` recovers per-sample deltas which align
  against the logged list by index/delta matching (OpenCamera-Sensors,
  the Skoltech fork, is prior art for exactly this technique).
- A parallel `ImageAnalysis` purely for timestamps is possible (values
  match exactly across streams) but both streams drop frames
  independently and the binding combination is device-dependent — the
  interop callback avoids all of that.
- No public `Recorder` per-frame API exists through 1.7.0-alpha02; the
  CameraX team's standing advice is the interop callback.

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

## Capture-time sensor pairing under load (design item, user-raised 2026-08-07)

frontend2's `snapshotSensors()` reads `lastLocation`/`lastOrientation` at
shutter-press time — a point sample. The Tauri app instead logs compass and
GPS continuously into a table (GeoTrackingManager) and pairs the capture
with the sample nearest its timestamp afterwards. The point sample is fine
on an idle phone and wrong in exactly the conditions this app is used:

- **Load/throttling skew.** Long capture sessions in the sun overheat the
  phone; under thermal throttling the main thread and sensor delivery lag,
  so "the freshest sample at shutter time" can be hundreds of ms stale —
  and `capturedAtMs = System.currentTimeMillis()` at `capture()` entry is
  itself early: the real exposure happens later in the CameraX pipeline.
- **No interpolation.** With a table you can pair a capture with one fix
  before and one after and interpolate — strictly better bearing/position
  for a moving vehicle. A point sample can never do this.

Direction agreed: eventually switch to the log-and-pair model — the shared
GeoTrackingManager already exists and the clock-video work already proved
the timestamp side. Sketch:
1. Keep feeding EnhancedSensorService + GPS into the shared tracking store
   while the capture screen is up (the Tauri app does this always).
2. Stamp the capture with the sensor-clock time of the actual exposure —
   CameraX's `onCaptureStarted`/`SENSOR_TIMESTAMP` per the frame-metadata
   research, not wall-clock at `capture()` entry.
3. Pair post-hoc: nearest sample, then interpolated bracketing samples.
   EXIF can be written after pairing (the file save already happens off the
   shutter path).
Interim mitigation available now: `locationAgeMs` is already recorded in
the snapshot — surface it as a quality signal.

## Navigation architecture (discussion queued, user 2026-08-07)

How much should frontend2 follow the Tauri navigation style — a menu that
switches routes, while mode buttons inside the map route switch *modes*,
with the mode surviving app restarts? The user likes it (deliberately),
notes it may not be CMP/Android-idiomatic (Nav3 back-stack semantics,
predictive back, deep links all assume routes), and suggested a setting
could choose between styles. To discuss before the app grows more
destinations: what is a route vs a mode, what persists, and what the back
button does in each style.

## Pan-as-exploration + the manual-position claim (DONE 2026-08-07,
user-designed)

The long-standing pain, solved in two iterations the same day. First cut
was a demote-confirm with a 10 s auto-revert; the user refined it: the
timeout fought the very thing panning is for. Final model:

- **Panning is exploration.** It parks the map (no yank-back, ever) and
  never changes what captures record — you can pan around mid-interval-run
  to figure out where you are, harmlessly.
- A small two-sided pill appears on pan: **"Capture here" / "⟲ GPS"**. The
  claim side is the only way the map position becomes the capture
  position — the Tauri parked-map semantic, now behind an explicit accept.
  While claimed: captures geotag from the map centre even over a fresh fix,
  tagged location_source "manual", degraded shutter tone on every shot, an
  override line on the capture screen withdraws it.
- The claim survives entering capture (a gated claim cannot be stale);
  everyone else still gets the clean-ACTIVE re-arm regression guard.
- The shutter is bilingual: stock click for fresh-fix captures, warning
  beep for manual/stale/absent — the pocket hears what it cannot see.

Still open on the Tauri side: promoting background-tagged fixes out of
UserComment/alt_location (the repair flow) remains unimplemented there.

## The claim is not the background flag (design note, 2026-08-07)

In Tauri, BACKGROUND *is* manual mode — "a manually parked map keeps
meaning 'I'm at the map position'", fixes tagged `-background` lose the
photo-pairing lookup. One flag, two meanings fused.

frontend2 splits them, and the split is the feature:

| state                  | map    | GPS        | captures geotag from |
|------------------------|--------|------------|----------------------|
| ACTIVE                 | follows| subscribed | the fix              |
| BACKGROUND, no claim   | parked | subscribed | **the fix**          |
| BACKGROUND + claim     | parked | subscribed | map centre, "manual" |
| OFF                    | parked | off        | nothing / no-fix lift|

Unclaimed BACKGROUND is the exploration state — pan mid-interval-run to
figure out where you are without touching what captures record. If
BACKGROUND alone implied manual (the Tauri fusion), that state could not
exist. Coupling is one-directional: claiming forces BACKGROUND; leaving
BACKGROUND in either direction withdraws the claim.

Consequences for the future log-and-pair work:
- The **claim**, not BACKGROUND, must decide which fixes lose the pairing
  lookup — unclaimed-background fixes are good pairing candidates.
- Log fixes **untagged always**; let pairing consult the claim history.
  Then a wrong claim stays repairable after the fact — which the Tauri
  `-background` tagging (baked in at log time) makes hard, and is why its
  repair flow (promoting alt_location out of UserComment) never got built.

## Storage: the hidden-.Hillview question revisited (user, 2026-08-07)

The two real user needs pull apart: "photos gone from my gallery" AND
"photos survive uninstall" (dev-apk swaps; and a bug may have left some
photos un-uploaded, so losing local files can mean losing photos, period).

What the verified storage facts say (see storageFacts, all API-dependent):
- **App-private** hides from gallery but dies with uninstall — it is the
  mode the "that sucks" scenario lives in; the settings screen already
  shows the ✗.
- **DCIM/.Hillview via File API (API 30+)** actually satisfies BOTH:
  hidden from gallery scans, survives uninstall, still reachable by file
  managers. The idea has merit precisely on modern Android.
- **MediaStore mode cannot hide** — it rewrites `.Hillview` to
  `_.Hillview` and indexes anyway (verified on API 36). On API 29, where
  MediaStore is the only public option, hiding is therefore impossible.
- Alternative worth considering: **DCIM/Hillview + a `.nomedia` file** —
  same gallery-hiding effect without the confusing dot-name in file
  managers, same uninstall survival. Would need the Tauri side to agree
  (its spec treats `Hillview` and `.Hillview` as the two valid shapes).

Mitigations for the un-uploaded-photos-lost-on-uninstall risk, orthogonal
to folder choice: the pending-upload count is already visible; a
"copy pending photos to Downloads" escape hatch would make any uninstall
safe regardless of storage mode. Dev-apk coexistence also blunts the
scenario: debug builds install as cz.hillview.debug alongside the release
app, so "uninstall to try a dev build" is only forced when sideloading a
release-signed build.

Decision: parked until the user can play with the app; no behaviour
changed today.
