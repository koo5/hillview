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
7. **Check for a Tauri Kotlin twin BEFORE building any subsystem.** The
   marker-source episode: a parallel Ktor client was half-built before the
   plugin's photo-worker stack (richer in every way) was found and
   graduated instead. The plugin's src/main/java is the first place to
   look, always.
8. **Phone-in-hand rounds outrank everything.** Every single user
   observation this cycle was a real bug with a clean root cause
   (unrequested permissions, stale-fix display, claim-blind gate, arrow
   grab annulus, unbounded fling, poll-instead-of-moveend, double zoom
   buttons, tile bleed, dialog-window animations, dialog-shaped capture
   pane). Ship a build, collect observations, fix with a regression test
   each — the loop converges fast.
9. **Merged-world testing rules** (one process, one persisted activity):
   arrange state in @Before, never assume a fresh app; a persisted capture
   activity composes at LAUNCH — before @Before — so helpers bounce it;
   GMS's fused location cache is SYSTEM-wide and survives reinstalls, so
   mocks must cover both the platform provider AND fused mock mode;
   connected test runs uninstall the app afterward (data gone); offscreen
   Compose nodes get "clicked" wherever their coordinates land — scroll
   into view first; keep gate-semantics tests strict and let everything
   else use adaptive openers.
10. Compose platform edges collected: view-interop containers do not clip
    children (osmdroid tile bleed); Compose dialogs ignore activity-theme
    dialog styles (strip animations per-window via DialogWindowProvider);
    a property named like an interface method collides on the JVM.

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
- The Main page merge is LIVE: split layout over an always-mounted map,
  persisted activities, hamburger menu, capture pane in the original's
  camera shape; MapStateHolder is process-wide (capture and map move one
  camera); locations ride shared-kt's fused PreciseLocationService; the
  photo folder is Hillview2 (HILLVIEW_FOLDER env var overrides).
- Capture pane = the video (round 4): FILL_CENTER preview, every control
  floats over it in the original's absolute spots (pill 60/60, shutter
  pill bottom-centre, 📷 lower-left, ⚡ shutter-speed menu lower-right,
  Leaf top-right, upload prompt = floating card, never a dialog); the
  interval slider hides behind a shutter long-press. Contract section:
  "Capture pane layout — the video IS the pane".
- /device-photos is ported (cards, status palette, global retry, menu
  entry); the anonymization menu is deferred.
- Tests: ~135 jvm + 160 android-host + 51 shared instrumented + 15 app
  behaviour tests, all green. The behaviour layer covers map tracking
  (incl. the return-from-capture demote regression it caught), capture
  gating (mock-GPS determinism), storage shape per preference, upload
  coalescing (marker-log arithmetic, no foreground promotion), settings
  persistence (restart contract via prefs + fresh-repo + recreation),
  the offline upload queue (real login, radios off/on, WorkManager
  drain to the dev backend), and session-expiry reconcile (persisted
  flag → startup reconciler). The two backend-needing tests SKIP when
  the dev backend is down.

## Remaining tasks

Implementation, roughly in value order:

1. **More Appium scenario ports** onto the new app-behaviour layer — the
   suites in `frontend/tests-appium/specs/` are the source; the testTag
   surface is complete. Done (2026-08-07): capture gating flow,
   storage-shape assertions, upload coalescing, settings persistence,
   upload-queue-offline, session-expiry reconcile. Most remaining specs
   wait on features frontend2 doesn't have yet (intents, FCM,
   geo-tracking export, deep-link auth) — the next value is item 2.
2. **Backend photo query for map markers** — LANDED 2026-08-07, by
   graduating the Tauri app's Kotlin photo-worker loaders to shared-kt
   (StreamPhotoLoader, DevicePhotoLoader, PanoramaxPhotoLoader,
   CullingGrid, AngularRangeCuller, types) and adapting them behind
   PhotoMarkerSource: device + hillview merged by content hash, viewport
   queries with picks, `filtered` → washed-out, featured, source-colour
   borders. Server-log-verified end to end (viewport → query → marker →
   selection → picks round-trip). Still open from this area: mapillary/
   panoramax SourceConfigs + a sources UI, the analysis-filter controls
   (backend flagging already works), CullingGrid adoption, and carving
   PhotoWorkerService's ExamplePlugin coupling so the whole orchestrator
   can graduate too.
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
7. Smaller: "copy pending photos to Downloads" escape hatch; Tauri-side
   repair flow for `alt_location` (still unimplemented there).
   (`locationAgeMs` landed: EXIF UserComment + the stale-fix warning.)

Also landed 2026-08-07: the /device-photos port (DevicePhotosScreen —
cards with thumbnail/status/details from the shared Room DB, global
retry via the shared-kt retry_button path, menu entry
`menu-device-photos`; the anonymization ⋮ menu deliberately deferred —
contract section in tauri-capture-ui-contract.md).

Decided 2026-08-07 (phone in hand): **match the Tauri navigation** — one
Main page (resizable split: photo panel over an always-mounted map) with
persisted activities (view/capture), floating camera/menu buttons, real
routes only for settings/login/etc. The contract section "Main page:
routes, activities, split layout" in tauri-map-ui-contract.md is the spec.
**LANDED same day** (MainScreen.kt): draggable persisted split, persisted
activity with the enter/leave-capture wiring and the zoom>=17 bump, the
hamburger menu absorbing Home (session status/expiry notice, settings,
login, clock video), MapStateHolder lifted to a Koin singleton so capture's
follow-me/claim and the mounted map move the same camera, capture pane
scrollable. The view activity's photo panel is a PLACEHOLDER — the real
gallery is deliberately deferred. All 13 app-behaviour tests migrated to
the merged UI (camera-button toggle, menu navigation, bounce-on-persisted-
capture) and green; both activities verified visually on the emulator. Phone-in-hand fixes already landed:
map location-permission ask on the location button, capture auto-asks
location on entry, single zoom-button set, reload-on-move (no polling),
arrow grab restricted to the arrow outside car mode, osmdroid fling off.

Still parked:

- **Exploration pill UX pass** with real thumbs (placement, wording,
  small screens).
- **Storage**: the hidden-.Hillview / `.nomedia` question (analysis in
  the backlog doc; on API 30+ hidden-public satisfies both needs).
- Tauri Play release: user will run a release and see whether the
  targetSdk-36 pass already succeeds (deadline 2026-08-31).
