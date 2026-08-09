# frontend2 — working state, approach, and remaining tasks

Snapshot 2026-08-07, end of the capture/map parity push. This is the
orientation page; the detail lives in the documents it points to.

**WHY this rewrite exists (user, 2026-08-08)**: the Tauri app stopped
processing captures fast enough in short-interval mode — Android 15
update, summer heat, or both (thermal throttling). CAPTURE THROUGHPUT
UNDER THERMAL PRESSURE is the hard requirement everything else serves.
Corollaries: auto-uploads and dense marker drawing are secondary (the
user turns uploads off and drops max markers to ~10 in critical
sessions); optimizations should concentrate on the shutter-to-final-
bytes path. First throughput fix landed 2026-08-08: capture
finalization (whole-file EXIF rewrite + gallery index) moved OFF the
main executor onto a process-lifetime IO scope — the shutter frees the
moment CameraX hands the JPEG over, finalizations overlap, and a
capture just before leaving the pane still finalizes. lastPhoto (the
upload trigger) still publishes only after the final bytes exist.

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
  interval slider works the DualCaptureButton way — one finger: hold
  300 ms, slide onto it, release starts the run (release on the button
  cancels, tap stops); run badge on the button + session total in the
  corner (CaptureQueueIndicator); the Leaf answers the same grammar with
  an fps ladder (capture-only → 0.1–1 duty band → 7–30 AE band →
  default; stream-gated beats, fresh Preview per beat, bitmap-overlay
  freeze frames — see the contract's hard-won platform facts).
  Contract section: "Capture pane layout — the video IS the pane".
- Exposure is a RULE, not a pinned time (⚡ menu, three rows: rule /
  target / bias). A pinned shutter cannot survive open sun — the aperture
  is fixed, so once ISO sits on the sensor floor a pinned time has nothing
  left to give and blows out by 3+ stops. Modes are parameter tuples over
  one function (planExposure, commonMain): Pin = the old exact behaviour,
  Floor = that time or faster, Sports = a floor that hands the shutter
  back to 1/125 before pushing gain past ISO 1600. EV bias is the answer
  to a sun in frame (metering targets the average; no shutter rule helps).
  Interval runs call prepareExposure() before each shot — AE gets the
  camera back for a few frames, we take its reading and re-apply the rule
  — because a rule turns AE OFF, which used to freeze the metering at
  whichever scene the rule was chosen in. The plan's outcome (on target /
  faster / slower / under / overexposed) is tallied per shot in the Stats
  dialog: that tally is how "which mode is right" gets answered from a
  real drive rather than from the couch.
  2026-08-09: the shot's exposure story also rides in the UserComment
  provenance JSON — `"exposure":{mode, target_ns, ev_bias, applied_ns,
  iso, outcome, metered_ns, metered_iso}`, snapshotted at the shutter.
  CameraX's standard tags say what the sensor DID; this says what was
  asked and why the answer came out that way. Absent under auto exposure.
  prepareExposure() is also cancellation-safe now: a run stopped
  mid-metering-window returns the borrowed preview and puts the rule back
  (NonCancellable finally) instead of leaving the eco-0 band streaming.
- /device-photos is ported (cards, status palette, global retry, menu
  entry); the anonymization menu is deferred.
- Native auth is LIVE: backend POST /api/auth/google/native verifies a
  Google ID token (audience = GOOGLE_CLIENT_ID, the web client id) and
  mints the standard sid pair via the extracted oauth_user_to_tokens
  tail; the app's CredentialGateway seam (androidx.credentials +
  googleid) gives the login screen a passive saved-password offer,
  save-on-success, and a Continue-with-Google button (hidden unless
  HILLVIEW_GOOGLE_CLIENT_ID is baked in at build; native-only — the
  browser fallback joins with deep-link work). NativeAuthConfig.uiEnabled
  is the test kill-switch for system sheets; GitHub remains unimplemented
  (the Tauri UI keeps its button commented out too). Full study doc:
  docs/native-auth.md.
- Native zoom/focus (2026-08-08, user-directed divergence): pinch-to-
  zoom + ratio chip, long-press AE/AF lock + chip, Focus Auto/∞ in the
  📷 menu; the original's slider pair retired.
- Geo-tracking CSVs are WIRED (2026-08-08): raw fused + orientation
  streams feed shared-kt's GeoTrackingManager while capture is open.
  Dump-and-clear at capture-session end (auto_export pref) + Export-now
  and the auto-export switch in Settings; CSVs land in GeoTrackingDumps/
  beside the clock videos. Room forbids main-thread DB reads — store on
  IO (this crash-looped otherwise).
- The ELECTION rework (2026-08-08), a shared-kt change serving both apps.
  `bearings`/`locations` are keyed on (timestamp, sourceId) instead of
  timestamp alone, so concurrent streams stop silently eating each
  other's rows; `source` became a small elect-able vocabulary (android |
  gps-kalman | manual) with the fine provenance moved to a new `detail`
  column; and every row records which source was ELECTED at the instant
  it was written, so a background stream can be re-elected post-hoc.
  Three things that were the election encoded as data are gone with it:
  the "-background" source suffix and its write-ordering choreography,
  the `%background%` exclusion in LocationDao, and frontend2's synthetic
  effective_* stream (which existed only because the tables could not say
  which source was in use — now they can). The stale-fix hand-over went
  too; see tauri-capture-ui-contract.md, "Fix freshness". frontend2's
  pill survives as the primary way an election happens, with
  MapSession owning both routes into it. pics consumes it via
  gps_log.find_effective_before. Full design + rationale:
  memory/geo-tracking-election.md.
  Follow-up (2026-08-08, evening): `GeoTrackingManager` is now ONE
  instance per process (`GeoTrackingManager.get(context)`, the
  PhotoDatabase.getDatabase idiom). frontend2 had two — the map pane's,
  which publishes the election, and the capture pane's, which writes the
  fix rows — and the elected source is per-instance state, so every fix
  taken while the map position was elected reached disk with NO election
  recorded: precisely the row the two-step lookup has to drop. Found by
  the new GeoElectionBehaviourTest, not by hand. The Tauri app was never
  affected (ExamplePlugin holds exactly one). Test debt from the rework
  and what is left of it: docs/geo-election-test-todo.md.
- Server-URL discipline (the stranded-client-key incident, 2026-08-08):
  the SETTING and the RUNTIME URL are separate values; changing the
  setting shows a restart banner and "Restart now" performs a full
  process relaunch — the only sanctioned way to move auth, workers, and
  cached clients together. The settings field persists trimmed (no
  trailing slash) while editing raw. Backend answers a never-registered
  client key with 409 + error_code=client_key_not_registered (and a
  server-side warning log); the shared-kt authorize step self-heals it
  by re-registering and retrying once (prose-matched 400 fallback for
  old backends kept).
- Tests: 142 jvm + 106 android-host + 129 shared instrumented (the
  device tree carries commonTest along) + 18 app behaviour tests, all
  green — measured 2026-08-08 after the election test debt was paid
  down (docs/geo-election-test-todo.md). The behaviour layer covers map tracking
  (incl. the return-from-capture demote regression it caught), capture
  gating (mock-GPS determinism), storage shape per preference, upload
  coalescing (marker-log arithmetic, no foreground promotion), settings
  persistence (restart contract via prefs + fresh-repo + recreation),
  the offline upload queue (real login, radios off/on, WorkManager
  drain to the dev backend), and session-expiry reconcile (persisted
  flag → startup reconciler), and the geo ELECTION end to end (claim →
  pan → shoot stamps the new centre; the no-fix hatch does the same; the
  election reaches the exported CSVs — which is how the two-instance
  GeoTrackingManager bug was found). The two backend-needing tests SKIP
  when the dev backend is down.

## Remaining tasks

Implementation, roughly in value order:

0. **Car-mode capture bearing — FIXED 2026-08-08**: the stamp (and the
   pill, and the effective CSV) now reads the map's bearing state via
   PhotoCapture.stampBearing, and car mode actually WORKS on the map:
   MapSensorController feeds every fix through the shared-kt Kalman
   heading filter + mount offset (source "gps-kalman", starting the fix
   stream if follow-me hasn't), both modes drive the holder past a 1°
   dead-band. Bonus finds fixed with it: compassAccuracy was never set
   (calibrate button could never appear), and the gps-kalman bearing
   stream now lands in the tracking tables like Tauri's.
0a. **EXIF orientation — FIXED 2026-08-08**: every JPEG used to claim the
   pose the capture pane happened to OPEN in. CameraX derives the EXIF
   Orientation tag from ImageCapture.targetRotation, whose default is the
   DISPLAY rotation sampled once at use-case construction — and the
   activity handles `orientation` config changes itself and never
   rebinds, so it never moved again; with auto-rotate off (the normal
   state when shooting) display rotation never tracks the device at all.
   Now shared-kt's MyDeviceOrientationSensor (accelerometer tilt, the
   same class driving the Tauri plugin's `device-orientation` event,
   FLAT_UP/FLAT_DOWN filtered so ground/sky shots keep the last real
   pose) drives targetRotation live, seeded at bind and re-asserted at
   the shutter; the pose also lands in SensorSnapshot.deviceRotationDeg.
   New DeviceOrientation.toDegrees/toSurfaceRotation in shared-kt; the
   Tauri toExifCode table is untouched and deliberately NOT reused —
   its canvas frames were already display-oriented, so the same physical
   pose wants a different tag than a raw CameraX sensor-frame buffer
   (portrait: 1 there, 6 here). PhotoExifWriter still must not write the
   tag — only CameraX knows sensorOrientation and lens facing — its job
   is not to lose it across the whole-file rewrite, now pinned by a
   test. NOT verifiable on the emulator: its camera's JPEG EXIF is
   canned, so the four-pose check with auto-rotate OFF needs hardware.
0b. **Stamp refinement — SUPERSEDED by the 2026-08-09 decisions.** The
   double-writes/restamp_pending mechanics (and every open question they
   dragged along: surgical EXIF patches, re-upload fallbacks, eco-mode
   double-write cost) dissolve under the roadmap the user set:
   - **The DEFAULT capture mode becomes hillview-centered**: finalize =
     the fastest possible file write, NO EXIF rewrite at all. Metadata
     lives in the photos table and goes to the worker FROM the table.
     EXIF writing (today's PhotoExifWriter pass) becomes an OPT-IN for
     people using the app outside the hillview usecase.
   - **Interpolation is then a pure table-side refinement**: the photo
     row is written instantly with the at-the-time values; a refiner
     updates the row when the bracketing data lands — the NEXT FIX for
     location and the car-mode (gps-kalman) bearing, both interpolated
     across the bracket; W/2 of the smoothing window for the compass
     bearing, recomputed as a CENTERED window over the ~10 Hz samples
     already in the bearings table (zero-phase: removes the causal EMA's
     lag, which is worst exactly when shooting while turning). The UI
     shows a small progress indicator while any refinement is in flight.
     Truncation is a NON-ISSUE by design: worst case the last few photos
     of a session keep their at-the-time values (user's explicit
     acceptance) — no re-uploads, ever, because nothing downstream is
     stamped until the worker reads the row.
   - A separate **"external camera" activity** (0c) covers the
     native-camera-app usecase the tracking tables were originally for.
   **The fast-write default LANDED 2026-08-09.** The channel already
   existed: the worker's `/upload` takes a `metadata` form field that WINS
   over embedded EXIF (built for browser captures, which cannot write
   EXIF; the pics pipeline uses it too). What landed: photos table v15
   gains bearingSource / locationSource / locationAgeMs / exposureJson
   (ALTER TABLE, both apps' schemas re-exported, same identityHash);
   capture threads them PendingUpload → registerCapturedPhoto → row;
   PhotoUploadLogic.buildUploadMetadata renders every upload's row into
   the metadata field (ms-ISO captured_at via the new
   formatTimestampToIsoMillis — EXIF is second-granular); finalization
   skips PhotoExifWriter unless the new "Write EXIF into photo files"
   opt-in (settings-write-exif, default OFF) is set — the CameraX save IS
   the final file, stats metric finalize(fast) vs finalize(exif+index).
   Worker side: the synthesized UserComment now passes through
   location_age_ms + exposure; captured_at flipped to metadata-WINS
   (embedded DateTimeOriginal is second-granular local wall-clock — the
   fill-if-missing rule silently preferred the worse value whenever a
   file carried any EXIF); Z-suffixed values no longer get the file's
   local offset applied (that shifted an already-UTC instant by the
   timezone). Emulator-verified: fast file = CameraX tags only (no
   GPS/UserComment, actual 1/500@ISO221 from the Floor rule), v14→v15
   migration ran on a live DB, row carries the full provenance, drain
   logs the complete metadata blob per photo — old rows degrade to
   geo+captured_at with EXIF fallback. (Upload's last hop to the dev
   worker blocked by the emulator not trusting dev4's Caddy CA; the
   worker merge is unit-tested and is the browser path's production
   code.) STILL OPEN from this block: the interpolation refiner itself,
   and the in-flight progress indicator.
0d. **Election follow-ups (small, 2026-08-08)**: `is_sensor_bearing_source`
   in src-tauri/src/device_photos.rs — FIXED. Was a substring sweep
   ("contains compass/rotation/gyro/sensor/tauri/...") from when source
   names were long ad-hoc strings; now the explicit
   `starts_with("android") || == "gps-kalman"`, mirroring
   `kotlinOwnsSource()` in mapState.ts. The two are one invariant: a
   source the frontend echoes into the table is one whose frontend value
   Rust trusts; a source Kotlin owns is one Rust looks up. Deliberate
   behaviour change: the web DeviceOrientation fallback
   (`web-absolute-compass-true`) used to match on "compass" and no longer
   does — its value never crossed the JS bridge, so the staleness the
   function corrects cannot apply and the frontend value is fresher.
   CaptureScreen's `overridePosition` now also applies for the no-fix
   hatch, not just the pill's claim, since both set the same flag —
   VERIFIED on a device 2026-08-08 (`GeoElectionBehaviourTest.
   theNoFixHatchFollowsTheMapAsWell`: the hatch's own label follows the
   map and the capture stamps that same position).
0e. **Stamp position made live — FIXED 2026-08-08**: `capture.manualLocation`
   was read once, at the moment the map position was elected, so claiming
   at one place then panning to another and shooting stamped the FIRST
   while the tracking table (which does follow pans) recorded the second
   — photo and log disagreeing about where the user said they were. It
   now collects `mapState.spatial`, the same shape as the stamp bearing,
   and the same as Tauri whose locationData is reactive on $spatialState.
   The freeze predates the election work; what the election work added
   was a witness to it. Guarded on a device since 2026-08-08
   (`GeoElectionBehaviourTest.aClaimStampsWhereTheMapIsNowNotWhereItWasClaimed`
   — claim, pan 0.05°, shoot, and the row must be the new centre).
0f. **External camera mode — LANDED 2026-08-09.** A PANEL MODE beside
   capture in the same slot (user's framing: "just another panel mode
   next to capture mode… just no camera stream running"), reached from
   the menu, `mainActivity = "external"`. Composing the pane starts an
   `ExternalCameraService` — a `location`-typed FOREGROUND service, so
   the record survives the system camera app taking the screen, which is
   the entire point; leaving the mode stops it. Sensors + GPS write the
   tracking tables continuously with "android" elected (starting the
   mode IS that user act), CSVs auto-dump every 5 minutes for
   crash-safety on long sessions plus one at stop. The pane shows the
   live fix/heading and the growing row counts, and offers "Open camera
   app" + "Export CSVs now". THE MAP STAYS IN CHARGE: elections (the
   pill's manual claim), car mode and follow-me are the map's, unchanged
   — which is why the service deliberately does NOT feed the Kalman
   heading filter (the map's controller already does, from its own fix
   stream; a second feeder would double-pump it). Emulator-verified:
   foreground service `types=0x8` (LOCATION), live status line, counts
   climbing, clean stop on leaving. STILL OPEN here: per-mode sensor/GPS
   rate defaults (0c) — external wants continuous, capture wants
   optimize-around-the-shutter, gallery wants neither.
0c. **Eco/sensor design queue (user, 2026-08-08, not built)**: eco
   SUB-FLAGS to test variations — e.g. sleep the bearing sensors until
   around capture time in eco interval runs; a GPS interval slider
   (same grammar as the fps ladder); and a deliberate divergence: a
   separate "EXTERNAL CAMERA" activity where sensors run and tracking
   tables write CONTINUOUSLY (for shooting with the native camera app;
   pairs with the PiP float-mode idea) — as opposed to the capture
   activity, which optimizes around capture moments, and the gallery
   activity (thought through later). 2026-08-09: the external-camera
   activity is CONFIRMED roadmap ("what we'll definitely do"), alongside
   the hillview-centered fast-write default in 0b.

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
