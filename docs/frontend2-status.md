# frontend2 — working state, approach, and remaining tasks

Snapshot 2026-08-07, end of the capture/map parity push. This is the
orientation page; the detail lives in the documents it points to.

## The approach (how this work is done)

1. **Observe first, port second.** For every UI port, read the Tauri
   component control-by-control and write what it *actually does* into a
   contract doc before writing Kotlin — "every nuance is hard-won".
   Contracts: `tauri-map-ui-contract.md` (map), `tauri-capture-ui-contract.md`
   (capture, growing), `app-behaviour-scenarios.md` (behaviour mined from
   the Appium + Playwright suites; its 13-item disagreement list is fully
   closed). Dead code found during observation is recorded and *not*
   ported.
2. **Divergences are explicit decisions**, written down with their reasons
   (the rose vs the 7px offset, real sensor resolutions vs the hardcoded
   four, the claim-vs-background split, the exploration pill vs
   pan-demotes-silently).
3. **Rules live in commonMain, testable; platforms hold only plumbing.**
   Four test layers, cheapest first: `:shared:jvmTest` (pure rules +
   desktop Compose UI), `:shared:testAndroidHostTest` (same rules, Android
   JVM), `:shared:connectedAndroidDeviceTest` (device contracts: EXIF,
   storage, real MotionEvents), `:androidApp:connectedDebugAndroidTest`
   (Appium behaviour ports driving the real MainActivity).
4. **Device-verify every behaviour claim** on the capped emulator
   (`scripts/emulator.sh`), at the level that cannot lie: persisted state
   files, CaptureResult frame logs (emulator JPEG EXIF is canned),
   exiftool on pulled photos, semantics dumps. Two fixes-of-fixes came
   from second-order verification (send a SECOND fix; pin then capture).
5. **Shared-kt stays the single implementation** for upload/sensor/auth
   machinery — both apps compile it; divergence is a later explicit
   decision. The full API URL is one config value, never assembled.
6. Build instructions: `frontend2/README.md`. Research record (camera
   libraries, PiP/FGS, per-frame metadata): `frontend2-capture-backlog.md`.

## Where things stand

- Map: ported control-for-control, all 13 behaviour disagreements closed,
  incl. two-finger rotation + ↑N, marker identity, tap selection,
  photo-marker semantics, echo-guarded follow-me (osmdroid cannot tell a
  finger from setCenter — the pushing-flag + quantized-readback guard).
- Capture: full widget parity plus deliberate improvements — glass
  overlay, calibration sheet, eco mode, tap-to-focus, shutter-priority
  ladder (MANUAL_SENSOR-gated), real-resolution menu, location gate with
  the map-position lift, auto-upload consent chain (null licence default),
  bilingual shutter tone.
- The exploration pill + manual-position claim: pan is exploration,
  "Capture here" is the only way the map position becomes the capture
  position; claim survives entering capture; withdrawal everywhere.
- Tests: ~130 jvm + 158 android-host + 40+ shared instrumented + 8 app
  behaviour tests, all green. The behaviour layer covers map tracking
  (incl. the return-from-capture demote regression it caught), capture
  gating (mock-GPS determinism), storage shape per preference, and upload
  coalescing (marker-log arithmetic, no foreground promotion).

## Remaining tasks

Implementation, roughly in value order:

1. **More Appium scenario ports** onto the new app-behaviour layer — the
   suites in `frontend/tests-appium/specs/` are the source; the testTag
   surface is complete. Done: capture gating flow, storage-shape
   assertions, upload coalescing (2026-08-07). Good next picks:
   session-expiry reconcile, upload-queue-offline, settings persistence
   across restart.
2. **Backend photo query for map markers** — retire the
   RecentPhotoMarkerSource scaffolding; brings analysis filters to life
   (the gating is already built and tested) and non-device sources
   (hillview/mapillary/panoramax) with source-colour borders.
3. **Log-and-pair sensor capture** (design in the backlog doc): feed
   GeoTrackingManager while capturing, stamp captures with
   SENSOR_TIMESTAMP, pair post-hoc with interpolation; fixes load/thermal
   staleness. Log fixes untagged; pairing consults the claim history.
4. **PiP float mode** — map floats over the native camera app; research
   says no FGS needed while PiP is visible. Needs an entry point, an
   `isInPictureInPictureMode` guard on onPause, and releasing our camera.
5. **Camera enumeration rows** in the 📷 menu (front/back/multi-lens);
   the menu structure left room.
6. **Video recording mode** — extend the clockvideo CameraX stack; the
   per-frame metadata recipe is researched and written down.
7. Smaller: `locationAgeMs` as a surfaced quality signal; "copy pending
   photos to Downloads" escape hatch; Tauri-side repair flow for
   `alt_location` (still unimplemented there).

Decisions parked until the user can play with the app:

- **Navigation architecture**: routes-from-menu vs modes-in-map, mode
  persistence across restarts, CMP-idiom tension, maybe a setting.
- **Exploration pill UX pass** with real thumbs (placement, wording,
  small screens).
- **Storage**: the hidden-.Hillview / `.nomedia` question (analysis in
  the backlog doc; on API 30+ hidden-public satisfies both needs).
- Tauri Play release: user will run a release and see whether the
  targetSdk-36 pass already succeeds (deadline 2026-08-31).
