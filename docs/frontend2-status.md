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
  **2026-08-19: the two panels are `movableContentOf`** — a rotation
  re-parents them between the portrait Column and the landscape Row
  instead of rebuilding them. Plain lambdas disposed both compositions,
  which is why an interval run stopped on rotation (its `repeating`
  rememberSaveable had nothing to restore from — only activity
  recreation goes through the Bundle, and MainActivity handles
  orientation itself), and took the exposure rule and the camera binding
  with it. Two re-parenting facts: CameraX's PreviewView (TextureView)
  re-attaches its SurfaceTexture on its own; osmdroid's MapView does NOT
  survive it by default — destroy mode runs onDetach() on every
  onDetachedFromWindow — so `setDestroyMode(false)` and the explicit
  onDetach() on dispose (rememberMapView). **Rotation-verified on an
  emulator 2026-09-17**: a 2 s interval run was taken through
  portrait → landscape → portrait and kept shooting across both (badge 6 →
  24 → 45), with the Sports rule still engaged, the preview still streaming,
  osmdroid still drawing, and no exception either way.
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
  **2026-08-11: metering is CONTINUOUS** (SceneMeter, backlog "Metering
  made continuous"): a 640×480 ImageAnalysis stream measures the scene at
  the exposure we set, and the rule is re-planned from it at ≤3 Hz; the
  AE window above is now only the fallback for hardware that refuses a
  third use case — prepareExposure() returns at once otherwise, and a
  manual tap never calls it. So nothing of OURS sits between the press
  and the shutter.
  **2026-08-19: the shutter lag was CameraX's, not ours** — see backlog
  "Shutter lag: the 3A lock". ImageCapture ran in MAXIMIZE_QUALITY, which
  in the 1.6 camera-pipe backend locks 3A (converge ≤1 s, AF trigger +
  wait for lens-locked ≤1 s) before every still; with Focus ∞ (AF OFF)
  the lens never reports locked, so that wait is expected to run to its
  timeout. Now a knob in the 📷 menu (StillCaptureMode: Quality /
  Latency [default] / Zero shutter lag where supported) plus a decoupled
  JPEG-quality row (default 100 — what Quality gave implicitly); the
  shutter tone plays at onCaptureStarted (the exposure) instead of after
  the JPEG write; Stats gains press→exposure / exposure→jpeg, and the
  press logs the HAL's 3A state so a Quality-mode timeout is visible.
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

## Concerns raised 2026-08-09 (review before the next feature)

These came out of the user's read of the refiner + external-camera work.
They are ONE architectural problem seen from four sides, plus one queued
default. Read them together; fixing the hub answers most of them.

**C1. No sensor/geo hub — FIXED 2026-08-09 (`GeoEngine`).**
frontend2 now constructs **three** independent `EnhancedSensorService`
instances (map `MapScreen.android.kt:785`, capture
`PhotoCapture.android.kt:320`, external `ExternalCameraService.kt:94`)
and **three** `PreciseLocationService` instances (same three files). The
Tauri app — the known-good semantics — has exactly ONE of each, in
`ExamplePlugin`. This is the marker-source episode repeating: a parallel
path built beside an existing one instead of on top of it.

The user caught it from the outside, which is the tell: *"the external
camera page shows some compass feed"*. It does — its OWN, formatted from
its OWN sensor instance, not the app's canonical bearing. The canonical
bearing is `MapStateHolder.bearing` (what capture stamps from via
`stampBearing`), so the number on the external pane can legitimately
differ from the number the app would stamp at that instant. Two clocks,
one of them decorative.

**Designed 2026-08-09: `docs/frontend2-geo-engine-design.md`** — written
after reading the original rather than from memory. Short version: the
original is one value pair (`spatialState` + `bearingState`), ONE
hardware owner fanning each sample out to both the table (full rate) and
the state (UI rate) from a single callback, one write funnel
(`updateBearing`/`updateSpatialState` = state + election + table echo in
one call), and an explicit per-source rule for which materialization is
authoritative (`kotlinOwnsSource` / `is_sensor_bearing_source`, declared
one invariant). frontend2 has the state pair but neither the single owner
nor the funnel. The fix is a process-wide `GeoEngine` owning the sensors
off the UI thread, `MapStateHolder` as the single funnel, panes as pure
observers, and the foreground service HOSTING the engine rather than
duplicating it.

Why it happened, worth keeping: in Tauri the plugin boundary did the
architectural work — JS *cannot* open a sensor, so single ownership was a
wall, not a convention. In CMP the wall is gone and nothing stops a pane
from constructing its own. **Port the constraints the original's
structure enforced, not only the behaviour it produced.**

**C2. Car-mode bearing derived on the UI thread — FIXED 2026-08-09.**
The composition moved into the engine, on its own HandlerThread; the map
only observes `engine.carBearing`. Measured on the way: BOTH shared-kt
services deliver on the main looper, in both apps — the original gets
away with it only because its map draws in the WebView renderer process,
so this now goes further than the original rather than copying it.
Original wording: (user: "slightly
nervous… that's a UI thread in what should be a stutter-less pipeline,
held up by marker rendering and stuff"). Every canonical bearing write —
`state.updateBearing(...)` — is inside `MapScreen.android.kt`, and the
car-mode composition (fix → `feedLocationForHeadingFilter` → mount
offset → bearing state → capture stamp) rides the map component's
callbacks. So marker rendering and map work sit on the same thread as
the value photos are stamped with. It is correct today (verified
end-to-end) but structurally wrong: bearing derivation belongs in the C1
hub, off the UI thread, with the map as one more observer. Note this is
also WHY the external service deliberately does not feed the Kalman
filter — with a hub, that awkwardness disappears.

**C3. Refiner/upload consistency — FIXED 2026-08-09.** The question was
whether a photo can be restamped after its upload starts, leaving
device-photos and the server disagreeing. It could, and the window was
WIDER than first described: the drain snapshotted a row
(`getNextPhotoForUpload`), then validated an auth token — possibly a
network refresh — and hashed the file, and only THEN marked it
`uploading`; and it uploaded the SNAPSHOT. So a refinement landing any
time in that gap was written locally and never sent.

**The primary mechanism was never the claim — it is "do not select a
photo that is still due for restamping", and that already existed
(`uploadHoldUntil`, filtered by both candidate queries). The race
happened only because the deadline was mis-tuned:** `BRACKET_TIMEOUT +
2 s`, about 1.5 s of headroom over the refiner's own worst case, so an
ordinary GC pause or a dozing device expired the hold while the refiner
was still working. A deadline is a CRASH BACKSTOP — it answers "the app
died mid-refinement, how long before this photo may upload anyway" — so
it is now 60 s, and app start drops holds left by a process that is gone
(`clearAllUploadHolds`), which is what lets it be generous: a real crash
recovers on the next launch instead of waiting it out. Costs nothing in
latency, because the refiner clears its hold the instant it finishes and
pokes the drain; uploads are driven by completion, never by expiry.

Beneath that, the claim itself was still a read-then-write, so the fix
has two more halves as the correctness floor for the crash-recovery
instant:

- **Claim atomically.** `claimForUpload(id, expectedStatus, now)` is a
  compare-and-set on the status the row was selected under; 0 rows means
  the claim was lost and the drain skips the photo. Deliberately not a
  new STATUS (which was the first instinct): a status must be exited by
  whoever set it, so a crash mid-refinement would strand the row and need
  a sweeper. `uploadHoldUntil` stays a timestamp for the same reason —
  time alone re-arms it.
- **Re-read after claiming.** The upload is built from the post-claim
  row, so a refinement that won the race IS uploaded. After the claim
  nothing can change the stamp, because `applyRefinedStamp` only touches
  rows still `pending`.

Together the two orderings are both consistent: refine-then-claim
uploads refined values; claim-then-refine leaves the at-the-time stamp
in place everywhere. Asserted on a device by
`UploadClaimRaceTest` (4 tests: the CAS, refinement blocked after a
claim, refinement honoured before one, and a held row being invisible
until its deadline).

**Correction to the original note:** the `insertPhoto`-is-REPLACE hazard
listed here is NOT reachable. `scanForNewPhotos` skips existing photos by
path AND by hash before inserting, so it cannot wipe the refinement
columns of a row it re-encounters. Known remaining nuance, accepted: a
refinement still in flight when an upload FAILS is lost, since the row is
then `failed` rather than `pending` — the failure mode is "keeps the
at-the-time stamp", which is the designed worst case.

**C4. Per-activity sensor/GPS rate defaults — LANDED 2026-08-09**, as
predicted, the moment C1 gave rates an owner. `GeoConfig` is passed IN at
the call site (`GeoDefaults.kt`: capture/external at 33 Hz + 1 s fixes,
map-only relaxed to 10 Hz + 2 s), never baked into the engine — the
user's call, and it is what makes the GPS-interval slider and the eco
sub-flags VALUES rather than new machinery. Device-verified: leaving the
external activity drops the engine to Off, and a map-only view comes back
at the relaxed rates. Remaining: the sliders themselves, and real-device
tuning of the numbers.

**C5. Compass and GPS frozen after unbackgrounding — RE-ARMED 2026-08-19,
not yet device-verified.** User report (recurring; the 2026-08-18
monotonic-clock fix removed one cause, not this one): come back to the
app and both the compass and the fix are stuck at their last values. By
reading, every consumer downstream is lifecycle-agnostic (plain
`collect`s, no `repeatOnLifecycle`), so the sources are the suspects:
`EnhancedSensorService` paused/resumed ITSELF via its own
ProcessLifecycleOwner + screen-state observer (and the engine never
released those — every instance ever made stayed registered), and the
fused-location request was simply left in place across a backgrounding,
which on modern Android means across a FROZEN process. Whatever the
platform does to those registrations, a fresh one is known-good, so the
engine now owns the policy: it observes the process lifecycle itself
(`observeAppLifecycle = false` to the service, `destroy()` on stop),
pauses sensors on background unless `GeoConfig.sensorsInBackground`
(true only for the external-camera service — which, incidentally, had
its sensors paused by the old observer the moment the system camera came
to the front, the exact moment it needs them), and on every foreground
return tears down and re-registers sensors and removes + re-requests the
fix stream. A watchdog on the geo thread (5 s) catches what no lifecycle
event announces: a registered listener silent for >5 s in the foreground
(raw events, `lastRawEventElapsedMs`, not the change-suppressed output —
a still phone emits nothing) is re-registered with backoff to 60 s; no
fix for >60 s re-requests the stream with backoff to 10 min (no sky is
normal). Every action is an event-log "geo" line, the Stats dialog shows
`geo: foreground/background, sensors raw event Ns ago, fix Ns ago`, and
`registerListener` refusals are now logged. If the freeze recurs WITH the
re-arm lines present in the event log, the fault is downstream after
all and the liveness line says which stream.

**Tracking CSV exports can outlive the app (2026-08-19, user-requested).**
The dumps' home — app-private `GeoTrackingDumps/` — is deleted on
uninstall and unreachable to file managers since Android 11; public typed
dirs (DCIM/Pictures) refuse non-media files, and unprompted writes into
Documents/ would litter a folder the user never offered. So durability is
the user's explicit act: a "Choose folder…" row under Tracking CSV export
opens the system folder picker (SAF), the tree URI persists as
`export_tree_uri` in hillview_tracking_prefs (grant taken before pref,
released on Reset), and `dumpAndClear` creates the CSVs there via
DocumentsContract — framework APIs only, so shared-kt still compiles in
the Tauri app, which has no picker and keeps its old behaviour. A dead
grant (reinstall, folder deleted) drops the choice loudly (event-log
"export" line) and falls back to app-private; transient failures fall
back per-file and keep the choice. Every dump now logs an "export" line
with counts and destination. Default unchanged — private, dies with the
app — deliberately: a location history that outlives the app must be
opted into. Not yet device-verified.

## Two numbers are called "the compass" (2026-08-20)

Worth knowing before the next heading bug is reported, because it cost a
morning:

- **The engine's raw heading** — `GeoEngine.orientation.trueHeading`. Moves
  whenever the phone turns, as long as the engine is bound. The
  external-camera pane's STATUS line prints this one.
- **The app's elected bearing** — `MapStateHolder.bearing`. This is the value
  a photo is stamped with, the map arrow points at, and the capture pill
  shows. It is only written while something is driving it, and in car mode it
  comes from the GPS course, not the compass.

So "the compass is stuck in capture but fine in the external pane" is one
value frozen next to another that never was. Three paths stand the elected
side down, all silently and all faithful to the original: dragging the
bearing arrow (`Map.svelte:1230`), navigating photos in the viewer
(`bearingTracking.ts:32`), and a failed compass start reverting the intent.
The original's answer to all three is the capture pane's bearing-tracking
hint, which frontend2 now has.

**A registration can die without going silent (2026-08-20).** The liveness
watchdog stamped `lastRawEventElapsedMs` on event ARRIVAL, so a
rotation-vector sensor repeating one frozen sample at full rate looked
perfectly healthy — and everything downstream stays healthy with it: the EMA
converges on the frozen value, the elected bearing tracks it faithfully. The
only live input left is then the device-orientation remap
(`remapCoordinatesForOrientation`), so the heading alternates between a
handful of values depending on how the phone is held. The service now also
tracks when a sample last CHANGED, and the watchdog re-registers when a
repeat outlasts a turn (`sensorLooksStuck` — repetition alone is a phone on
a table, and must never trigger a restart).

**When OTHER apps' compasses are stuck too (2026-08-20).** Then the stall is
the device's sensor hub, not ours, and re-registering cannot cure it — but
Hillview is still the prime suspect for causing it, because it is the app
running the sensors hardest. Three misbehaviours were found and fixed while
looking:

- `GeoConfig.sensorDelayUs` never reached `registerListener` (which used a
  hardcoded 30 ms), so the relaxed map-only rate never existed AND every
  activity switch tore down the registration to rebuild an identical one —
  churn that changed nothing.
- The watchdog re-registered forever, backing off only to once a minute. At a
  hub that is already wedged that is pure harm; it now gives up after
  `SENSOR_RESTART_GIVE_UP` attempts until a foreground return or a config
  change, and says so in the event log.
- The "boost sensor processing" code boosted the CALLING thread and never
  restored it. With frontend2's callback handler that pinned the UI thread at
  `THREAD_PRIORITY_URGENT_DISPLAY` for the life of the process while the
  thread it meant to boost ran at default. (Under Tauri, caller and callback
  thread are both the main looper, which is why it read as correct.)

The Stats line counts registrations per session, which is the first number to
look at if it happens again.

**The remap table is CORRECT; the model that doubted it was wrong (settled
2026-09-04).** Both modes — plain UPRIGHT and the A22 landscape workaround —
were tested and vetted on real devices in the Tauri app, and both live in
`shared-kt` (`EnhancedSensorService`), which BOTH apps compile: the vetting
carries to frontend2 unchanged. So the offline model below is wrong
somewhere (most likely in how it maps a physical pose to the
DeviceOrientation class, or in the roll-flip interaction), and the episode
is kept only as a warning about the instrument, not about the code. Do not
"fix" the remap on the strength of a model.

(frontend2 has so far been exercised only on an A22 with the workaround on;
the no-workaround path is vetted in Tauri and is the same shared code, so
this is a coverage note, not a doubt.)

**The original investigation, for the record.** UPRIGHT mode keys a
coordinate remap on a four-state device-orientation class
(`remapCoordinatesForOrientation`), and when the attitude sample freezes that
remap is the only live input into the heading — which is why a frozen sensor
presents as a compass alternating between a couple of values according to how
the phone is held. Suspicion naturally falls on the table itself, and an
offline port of `remapCoordinateSystem`/`getOrientation` (validated against
Android's own documented example) does say the two landscape branches read
180° off for a phone held VERTICALLY in landscape.

Do not act on that without better evidence than we have. The phone says
otherwise — the compass is right upright, in landscape and lying flat — and
the emulator cannot arbitrate, because its synthesized rotation vector does
not follow `adb emu sensor set acceleration/magnetic-field`: the portrait
pose read a stable 14.5° while an equivalent landscape pose drifted
285.8° → 294.3° across two 20-second settles, matching neither the model nor
itself. The device-orientation class is now shown in the debug readout, so
the next person to see the alternation can watch whether the heading moves
only when the class does.

`Settings → Geo debug readout` prints the whole chain under the photo count:
elected value, who wrote it, how long ago, against the raw heading with its
own age, how long that raw sample has been REPEATING, and the drift between
them. The two ages are the diagnosis — the map
writes only past a 1° dead-band, so a still phone's elected age is
legitimately minutes old, and only a FRESH raw age beside a large drift means
the chain stopped. See `GeoDebugText.kt`.

## 2026-09-17 — the photo index, on an emulator at last

The index had been written, sharded, tuned and documented without ever being
watched. An emulator became available; every claim about it was wrong in some
way.

- **The "Write it now" button had never once worked.** `dumpNowForResult` is a
  suspend function, which says nothing about which THREAD — it inherits the
  caller's, and the caller is a button in a Compose screen. Room refuses the
  main thread outright, so every press threw `IllegalStateException: Cannot
  access database on the main thread`, caught its own exception and reported
  "failed". Fixed with an explicit `withContext(Dispatchers.IO)`. The
  automatic triggers were never affected: they come off the IO scope.
- **The index was growing a new file per dump, then stopped writing at all.**
  The emulator carried `photos.csv` plus `photos (1).csv` … `photos (31).csv`,
  and was falling back to app-private storage — the one destination that does
  not survive an uninstall, which is the entire point of the feature.
  - The chain: `findInMediaStore` asks by RELATIVE_PATH + DISPLAY_NAME, and
    the media database hides a NON-MEDIA row from every app but its owner.
    An uninstall orphans ownership, so after a reinstall the lookup came back
    empty for a file plainly sitting there. The dump then inserted;
    MediaProvider never overwrites, so it handed back a numbered sibling;
    nothing remembered the new name, so the next dump repeated the whole
    dance. At 32 siblings `buildUniqueFile` gives up
    ("Failed to build unique file"), the insert throws, the File API gets
    EACCES on a file owned by the previous install's UID, and the index lands
    app-private.
  - The fix keeps the media row's URI per shard (`PREF_URIS`) and writes to
    it. MediaProvider's own de-duplication becomes a CLAIM: whatever name it
    gives the first time is the name kept, so there is exactly one file per
    install — and the previous install's index, which describes photos still
    on the phone, is left alone rather than overwritten by a fresh install's
    empty table. That turns out to be the RIGHT behaviour, not a compromise.
  - Landing app-private is now said out loud, in the event log and in the
    settings row ("⚠️ app-private — this copy goes when the app does"). It
    was previously reported as a path, leaving the reader to work out that
    the safety net had quietly stopped being one.
- **Rotation, finally tested on a device.** The `movableContentOf` split has
  carried a "not yet rotation-tested" note since 2026-08-19. A 2 s interval
  run went portrait → landscape → portrait and kept shooting across both
  (run badge 6 → 24 → 45), with the Sports rule still engaged, the camera
  still streaming, osmdroid still drawing after being re-parented, and no
  exception in either direction. That was the bug class the note was about:
  plain lambdas used to dispose both compositions and take the run, the
  exposure rule and the camera binding with them.
- **The interval ladder and the recording indicator were watched too, and
  both do what they claim.** The ladder draws all 21 rungs with the hovered
  band filled, its label centred inside it, and a line at the finger's exact
  height; the shutter previews the release; the bottom rung says "cancel".
  A recording shows `REC 0:06` on dark glass over a red Stop shutter, and
  sampling four frames confirms the dot alternates between #FF5252 and
  nothing while the text beside it does not move.
  - One defect, found by looking: the ladder ran the pane's FULL height, so
    its top rungs — VIDEO among them — were drawn behind the Main page's
    floating controls. It now insets by `FLOATING_CONTROLS_HEIGHT`, named
    beside the row it measures. The inset is applied to the rect used for
    the DRAWING and the MAPPING both, computed once: insetting only the
    picture would restore exactly the disagreement the control was rebuilt
    to remove.
- **Verified on the emulator (API 36), in this order:** a capture writes
  `Documents/Hillview2/photos.csv` with every column populated — position,
  bearing 5.396°, pitch 4.716°, `capturedAtUtc` 2026-09-17T13:40:43Z,
  accuracy, `bearingSource` android-compass-true, `locationSource` gps,
  `locationAgeMs` 86; four forced writes leave exactly one file; leaving the
  app writes, and leaving it again with nothing changed does not; **an
  uninstall leaves both the 322 JPEGs and the index in place**; and the
  reinstall claims `photos (1).csv` once and keeps reusing it.

## 2026-09-15

- **The photos-table dump published an absent accuracy as 0.0 m** (user-asked
  while checking where else the radius travels: "do we save gps accuracy also
  into the photos table dump and into the geo tracking dump?"). Both carry it —
  the dump has an `accuracy` column and the geo dump's locations file has
  `accuracy` and `verticalAccuracy` — but the photos dump wrote the table's
  absent sentinel through verbatim, so a reader saw a perfect fix where the row
  meant no fix quality at all. Its nullable neighbours (latitude, longitude,
  altitude, pitch) already left the cell empty; the geo dump already did too,
  because `LocationEntity.accuracy` is nullable there.
  - The absent test now lives in ONE place, `PhotoEntity.accuracyMOrNull`, and
    the upload metadata reads it through the same property instead of spelling
    `> 0` out again. The file and the wire cannot disagree.
  - The column stays non-null in the table, unlike altitude before v21: a
    receiver never reports a radius of zero, so the sentinel costs no real
    measurement on the way in. It only had to stop being published as one.
  - Both apps compile (frontend2 host tests, and the Tauri plugin that shares
    these files).

- **Backgrounding the app crashed it, on three screens** (user's phone log).
  `SerializationException: Serializer for subclass 'UploadStatusKey' is not
  found in the polymorphic scope of 'NavKey'`, thrown from
  `onSaveInstanceState` as the activity stops. `NavKey` is a library
  interface, so it cannot be sealed and kotlinx.serialization cannot resolve
  the polymorphism for us: every key has to be named in App.kt's serializers
  module. Three were not — EventLog, UploadStatus and CaptureGuide — so those
  screens worked perfectly until the app went to the background, and then took
  the process down. Backgrounding mid-upload is exactly when a user is on the
  upload screen, which is how it was found.
  - **Registered, and the list is now checked rather than remembered**
    (`RouteKeyRegistrationTest`, jvmTest). It reads both source files, compares
    the keys declared in Routes.kt against the `subclass(...)` calls in App.kt,
    and fails in both directions. Nothing about writing a screen reminds anyone
    to edit a list in another file, which is why this happened at all — and why
    a comment saying "remember to register" would not have been enough.
    Verified by deleting one registration and watching the test fail.
  - Emulator-verified end to end: each of the three screens opened, backgrounded
    with HOME, no exception and the process still alive.

## 2026-09-13

- **GPS accuracy finally leaves the phone** (user-raised while reading a
  walk whose first eighteen frames wander inside a 10 m blob before a
  9.8 m jump: "shouldn't gps accuracy go into usercomment, at least in
  frontend2?"). It never had: `SensorSnapshot.accuracyM` went only into
  the on-device EXIF `GPSHPositioningError`, which the fast-write default
  does not write and the upload never reads, and `SharedStackUploadPipeline`
  registered every row with `accuracy = 0.0` — the table's "absent"
  sentinel, so `buildUploadMetadata` omitted it. Now `PendingUpload.accuracyM`
  carries the snapshot value into `PhotoEntity.accuracy` (no schema change:
  the column existed from the Tauri era), the metadata sends it as before
  when > 0, and the worker writes the wire field `accuracy` into the
  synthesized UserComment as `location_accuracy_m` (user: bare "accuracy"
  does not say accuracy of what), beside `location_source` and
  `location_age_ms`. The Tauri app had been sending it all along; the
  worker dropped it for both clients. Measured on the 334 frames of that
  walk before the fix: zero GPS EXIF tags on any uploaded file, fix ages
  35–1142 ms, nothing that could tell the wandering frames apart. Stamp
  refinement stamps the WORSE of the two bracketing fixes' accuracies
  (user: "for interpolated fixes, it should probably use the worse of the
  two") — `worseAccuracy`, host-tested; `applyRefinedStamp` gained the
  column.
  Worker unit tests pass in the worker image; `:shared:compileAndroidMain`
  verified. Recon-side reading of the new key is
  `docs/reconstruction-field-notes.md` (2026-09-13).
- **The hold in front of manual bearing applies only where a bearing is
  RECORDED** (user: "the bearing circle, which we've made to require the long
  press to become turnable, only needs to require that in capture activity,
  not in gallery activity"). The gate buys one thing — that no single touch
  can change where the app believes you were facing when it stamped a photo —
  and in the viewer there is no photo being stamped and turning the bearing
  IS the interaction. So `BearingArrowOverlay.requireHold` follows the
  activity, through one `isRecordingActivity` that MainScreen's own
  enter/leave rule now shares. "external" counts as recording: another app's
  shutter, but this app's record behind it.
  - **The viewer is back to what the original does** — the ring is taken on
    contact and the arrow follows the finger (`ArrowArming(holdMs = 0)`, armed
    by the first movement rather than by a timer). What does NOT come back is
    the original's tap-to-set: the bearing moves on the first MOVEMENT, never
    on the press, so a tap still reaches the photo markers under the ring.
  - **And the band narrows with it**, 36 dp either side down to 18. The wide
    band was affordable only because landing on it did nothing until the hold
    was served; where a press inside it is a turn, every dp of it is a dp the
    map cannot be panned from. 18 is the original's own figure (its ring hit
    area is a 36 px stroke).
  - No closing arc and no long-press haptic in the viewer — both announce a
    wait that is not happening.
  - **Device-verified on the emulator**, which also caught up the three
    `MapGestureTest` cases that still asserted the PRE-arming contract (a
    press on the tip claiming the touch, the far side of the ring belonging
    to the map). Seven cases now: the press falls through in both modes, the
    first movement turns the arrow without the hold and pans the map with it,
    every angle grabs, and 27 dp off the ring is the map's in the viewer.
    Confirmed by hand too: the same slow drag turns the arrow and stands the
    compass down in the viewer, and pans the map in capture.

## 2026-09-11

- **Lock controls, for shooting from a pocket** (user-raised: "for when they
  literally want to keep interval-shooting from their front pocket").
  - **The gap underneath it.** A pocket run dies at the screen timeout today.
    Nothing in the capture pane holds the screen awake, and CameraX unbinds
    at `onStop`, so the display sleeping ends the shoot. Keeping the screen on
    is therefore not one of the lock's options, it is the mechanism the lock
    exists to make bearable.
  - **The scrim is the WHOLE window** (user: "nothing else than the unlock
    slider will be responsive"). A pocket touches everywhere, so guarding one
    strip guards one strip. Touches are swallowed in the MAIN pointer pass,
    not the initial one, so the slider still gets its events first — children
    are dispatched before their parent there, and swallowing early would lock
    the unlock.
  - **A slider, not a hold.** The user's call and the better one: sustained
    pressure on one spot is exactly what a pocket applies, while one long
    deliberate sweep along a line is what it cannot produce. The knob must
    travel 92% of the track, and a short drag snaps back. The track is inset
    48 dp from both edges, because a horizontal drag that STARTS at a screen
    edge is the system's back gesture rather than ours.
  - **Four settings on a page of their own**, since every one is a trade
    against particular hardware and habits: dim the screen (with a level),
    black theme while locked (free on an AMOLED, counterproductive on an LCD
    — the user's distinction, and why it is off by default), hide the system
    bars, and pin the screen. Screen pinning is Android's lock task mode and
    is the ONLY thing that reaches home and recents, which nothing this app
    draws can; it is off by default because the system asks before it starts
    and some phones refuse it outright.
  - The effects and the theme live OUTSIDE the NavDisplay, so a lock survives
    whatever screen is on top. The lock itself is session-scoped: one that
    persisted would greet whoever relaunched the app with a locked screen and
    no run behind it.
  - **The seam for screen-off is left, not built.** The settings page says so
    in as many words. It needs the run to outlive the screen, which means
    moving it off the activity's lifetime and onto a service's — a different
    size of job, and the user's own read is that Android will fight it.
  - **The first cut of the slider could not be grabbed** (user-caught, same
    day), and the way it failed is worth keeping. `detectHorizontalDragGestures`
    spends the first few millimetres NOT consuming, waiting to see whether the
    drag is really horizontal — and the scrim it sits in consumes everything it
    is left, which is its whole job. A neighbour consuming during that window
    cancels the detector. So a fast flick unlocked, because one event clears
    slop outright, and a human-speed drag did nothing at all. The gesture now
    claims the pointer on the DOWN, which removes the window; the grab is still
    targeted, with 16 dp of slack round the knob so it need not be hunted for.
  - **And the emulator test had certified it.** `adb shell input swipe` at 700
    ms jumps past slop in a single event, so the automated check exercised
    exactly the speed that worked. Repeating it at 2.5 s reproduced the fault
    at once — a reminder that an injected swipe is not a finger, and that the
    duration is part of the test.
  - Two other faults fixed with it: the knob's offset was animated during the
    drag, so it eased toward the finger rather than staying under it, and the
    track width was assigned from inside the layout's content, which churns
    the very `pointerInput` key it feeds.
  - Verified on the emulator at HUMAN speed: the knob tracks a 3 s drag, a
    half-track drag snaps back and leaves it locked, a full sweep opens it.
  - **The button moved to the opposite corner** (user, same day: "lets maybe
    just shift the lock button into the top right corner, away from the
    activity buttons"). It was the third of four in the floating row, which
    put the two presses that cost the most next to each other: reaching for
    🎞 and hitting 🔒 costs a scrim and a deliberate slider, and reaching for
    🔒 and hitting 🎞 ends the shoot. It stays one tap — it is pressed as the
    phone goes into the pocket — just a screen's width away from the rest.
  - **Which needed the corner to belong to the WINDOW, not to a panel.** The
    screen's top-right is inside the photo panel in portrait and inside the
    map panel in landscape, and both had something there already: the
    viewer's ↗ chip and the map's location/compass pair. So `PanelEdges`
    gained `ownsWindowTopEnd` (top && end — true for exactly one panel at a
    time, which the test asserts) and a single `WINDOW_CORNER_RESERVE`, and
    each panel steps aside by it only when it is the one underneath. The
    capture pane needed nothing: its Leaf already starts 52 dp down, which
    was the original's provision for the debug toggles in that corner.

- **The map's controls now know which edges are the screen's**
  (user-raised: "some controls are rightfully moved off the edge of the
  screen to lower the chances of accidental touches, but i dont know if we
  had any reason to take it so far as to offset them all... My goal is to
  free up reasonable amount of space in the center of the map panel").
  - **The distinction that was missing.** The map panel is half a split: the
    bottom half in portrait, the right half in landscape. So exactly one of
    its edges is the app's own DIVIDER and the rest are the screen's. A
    gutter at a screen edge buys something — a mis-swipe there leaves the app
    or fires a system gesture. A gutter at the divider buys nothing: the
    divider runs the whole width or height of the split and can be taken hold
    of anywhere along it. `PanelEdges.mapPanel(portrait)` is that fact, and
    MainScreen is where it is known.
  - **Window insets were the bigger waste.** `safeContentPadding()` covered
    the whole overlay, and Compose does not clip window insets to where a
    composable sits — so a gesture strip's worth of map was held back at the
    divider, against a system gesture that cannot happen there. Now only the
    screen's sides are asked for (`screenInsetSides`).
  - **A gutter goes to CRITICAL controls only**, 8 dp, and only at an edge
    that is the screen's. Critical is about what the mis-tap COSTS, not about
    the control's importance: tracking qualifies, because a stray touch turns
    the compass or the receiver off and nothing on screen necessarily says so
    afterwards. It loses its 16 dp top in portrait (the divider is above it)
    and keeps its end gutter in both.
  - **Everything else sits flush** — zoom and the north badge (user: "since
    zoom isnt critical, it can, in portrait, sit flush to the left edge of
    screen"), the hunter toggle with the two toolbars that unfold from it,
    and the debug readout. All are undone by tapping again, and the system
    insets still hold them off the status bar and the gesture strips; what is
    gone is the decorative margin on top of those.
  - The right-edge source tabs' top and bottom are CLEARANCES, not gutters —
    they keep out of the tracking row and the hunter row — so they are now
    derived from the same constants rather than being two hardcoded numbers
    that had to be kept in step by hand.
  - `movableContentOf` needed care: the map panel is ONE instance that travels
    between the portrait Column and the landscape Row, so the orientation is
    read through a `rememberUpdatedState` rather than captured, which would
    have frozen it at whichever orientation the app started in.
  - The re-parenting itself is verified (2026-09-17, emulator): the split
    turns from a Column into a Row with the run, the rule, the camera
    binding and the map all intact. The INSET work above is still only
    screenshot-checked in portrait.
  - **safeDrawing, not safeContent — found on the emulator.** "Flush" still
    left 30 dp of map down each side: `safeContent` includes the system's
    GESTURE strips, and every control was being held off them. That is the
    wrong inset family for a tap target — a tap at the very edge works, it is
    a horizontal DRAG from there that the back gesture takes. The user caught
    it by reading a town name in the gap ("can you read the Valva on the map
    left of the zoom buttons"; it was Velvary, beside the zoom column). The
    overlay now insets by `safeDrawing`, and the tracking pair asks for
    `safeGestures` BY NAME, being the one control where a swipe read as a tap
    is expensive.
  - **The jvm UI tests could not have caught this**: Compose on the desktop
    reports zero window insets, so every inset bug renders as a perfect
    layout there. The screenshot is the only instrument for this class of
    fault, which is an argument for taking one.
  - **The location button loses its fade and gains its glyph** (user: "let's
    drop the opacity, or get it in line with the other controls... let's make
    the icon inside the button normal-sized, not super-tiny"). It was drawn
    at 60% opacity when off, which made the one control that says whether the
    app knows where you are the faintest thing on the map and put it out of
    step with its neighbours; "off" is already said by the fill being chrome
    rather than blue. The ◎ moves from `titleMedium` to `headlineSmall`, the
    weight of the zoom glyphs beside it.
  - Verified on the emulator (Medium_Phone_API_36, gesture navigation, 420
    dpi) in both orientations; not on a phone.
  - **Two glyphs that were out of family.** The original's controls are ONE
    set — lucide line icons (Camera, Menu, LocateFixed, Compass, Leaf, Zap) —
    and this port lost that by reaching for an emoji per control, then
    tracing `LocateFixed` into the geometric `◎` where no emoji fitted. That
    is why the location and compass buttons could not match (user,
    2026-09-11). Within the emoji house style the answer is 📍, which is
    already the app's own word for a fix: the capture pill has shown it for
    one since it was written.
    - The per-fix FLASH moved to the button's fill. It coloured the glyph,
      and an emoji ignores that — Android draws those from the colour font
      whatever the paint says — so the flash would have gone silently missing
      the moment the glyph changed. A whole button blinking green is easier
      to catch anyway.
    - The external-camera activity is 🎞, not 🛰. A satellite says GPS, which
      is the half of that mode that is not the point — every activity here
      uses GPS. Film says "pictures being taken on something else", which is
      the half that distinguishes it. 👣 was the first suggestion and the
      user rejected it for a good reason: it would read as the compass's
      WALKING mode.
    - The real fix, if the mixed style ever grates enough: draw these few as
      vector paths and have one set again, as the original does. Not
      attempted; it is a different size of job from picking a character.

- **The location button announced a demotion a whole state early**
  (user-caught: "when i pan the map, i get the pill, so far so good, but the
  location tracking button turns mild-blue already. Mild-blue is supposed to
  indicate that location tracking is running in background and feeding into
  alt_location").
  - Right on both counts. Half-lit was driven by
    `LocationTracking.Background` alone, and that covers TWO situations here:
    exploring (panned away, prompt up, nothing claimed — the FIX is still
    what a photo records, with the map centre as the alternate) and claimed
    (the map centre records, the fix is the alternate). Only the second is a
    demotion.
  - **Why it was wrong here and right in the original.** The original
    castles the streams on the pan itself — `enterBackgroundTracking()` calls
    `setElectedLocationSource('manual')` in the same breath as it stops
    following (Map.svelte) — so "parked" and "the fix is demoted" are one
    event, and one colour truthfully means both. frontend2 deliberately waits
    for the pill's accepted claim, which puts a whole state between them. The
    colour rule was ported; the state it reads was not the same state.
  - `fixRole(tracking, mapPositionElected)` names the fix's ROLE — Off,
    Primary, Alternate — and the button renders that. The accessibility
    description follows it, which incidentally restores the original's
    vocabulary: "background" now means what its CSS class means.
  - Nothing is lost by the pan no longer showing on the button: the claim
    pill stays up until it is answered (no timeout, deliberately) and the
    blue GPS dot shows where the receiver says you are.
  - NOT phone-verified — no device reachable from this machine.

## 2026-09-10 — the bearing arrow arms before it moves

- **One touch could hand-set the heading, on an invisible target**
  (user-raised: "theres some weird hard to pinpoint handler maybe on the
  green perimeter circle? ... we should make bearing harder to accidentally
  override, lets say youd have to long-press the arrow (with some animation)
  first").
  - **What the handler was.** The arrow's own. Its tip sits at 1.3× the range
    circle's radius and its grab band runs from 0.6× the tip out to the tip
    plus a finger's slack — so the GREEN range ring falls in the middle of
    it, and in car mode with tracking on the band is the whole annulus rather
    than the arrow line. Nothing draws that band. A press inside it called
    `updateBearing` immediately AND stood compass tracking down, so a finger
    aimed at the map near the arrow silently swapped a measured heading for a
    hand-set one. Hard to pinpoint is exactly right: an invisible control
    that fires on contact is only ever found by triggering it.
  - **The grab is the WHOLE RING** now, at the arrow's tip radius, in every
    mode (user, same day: "it has to be the whole circle, i cant chase the
    arrow around"). It was the arrow line itself outside car mode, so setting
    a heading meant first finding a moving target. What a drag MEANS still
    differs by mode: car adjusts the mount offset by the angle travelled,
    everything else points the arrow at the finger. `mountOffsetDrag` is
    named for that now, having previously doubled as "the hit area is the
    ring".
  - **The press is not consumed until it arms.** The ring is a wide band
    across the middle of the map; swallowing every touch on it would cost a
    pan and every marker tap underneath. osmdroid hands each overlay every
    event regardless of what it returned last time, so the hold can be timed
    without claiming anything. The abandon slop is the PLATFORM's touch slop,
    so the instant the map decides this is a pan, the arrow decides the hold
    is over — one gesture cannot be both. The armed UP is consumed, which
    also swallows the tap a photo marker under the finger would otherwise
    receive.
  - **The gate** (`ArrowArming`, commonMain and tested): the arrow must be
    HELD for 450 ms before a drag moves anything. Arming itself points the
    arrow at the press point in absolute mode — someone who held the ring at
    south meant south, and making them drag a hair to commit it would be a
    second gesture for one intention. A press that goes nowhere
    now does nothing at all, and a finger sliding ACROSS the arrow abandons
    the attempt rather than arming at the end of its travel. The arming lives
    exactly as long as the finger — the shutter's grammar, and no mode left
    behind to be surprised by later.
  - **Standing tracking down moved to the arming moment**, which was the
    worst of the accidental override: the compass went off and stayed off.
  - **It says so now.** The handle ring is drawn in every mode, not just car
    mode, so the one control that can override the compass is visible.
    During the hold a ring closes on the FINGER from both sides and meets
    itself as control is granted, with the platform long-press haptic at
    that instant, and a ghost arrow fades in where the release will send the
    real one — without it, a press anywhere on the ring would teleport the
    arrow to a spot the user was only resting on.
  - The arming decision is made by a posted callback, NOT in `draw()`: it
    stands tracking down, and a state write from inside a draw pass
    recomposes the screen that is drawing — the same trap the arrow-stamp
    note in `MapScreen` describes.
  - A DELIBERATE divergence from the original, which sets the bearing the
    moment the arrow SVG is grabbed (docs/tauri-map-ui-contract.md, "Arrow
    grab zones", now annotated). Narrowed on 2026-09-13 to the recording
    activities only — see above.
  - Panning and marker taps over the ring are UNAFFECTED, which they would
    not have been under the first cut of this: it consumed the press to time
    the hold, and a ring-wide dead band across the map is too high a price
    for a gesture nobody makes most of the time.
  - Device-verified after all, on 2026-09-13, when the gate was narrowed to
    the recording activities: the press falls through, the hold is what takes
    the ring, and the same slow drag pans the map in capture. Still emulator,
    not a phone — the synthesized rotation vector cannot settle anything
    about the sensors, only about the touch handling, which is all this is.

## 2026-09-10

- **The photo index pays its way as the table grows** (user-raised: "i'm
  worried that saving thousands of rows is gonna lag the ui/system load? but
  at the same time, we dont want to pollute user docs with infinite number of
  per-day csvs... Space the dumps more once it's in thousands of rows, and
  switch to a new file after 10k rows perhaps?"). Three changes, each aimed at
  a different part of the cost.
  - **Sharded at 10 000 rows**, oldest first: `photos.csv`, then
    `photos-2.csv`. Only shards whose bytes changed are written, so a new
    capture rewrites ONE file whatever the table holds. The direction is the
    whole trick — newest-first would shift every row's position on every shot,
    dirtying every shard. `SimplePhotoDao.getPhotosOldestFirst` orders by
    `createdAt, id`, the id breaking ties so two photos in one millisecond
    cannot swap between dumps and dirty a closed shard for nothing.
    This also answers the "infinite per-day CSVs" half: the file count tracks
    the PHOTOS (one more per ten thousand), not the calendar.
  - **A cheap fingerprint gate.** `getPhotoTableFingerprint()` is one
    aggregate row — count, max createdAt / uploadedAt / lastUploadAttempt, sum
    version / deleted — asked before any row is materialized. Backgrounding
    the app with nothing new now costs a query instead of a full table read.
    A pure metadata edit that moves none of those (a licence change) slips
    until the next real change; the per-shard content hash still decides what
    is written, so the cost of that miss is staleness, never a wrong file.
  - **The capture pulse is size-scaled** (`photoDumpIntervalMs`): 2 min under
    a thousand photos, 10 min under ten thousand, 30 min under fifty, an hour
    beyond. Only the capture trigger is spaced — leaving the app and starting
    it are rare, important, and already cheap thanks to the fingerprint.
  - Peak memory is now one shard, not the whole table: shards are read with
    the paged query rather than `getAllPhotos()`. And the CSV is built into a
    single StringBuilder; the obvious spelling allocated a list plus thirty-odd
    strings per photo, which at ten thousand rows was most of the work.
  - NOT phone-verified — no device reachable from this machine.

- **The off-north badge is now an alarm** (user-raised: "when map is not
  north-up, and the northing button appears, can we make it really screaming
  red or something? map rotation keeps fooling me"). It was ordinary chrome
  with a red glyph in it, and it kept being missed — which is the failure that
  matters, because a rotated map does not look wrong, it looks like a
  different PLACE, and every judgement made from it is quietly off by the
  rotation. It is now filled red, larger than its neighbours, breathing
  (colour AND size, because sunlight kills the colour shift and a short glance
  can miss a full cycle), and it carries the angle in figures — "off north" and
  "off north by how much" are different questions. `offNorthDeg` is one
  function for both the appearing and the number, signed, so 350° reads as 10°
  the other way rather than as most of a turn. The animation only exists while
  the map is turned; a north-up map composes none of it.

## 2026-09-09 — the altitude that was never sent

- **`photos.altitude` is nullable (table v21).** It was a non-null `Double`
  defaulting to `0.0`, and both readers that send it to the server — the
  authorize request and the upload `metadata` blob — guarded it as
  `if (photo.altitude > 0)`. That test is wrong twice.
  - **A measured zero read as "unknown".** The sentinel and a real sea-level
    fix were the same value, the same collapse `pitch` was made nullable to
    avoid in v19.
  - **Every negative altitude was dropped, silently.** Android's
    `Location.altitude` is height above the WGS84 ELLIPSOID, not sea level,
    and that is legitimately negative across whole regions where the geoid
    sits below the ellipsoid — southern India reaches about -100 m, so a photo
    taken 40 m above the sea there reports about -60 m and lost it. The
    guard's comment says an omitted key falls back to the file's EXIF
    worker-side, which is exactly what the fast-write default does not have:
    no EXIF, no fallback, altitude gone.
  - **What the fix touches.** `PhotoEntity.altitude: Double?`, both send-site
    guards, `applyRefinedStamp` (the refiner already interpolated a nullable
    altitude and pinched it through a non-null parameter), `PhotoUtils`
    EXIF import (a file with no `GPSAltitude` now reaches the table as null
    rather than claiming sea level), and the CSV column.
  - **MIGRATION_20_21 is the first photos migration that is not an ADD
    COLUMN**: SQLite cannot drop a NOT NULL in place, so the table is rebuilt
    the way `MIGRATION_9_10` rebuilt bearings. `NULLIF(altitude, 0.0)` is what
    makes it a no-op for existing rows — a stored 0.0 was the absent sentinel
    and has never been sent, so carrying it across as a real 0.0 would start
    claiming sea level for every row that never had a fix.
  - **Verified on the emulator, not on a phone.** Both apps compile, both host
    suites are green (606), and `:shared:connectedAndroidDeviceTest` passes
    whole (282) on `Medium_Phone_API_36` — the migration test below, the EXIF
    writer and the upload claim race included.
  - **The behaviour suite's failures are NOT this change.** All of them fail
    identically with this work stashed, which is the only way to tell a
    regression from a flake and is worth the two minutes every time.
    (`DevicePhotosBehaviourTest.aCaptureShowsUpAsACard…` failed once and passed
    on retry — a real flake.) The other two are written up below; the suite now
    finishes 18 of 19.

## 2026-09-09 — neither "load-dependent" test was load-dependent

Chasing the two standing `:androidApp:connectedDebugAndroidTest` failures on a
2-core/200%-quota emulator. The tempting fix was a rule — skip under host load,
or downgrade failures to warnings. Both would have been wrong, and the reason is
worth keeping: **a load gate would have made a genuinely broken assertion
invisible on exactly the machines that expose it.**

- **`UploadCoalescingBehaviourTest` asserted the NEGATION of its own feature —
  FIXED.** Its vacuity guard read `enqueues >= burst`, counting
  `enqueue photo_upload` log lines and wanting one per capture. But
  `decideUploadSchedule` returns `Leave(why=N waiting, already scheduled)` when
  a capture arrives and work is already queued — that IS the coalescing, and it
  logs no enqueue. So the guard could only pass when every capture found nothing
  scheduled, i.e. when the burst was too slow to coalesce, which is precisely
  the case the collapse assertion twelve lines below calls unobservable and
  skips. The two bounds could both hold only in a narrow band of burst speeds.
  - The guard now counts `reconcile [capture]`, which is logged once per save
    whatever the decision. Measured across two runs: `reconciles` pinned at 5
    while `burstMs` moved 21480 → 33586 and `enqueues` swung 2 → 4. The stable
    number is the one a vacuity guard wants.
  - The collapse assertion also compared the wrong pair (`runs < enqueues`);
    every enqueue becomes a run, so those are equal in healthy operation. Now
    `runs < burst`, which is the property in plain words.
  - A false lead worth recording: the first hypothesis was logcat ring-buffer
    eviction, since the test clears the buffer but then reads it up to two
    minutes later at 256 KiB. Growing it to 16 MiB changed nothing. What
    settled it was the test's own counter line, not the pass/fail — **record the
    conditions on every run, and never gate on them.**

- **`theNoFixHatchFollowsTheMapAsWell` is failing on what looks like an APP
  bug: `hasFix` never ages. OPEN, and worth more than the test.**
  - The pane offers the hatch on `state.ready && !manualClaimed &&
    !mapPositionWithoutFix && !state.hasFix`. Instrumented at the moment of
    failure, the first three are all satisfied — `claimed=false hatchFlag=false
    status='ready' shutterEnabled=true` — and NEITHER action renders, so
    `hasFix` is stuck true.
  - `hasFix` is written in exactly ONE place: `onLocation`, when a location
    ARRIVES (PhotoCapture.android.kt:437). Nothing ages it on a timer,
    `engine.location` is a StateFlow so it re-emits only on change, and
    GeoEngine's silence watchdog re-REQUESTS location without touching
    `_location`. So once a fix has landed and the provider goes quiet, the gate
    stays open indefinitely.
  - **That is precisely the case the hatch exists for.** "Shooting underground"
    means the fixes stop arriving. On this reading a phone that loses signal
    never sees "No GPS fix — capture at the map position instead"; it keeps a
    live-looking gate around a fix that may be hours old. `staleFixWarning` is
    a pure function of `nowMs` and so does age correctly, which is probably why
    this has gone unnoticed: the WARNING appears while the HATCH does not.
  - Three fixes were tried and all failed, which is the evidence for the above:
    resetting the session election in `@Before` (the flags were already clean),
    growing the wait, and injecting a deliberately stale fix so `onLocation`
    would recompute (fused in mock mode does not deliver a location older than
    the one it last delivered, so it never arrived). All reverted; the test is
    untouched and still failing.
  - **Resolved at the level of the RULE, not yet the code** — see the position
    section and the new "Derived, not stored" section of `docs/one-state.md`
    (2026-09-09). The decision went further than aging `hasFix`: the shutter
    gates on camera readiness only; freshness and accuracy inform and never
    refuse; the state holds two records, `lastFix` (session) and `lastPan`
    (persisted), plus the claim, and the stamp is a four-row table over them
    with two words, `gps` and `map` — the original's contract; a blank first
    run writes `null` and means it. The hatch and its flag go; the claim is
    the only button. **Coded up 2026-09-09** (the Status block there says what
    moved): `FixState`/`lastFix` in the holder, the map adapter's
    `observeFixes` writer, `stampFix` into the pane and its own subscription
    deleted, `stampPosition` in commonMain with `StampPositionTest`,
    `shutterEnabled(ready)`, hatch + flag + `manual` gone, photos table v22
    with nullable coordinates and Null Island carried to null, upload omits
    an absent position. Behaviour tests restated to the new contract; the
    two "no fix" rows there are `Assume`d on an empty `lastFix`, because that
    record is process-lifetime and any earlier class's injected fix fills it
    — the rows are pinned unconditionally on the host instead. Verified on
    the emulator: host 304 + desktop 306 green, `:shared:` device suite 286
    green (incl. the v22 migration case: Null Island → null, real zeroes
    kept), behaviour suite 20 with 0 failures and 1 visible skip (the geo
    no-fix row, behind a sibling's injected fix). Two things learned on the
    device: the connected-test task UNINSTALLS the app after each run, so
    every behaviour run is a fresh install (`run-as` finds no package at
    boot) and any "app data persists on the emulator" assumption is stale;
    and the overlay's post-open hint owns the location rows for 4 s, so a
    behaviour test must not race it for the map-position note — that wording
    is pinned on the host (`CameraOverlayUiTest`), where the hint never
    fires. Not phone-verified. Awaiting the user's verdict on whether it is
    what they wanted.
    This test starts passing when the offer is derived from freshness rather
    than from the stored boolean.


- **`MigrationTestHelper` is wired up** (`PhotoDatabaseMigrationTest`, in
  `androidDeviceTest`). The migrations now run against the REAL exported
  schemas on real SQLite, and `runMigrationsAndValidate` compares the result
  with what Room generated from the entities — a migration that drifts from
  `PhotoEntity` fails there instead of on a phone at the next open. Three
  cases: the 0.0 sentinel becomes null while a negative measurement survives,
  the photos rebuild does not cascade `edits` away, and the whole v14→v21
  chain validates.
  - **What it took.** The `androidx.room` Gradle plugin replaces the bare
    `ksp { arg("room.schemaLocation", …) }`, because the helper reads the
    schema JSONs from the test APK's ASSETS and only the plugin stages them
    there. Plus `room-testing` on `androidDeviceTest`, and the migration list
    lifted out of `addMigrations(…)` into `PhotoDatabase.MIGRATIONS` so the
    builder and the test cannot disagree about which migrations exist.
  - **The unknown that had blocked it is answered.** The plugin does
    understand AGP 9.3.1 plus the KMP `androidLibrary` plugin: it knows the
    `com.android.kotlin.multiplatform.library` id by name and registers
    `copyRoomSchemasToAndroidTestAssetsAndroidDeviceTest` for it. Verified by
    unzipping the test APK — all eight `PhotoDatabase` schemas are in there.
  - **Bonus:** the schema directory is now a declared task output, closing the
    KNOWN HOLE the build file warned about (a deleted JSON went unnoticed).
    Only `frontend2` gets this; the Tauri plugin still uses the kapt argument.
  - **It fails when it should.** A passing new test proves nothing until it has
    been made to fail, so both halves were mutation-checked on the emulator.
    Dropping `NULLIF` from the copy fails the altitude case with "the 0.0
    sentinel must not become a real sea-level claim expected null, but
    was:<0.0>". Leaving `idx_photos_path` out of the rebuild fails all three
    with Room's own "Migration didn't properly handle: photos" — which is the
    schema-drift alarm that is the whole reason to have this test, and it was
    the failure mode I could most easily have shipped by eye.

## 2026-09-08 — the photo index

- **The photos table is written out beside the photos** (user-raised: "in all
  cases, we should do some periodic photos table dump into a public folder, so
  that in case of app uninstall, photos that survive it aren't useless").
  `PhotoTableDump` (androidMain) + `photoTableCsv`.
  - **The gap.** The stamp — position, heading, pitch, exposure, licence —
    lives in the photos TABLE, in the app's private database. A photo in DCIM
    survives an uninstall; the row that gives it meaning does not. With the
    fast-write default (`writeExif = false`) the surviving JPEG is a picture
    of somewhere, at some time, pointing some way.
  - **Unconditional, no setting.** A safety net with a switch is one people
    discover they had turned off. Deliberately unlike the geo-tracking export
    next door, which is opt-in and asks for a folder: a location history that
    outlives the app is a privacy decision to put to the user; a manifest of
    the photos they took and are publishing is the same data as the photos.
  - **Where: `Documents/<folder>/photos.csv`, not DCIM.** Beside the photos is
    the obvious answer and the wrong one — MediaProvider allows only images
    and video under DCIM, so a `.csv` there is refused. Documents takes any
    type, survives uninstall, is reachable to a file manager, and carries the
    same folder name as the photos. MediaStore first (no permission, API 29+,
    and it UPDATES the existing row so the name stays stable rather than
    becoming "photos (1).csv"), then the file API, then app-private as a last
    resort that at least exists while the app does.
  - **When:** app start (catches up after a crash, like the geo dump), leaving
    the app, and a five-minute pulse while shooting — an interval run in a
    pocket never backgrounds the app, so without the pulse the only trigger
    for hours would be the one that does not fire. Plus "Write it now" in
    Settings.
  - **The skip is on CONTENT, not a dirty flag.** The CSV is built, hashed and
    compared with the last one written; every mutation of the table — a
    capture, a deletion, an upload landing a server id — changes the bytes,
    and nothing has to remember to announce itself. The manual button forces,
    because the usual reason to press it is that the file is missing.
  - Every column, in entity order, with `capturedAt` repeated as readable
    UTC. Leaving a column out is a decision made on behalf of someone who can
    no longer recover it. `PhotoTableCsvTest` parses a row back with an
    ordinary RFC 4180 reader.
  - **Verified on an emulator 2026-09-17** — and it was broken in two ways
    when first watched; see the 2026-09-17 entry at the top.

- **The EXIF default is unchanged, and the question is still open.** The user
  is undecided; nothing here decides it. What the original does is worth
  putting on the record for whenever it IS decided: the Tauri app writes EXIF
  ALWAYS, and can afford to because it holds the JPEG bytes in memory and
  splices an APP1 segment in before writing the file
  (`device_photos.rs` → `create_exif_segment_structured`). frontend2 is off by
  default because CameraX writes the file itself and `ExifInterface` has no
  surgical patch, so a pass means copying the whole 4–25 MB file per shot.
  The third option neither default considers is to do what the original does —
  splice the segment into the bytes — which would make the choice moot. Not
  attempted; it means owning JPEG segment surgery on the capture path.

## 2026-09-08 — the recording indicator

- **A recording says so** (user-caught: "video recording isn't indicated in
  any way?"). It was not: the shutter stayed blue 📷 while recording, so the
  button that STOPS a recording looked exactly like the button that takes a
  photo, and `recordingStartedAtMs` — whose doc comment already promised "for
  the elapsed readout" — was rendered nowhere.
  - The shutter goes red with ⏺ and "Stop", symmetric with a run's green
    "Stop".
  - `● REC 0:12` above it, on dark glass, blinking once a second. The blink
    and the clock come off ONE ticker so they cannot disagree, and the dot
    fades rather than disappearing — a glyph that comes and goes shifts the
    text beside it twice a second, which reads as a fault. The dot-and-
    elapsed shape is the app's own, from the clock-video recorder in both
    apps; the period is the original's `blink 1s step-start`. Its own
    composable, so the ticker does not recompose the pane and its preview
    twice a second.
  - **Found while wiring it: the location gate could trap a recording.** The
    gesture tested `gateOpen` before the stop branches, so a fix lost
    mid-recording answered every press with "no GPS fix" and left the
    recording running — and the same trap held a repeating run. Stopping now
    comes first, in the gesture and in the accessibility click, and the rule
    is a named function (`shutterPressDoesSomething`) with the trap as a
    test. The gate withholds captures; it has no business withholding exits.
  - **Verified on an emulator 2026-09-17**: REC and the elapsed clock over a
    red Stop shutter, the dot alternating between #FF5252 and nothing across
    sampled frames while the text beside it stays put.

## 2026-09-06

- **The interval ladder goes sub-second, and becomes the scale it reads**
  (user-raised: "can we try to support modes faster than 1s? can we improve
  the slider? i think it should draw exactly where, on the vertical scale, is
  the gesture currently landing + highlight the current span + draw the
  seconds label right inside there").
  - **Rungs** (`IntervalLadder.kt`): cancel, 0.2 / 0.3 / 0.5 / 0.75 s, then
    1…15 s, then VIDEO. Not evenly spaced in time, deliberately: below a
    second the useful differences are proportional, not absolute. The state
    is now an INDEX into that list, and the run loop takes milliseconds.
  - **What the fast end promises.** Nothing, and it says so. A full-res JPEG
    takes a few hundred ms to issue on a mid-range phone, so 0.2 s is a
    request. The run loop already handles it: absolute timeline, wait for the
    previous shot rather than drop the beat, count each late one as
    "interval behind" in the capture stats. Asking for 0.2 s therefore gives
    "as fast as it can" plus an honest counter.
  - **The ladder is the catch zone.** The old control drew a 280 dp rotated
    Material slider beside the button while the gesture read `pos.x <
    circle.left` over the whole pane — one picture, a different hit-box.
    Now the zone itself carries the bands, at pane height, so what is drawn
    is what is read. Three consequences fall out: the head can no longer be
    clipped (it was, at common splits — the 2026-08-22 entry), the shutter
    cluster no longer grows by ~280 dp and carries the button ~115 dp up the
    pane out from under the finger holding it, and every rung gets a band the
    size it is actually selected at.
  - **Mapping is FLOOR, not round.** Each rung owns one equal band, which is
    the band drawn. The old mapping rounded against the interval COUNT, so
    the two end stops had half-height bands — harmless while the scale was
    invisible, a lie the moment it is drawn.
  - **What it draws:** every rung labelled small at the left while the bands
    are at least 14 dp; the hovered band filled with its label centred inside
    it; a line across the zone at the finger's exact height. Filled neutral
    while the thumb is still on the button, run-green or video-red once the
    finger is in the zone and a release would act.
  - **The bottom rung says "cancel", not "single"** (user-caught, same day).
    It was wrong twice over: a plain tap is what takes a single shot, and
    that rung does not take one. Releasing there is the same act as
    releasing back over the button — the original's release-over-nothing —
    so it gets the same word, and the release hint's two ways of saying it
    collapse into one.
  - **Verified on an emulator 2026-09-17**: all 21 rungs draw, the hovered
    band fills with its label centred inside it, the pointer line sits at the
    finger's height, and the shutter previews the release. One defect found
    and fixed in the same pass — the top rungs were behind the floating
    controls.

## 2026-09-04

- **The camera button rotates with the phone again** (user-raised: "in
  tauri, the camera button in main screen would rotate to indicate
  understood photo orientation"). The original's floating camera toggle
  turns with `relativeOrientationExif`, so its icon stays upright in the
  world and shows the orientation the next photo will be given
  (`Main.svelte`, `deviceOrientationExif.ts`). Ported as ONE state:
  - `DevicePoseState` (commonMain, koin single) is the twin of the
    original's `deviceOrientationExif` store. Degrees, not EXIF codes —
    this capture path already speaks degrees, and an EXIF code is the
    JPEG's business. `null` = nothing is sensing it, which is what the
    original's reset-to-1-on-unmount amounts to.
  - The ONE writer is the capture engine's existing
    `MyDeviceOrientationSensor` — the app's only pose listener, which is
    there because CameraX must be told where "up" is. It kept a private
    `@Volatile deviceOrientation` copy as well; that copy is gone, and the
    shutter reads the state like everyone else. Two copies of a
    hardware-derived fact is exactly how a reader ends up registering its
    own listener.
  - The second input is the DISPLAY's rotation, `rememberScreenAngleDeg`
    (the original's `screenOrientationAngle`). The two turn in opposite
    senses, so under auto-rotate they cancel and the icon sits still; it
    is under a rotation lock — the normal state when shooting — that the
    icon is the only thing that moves.
  - `devicePoseUiRotation` is that subtraction as arithmetic instead of
    the original's 16-row table; `DevicePoseRotationTest` checks it
    against every row of that table, in the original's own terms.
  - One deliberate divergence: the turn takes the SHORT way round
    (`nextRotationTarget`). The original animates the CSS value, so
    180° → -90° sweeps three quarters of a turn backwards. The phone did
    not do that.
  - NOT yet phone-verified — no device was reachable from this machine,
    and the emulator cannot pose a phone convincingly. What to look for on
    an A22: turn auto-rotate OFF, open capture, turn the phone; the 📷
    icon should follow the horizon within ~0.3 s and sit upright again
    once the camera closes.
- **The architecture test greps CODE, not prose** (`kotlinCodeOnly`, in
  `jvmTest/.../arch/`). The new patterns are `OrientationEventListener`
  and `MyDeviceOrientationSensor(` — names that the rule's own
  explanations have to say out loud, which would otherwise fail the test
  they document. Comments and string literals are blanked before matching;
  proved to still fire by adding a listener under `androidMain` and
  watching the build go red.

## 2026-09-26 — roll, and everything else the phone knew and dropped

**Roll never left the device.** The sensor stack has computed it since the
beginning; `BearingState` had no field for it, so the photo stamp could not
carry it and no column anywhere in the chain existed to receive it. Two
other values were in the same position: the MAGNETIC heading (carried in
the capture snapshot since the beginning and dropped by every writer, since
the EXIF tags take true north by convention) and the quantized device pose.

**The shape.** One `attitude` object, not a column each — the `alt_location`
precedent: nothing on the device queries it, it only travels, and the set
will grow. Named `attitude` and not `orientation` because EXIF already has
an Orientation tag meaning the display rotation (user-caught).

    DeviceAttitude (one state) -> SensorSnapshot.attitude
      -> attitudeProvenanceJson -> PendingUpload.attitudeJson
      -> PhotoEntity.attitudeJson (Room v24) -> upload metadata `attitude`
      -> BrowserMetadata.attitude -> PROVENANCE_KEYS -> UserComment
      -> _attitude() -> GET /photos/public/{uid}

- **`DeviceAttitude` is a new record in the one state**, the orientation
  side's twin of `lastFix`: written on EVERY compass sample by the
  allowlisted writer adapter, in BOTH bearing modes, elected or not. It had
  to go in the state — `OneStateArchitectureTest` forbids the shortcut of
  reading the engine from the tracking sink, and rightly.
- **No field duplicates a column, for a reason worth knowing** (user asked
  for the audit): `bearing` and `pitch` are the ELECTED answer and are
  DEAD-BANDED — the bearing state only updates past 1° — while the attitude
  is written past no gate. So even when the compass is elected these are the
  instantaneous reading and the columns are the last one that cleared the
  band.
- **The fake `0f` is gone.** A manual bearing row reached the tracking table
  with pitch and roll invented as `0f` (a level phone, recorded as
  measurement) and magneticHeading set to a copy of the hand-set bearing (a
  compass agreeing exactly with the hand that overrode it). New
  `GeoTrackingManager.storeBearingNamed` takes them nullable; the funnel
  passes the live attitude when fresh (`ATTITUDE_MAX_AGE_MS`, 2 s) and null
  otherwise.
- **Two accuracies, both kept.** `magnetometer_calibration` is the bare
  magnetometer's LATCHED status and rates the HEADING only (pitch and roll
  come from gravity and the gyro). `fused_sensor_accuracy` is what the
  sensor that produced the sample said about ITSELF — read and discarded in
  a commented-out log line until now. Disagreement is informative:
  magnetometer low + fusion high is a gyro on a stale field; the reverse is
  a fusion that has not settled.
- **Every key names what it measures**, not the API that produced it
  (user): `heading_true_deg`, `heading_magnetic_deg`, `pitch_deg`,
  `roll_deg`, `magnetometer_calibration`, `fused_sensor_accuracy`,
  `fusion`, `age_ms`, `device_rotation_deg`, `landscape_azimuth_negation`.
  That last one records whether the Armor-22 toggle was ENABLED; it only
  fires past 90° of roll, so `roll_deg` beside it says whether it applied.
- **`roll_deg` is NOT the camera's rotation about its optical axis.** The
  rotation matrix is remapped for the quantized pose FIRST, so it is the
  residual within that quadrant; absolute rotation needs
  `device_rotation_deg` too. Both travel for exactly that reason.
- **PUBLIC, on other people's photos** (user: "the whole of hillview is
  about sharing photos with location and orientation, and we dont want to
  limit 3d recon options to own photos"). `GET /photos/public/{uid}` serves
  it beside `location_accuracy_m`; the owner endpoint gets the same key so
  one client path reads both. Precedent was already set — `bearing` has
  always been public and `pitch` is in the map listing — and none of it
  narrows WHERE a photo was taken. NOT added to the bulk marker listing,
  which stays lean.
- **`_attitude()` is a typed projection, not a pass-through.** The
  UserComment is client-written, so serving it verbatim would put arbitrary
  JSON of arbitrary size in a public response. Known keys only, expected
  types only, `fusion` length-capped, `bool` rejected where a number is
  expected (it is an `int` subclass in Python, so `True` would have become a
  rotation of 1°), non-finite floats dropped.
- Room 23 → 24, both apps exporting an identical schema
  (identityHash `bf40b7e5a5f7da33151ad51abc7dafc5`). The CSV photo dump
  gains `attitudeJson` on the END, per the appended-column rule.
- Tests: 375 jvm (11 new, pinning the wire shape), 34 worker unit (2 new —
  the existing "every provenance key can get through" tripwire caught the
  door for free), 27 new API unit tests for the projection including
  hostile input. `test_curate_exif.py::test_dslr_without_35mm_tag` fails
  before and after this change — pre-existing, unrelated.
- **The bearings table gained the column too**
  (`BearingEntity.fusedSensorAccuracy`, GeoTrackingDatabase 1 → 2). A COLUMN and not an "extra" JSON cell, asked and
  answered: this table takes a row at 5-20 Hz, where JSON would repeat its key
  names on every row and force a parse per row on a CSV that `pics` reads
  column-wise; and the value set is a closed shape of scalars, unlike the
  photos blob, which is one row per photo and open-ended. The CSV header gains
  `fusedSensorAccuracy` on the END — verified safe: `pics` resolves every column by
  name (`gps_log.get_column_index`), reads a missing one as None, and sniffs
  the file type from the header's PREFIX.
  - The old comment "no migrations, and none coming" is gone. It was a claim
    about what the SPLIT cost, not a prohibition, and disposable data makes a
    migration CHEAP rather than unnecessary: a one-line ALTER TABLE keeps the
    session in progress where a destructive fallback would discard the tail no
    dump has reached.
  - **One value, ONE name** (user: "sensorAccuracy sounds uninformative
    though. like, what sensor"). It was `sensorAccuracy` in shared-kt and
    `fusedSensorAccuracy` / `fused_sensor_accuracy` everywhere downstream —
    three spellings of one number. Unified on the informative one, which is
    also accurate: a non-null value only ever comes from a FUSED virtual
    rotation-vector sensor, since the hand-rolled filters compose raw sensors
    and nothing rates their result.
  - `pics` does not yet READ the new column — its loader lists the names it
    resolves, so that is a one-line addition there whenever it is wanted.
- **NOT phone-verified.** Nothing in this entry has been on a real device, and
  the emulator cannot settle sensor-fusion questions (its rotation vector is
  synthesized).

## 2026-09-26 — everything the phone knows at the shutter

Plan and full record: **docs/recon-capture-metadata.md**. Driven by one
requirement — the phone should store every bit it has, raw and processed,
because the SfM bench can use all of it and a dropped value is unrecoverable.

Roll (2026-09-22) turned out to be a PATTERN, not a one-off: values the
platform hands us, captured at one layer, dropped at the next. Three more
instances closed here.

- **Five provenance objects, 42 fields, agreeing app → worker → API**, checked
  mechanically rather than by eye: `attitude` (10), `fix` (7), `lens` (14),
  `motion` (5, incl. the nested `imu_window` of 7). All served publicly, on
  other people's photos.
- **`lens` is the big one.** Nothing had read a single calibration key. Factory
  intrinsics + distortion + physical sensor size + pixel array from
  `CameraCharacteristics`; per-frame focal length, aperture, focus distance,
  rolling-shutter skew and dynamic intrinsics off the `TotalCaptureResult` the
  3A callback was ALREADY receiving — no new stream. `intrinsics_available`
  records whether the device publishes a calibration at all, because "this
  phone does not" and "this app did not look" are different claims.
- **`zoom_ratio` was the most consequential single gap.** Pinch-to-zoom has
  existed as long as the camera has, the UI prints "2.0×", and the stamp
  recorded nothing — so every zoomed photo had silently wrong intrinsics.
- **A third drop site, found on the way:** `GeoEngine`'s
  `PreciseLocationData` → `Location` conversion lost vertical, speed and
  bearing accuracy. `Location` has setters for all three; nobody connected
  them; `FixState` had no fields for them either.
- **The IMU window** (`ImuRing` → `imu_samples` table → `hillview_imu_*.csv`):
  a memory ring at `SENSOR_DELAY_FASTEST` behind `GeoConfig.imu`, so only the
  activities that produce photos pay; ±500 ms around each exposure is
  persisted, and a summary travels with the photo. Rows scale with PHOTOS
  (~100/shot) not session length (~720k for two hours) — continuous logging was
  considered and rejected on that arithmetic. Why raw samples at all: a single
  sample cannot describe an EXPOSURE, and motion blur is an integral.
- **The two focal lengths stopped pretending to be one** (user: "why dont we
  just store and display them both, since we dont understand them"). The
  camera's `FocalLengthIn35mmFormat` tag and exiftool's COMPUTED
  `FocalLength35efl` composite were collapsed with an `or`; they are now
  `focal_length_35mm` and `focal_length_35mm_computed`, and the web app shows a
  computed one as `~26 mm eq.` with both in the title. This also settles
  `test_dslr_without_35mm_tag` honestly instead of by editing the assertion.
- **Schemas:** PhotoDatabase 23 → 25, GeoTrackingDatabase 1 → 3. Both apps
  identical at every version.
- **`ImuRing` is `internal` in its own file**, not private inside the engine,
  because its wraparound and per-millisecond sequencing are real logic and were
  briefly untestable. 11 host tests.
- **`OneStateArchitectureTest`'s allowlist entry for PhotoCapture was
  widened and spelled out** — it now also calls `persistImuWindow`. The test's
  own comment says an entry that understates a file is how a violation hides in
  plain sight.
- **Tests:** 396 jvm, 403 android-host, 295 API, 111 worker, 12 frontend.
- **NOT phone-verified, and mostly not verifiable on the emulator** (synthetic
  camera, synthesized rotation vector). `pics` reads neither the new bearings
  column nor the IMU CSV yet — additive, safe, waiting for a consumer.
- **The raw samples stop at the device.** The server gets the per-photo
  `motion.imu_window` SUMMARY and nothing else. (Written here as "the samples
  reach a workstation as `hillview_imu_<ms>.csv`" — corrected later the same day:
  nothing looks an APP photo up in the tracking dumps. That export exists for
  external camera frames, which is why it lands in `a22geo/`.)
  Getting them to the server is **Phase 5** in docs/recon-capture-metadata.md:
  a top-level `imu_samples` metadata field (deliberately NOT in the UserComment
  provenance — it is a bulk artifact, not provenance), gzipped through the
  existing `POST /photos/upload-file` bulk path the renditions and DZI tiles
  already use, a `photos.imu_samples_url` column, and — the step most likely to
  be forgotten — the DELETION sweep, which leaks a file per deleted photo if it
  is not taught the new column.

## 2026-09-22

- **"Press ignored: previous shot still in flight", permanently** (field
  report: only leaving and re-entering the capture activity cleared it).
  The controller's flag was fine; the SHUTTER GESTURE held a stale copy of
  it. `CaptureScreen` reads `val state = capture.state` once per
  composition, and the shutter's `pointerInput` closes over that value,
  restarting only when one of its keys (gateOpen, repeating,
  state.recording) changes. Stopping a run sets `repeating = false` — a
  key — so the handler restarts; if the run's last shot was still in
  flight at that instant, the new lambda captured `capturing = true` and
  kept it forever, because every later press returned at the guard before
  anything could change a key. Also reachable by a camera rebind
  (resolution / JPEG quality / still mode) or a recording edge landing
  mid-shot.
  - **Fix:** the guards read the CONTROLLER live — `capture.state.capturing`,
    `.recording`, `.ready`. A key would be the wrong cure: `capturing`
    toggles per shot, and restarting `pointerInput` cancels the gesture in
    progress, including the press meant to stop a run.
  - **Third of its kind** in this file (the run loop's launch-time guard;
    recording becoming a key). The rule: anything a gesture lambda reads
    from a controller must be read THROUGH the controller, not from the
    composition's snapshot.

## 2026-09-19

- **The GPS fix dot draws over the photo markers** (overlay order in
  MapScreen.android.kt: range, markers, GPS dot, arrow, rotation). It used
  to sit under them and vanish in a pile. The dot overlay takes no touches,
  so marker taps are unchanged. Compiled, not phone-verified.

## 2026-09-18

- **The shutter gesture has no cancel rung, and the button's side of the
  pane is a capture** (user: "remove it from the bottom and make the right
  side of the pane show that it means capture"). `INTERVAL_LADDER` now
  starts at 0.2 s; everything right of the button — the pane minus the
  ladder — is `CaptureZone`, drawn like the ladder (the hit-box at its
  size, blue when a release would act, "📷 capture" in the middle), and
  releasing there takes ONE photo. The verdict line under the button says
  "release: capture". A stated divergence from the original's
  release-over-nothing (contract doc updated). The way out is off the
  pane: a release on the map does nothing, and the verdict says
  "release: cancel" there. `intervalIndex` is rememberSaveable, not
  persisted, so dropping the foot rung shifts no stored value. Tests:
  ladder tests updated, `CaptureZone` render test added. Compiled and jvm
  tests green; NOT phone-verified.

## 2026-09-03

- **Settings tidy-up.** Wi-Fi only sits directly under Auto-upload again
  (the geo export and GPS-interval controls had been inserted between
  them); the two DCIM storage targets are listed together (display order
  only — `PhotoStorage.chain` keeps the enum order for fallback); each
  licence radio carries a label and a two-sentence explainer
  (`LicenseInfo`, next to `ALLOWED_LICENSES`), and "About these licenses"
  opens the web app's /licensing page. The full1 wording separates the
  GRANT (full, to Hillview) from what Hillview does with it today:
  publishes the photo as all-rights-reserved PLUS the same OSM mapping
  grant the CC option carries (user, 2026-09-03 — the read-side name
  'arr' undersells this). 2026-09-07: the web app's /licensing page, its
  label table, the JSON-LD comments and both licence docs now say the
  same; the id 'arr' itself is KEPT by decision (shipped clients compare
  against it — compatibility project, not an edit), with the debt written
  up under "Known debt" in docs/todo/content-license-model-draft.md. The
  device-photos per-photo picker shows the same labels.
- **API URL is a combobox** (`serverPresets`: Production =
  `HILLVIEW_API_URL` = https://api.hillview.cz/api, Local dev = the
  platform default) under ▾ on the field; anything else is typed. Still
  the FULL …/api URL either way — the production API has its own host,
  which is why it is never derived from the web root.
- **Hiding photos — what current Android actually does** (AOSP
  MediaProvider `FileUtils.isDirectoryHidden`, checked 2026-09-03): a
  directory is hidden from the media collections when its name starts
  with "." OR it contains `.nomedia`; hidden status is inherited by
  subdirectories; `.nomedia` in a top-level default directory (DCIM,
  Pictures…) or in DCIM/Camera is DELETED by the provider, so only a
  subfolder can be hidden. On a MediaStore insert the provider rewrites a
  hidden name to "_" + name (`sanitizeDisplayName(rewriteHiddenFileName)`),
  which is the `_.Hillview2` we saw. Google Photos reads the same index, so
  a hidden folder is neither shown nor backed up. Android's own advice
  for media "that provide value to the user only within your app" is
  app-specific external storage (Android/data/<pkg>/files), which the
  index never touches. So the three honest options are: app-private
  folder (invisible, gone on uninstall), a hidden DCIM subfolder
  (dot-name or `.nomedia`, both equally supported), or visible.
- **Hidden means a direct file write** (decided after the research
  below): `PhotoStorage.chain(preferred, hideFromGallery)` leaves the
  MediaStore target out while hiding is on, `outputOptions` refuses
  MediaStore+hidden as the safety net, the MediaStore option's note says
  so, and the switch text says what it is (a second, hidden folder for
  NEW photos; earlier ones stay). Device test `hidingLeavesTheMediaStoreOut`
  added (compiled, not run — needs a device).
- **GPS fix interval control hidden** (`GPS_INTERVAL_SETTING_LIVE` in
  SettingsScreen.kt) until the value reaches the hardware; the persisted
  setting and the BindGeoToActivity seam stay.
- **Clock video is out of the ⋮ menu** (`CLOCK_VIDEO_IN_MENU` in
  MainScreen.kt, a lab tool for the pics pipeline); screen, route and
  callback stay wired.
- **OPEN — the GPS fix interval setting never reaches the hardware.**
  `GeoEngine.startLocation` constructs `PreciseLocationService` without an
  interval, and the service hard-codes 1 s (`UPDATE_INTERVAL` /
  `FASTEST_INTERVAL`, shared-kt). The slider therefore only drives the
  restart-on-change branch of `applyConfig` and the event-log line
  ("fixes Nms"); `mapOnlyGeoConfig`'s 2 s is equally nominal — every
  activity gets 1 s fixes. Fix = an interval parameter on
  `PreciseLocationService` (default 1000, so the Tauri plugin is
  byte-for-byte unchanged) passed from `startLocation`. Two more things
  the fix must know: the view activity ignores the setting by design
  (`mapOnlyGeoConfig`), and the external-camera SERVICE claims
  `externalCameraConfig()` with the default, so the engine's min-of-claims
  merge pins external mode at 1 s whatever the setting says — pass the
  setting to the service's claim too. Eco mode is camera-only
  (`ecoFps` → preview duty in PhotoCapture); it never touches geo.
- **"Hide from gallery" is a folder choice, not a flag.** It saves NEW
  captures into `DCIM/.Hillview2` (or the private folder's `.Hillview2`),
  which the media scanner skips, and skips the explicit post-save scan.
  Photos already taken stay where they were, and the Device photos list
  is database-driven, so nothing disappears. With the MediaStore target it
  cannot apply, and MediaProvider renames the folder to `_.Hillview2` on
  the way in — so hide+MediaStore currently lands photos in a THIRD
  folder, visible. What the switch should MEAN is an open decision; the
  Tauri version (dot-folder plus a `.nomedia` marker) was experimentation,
  not a template.

## 2026-08-29

- **Anonymization options** on Device photos (the original's modal: auto /
  none, custom noted): an edit → the drain applies it → targeted re-upload.
  Device-verified end to end.
- **Crash on Back (field: "back button, or an accidental gesture around
  it").** Reproduced: `IllegalArgumentException: NavDisplay backstack cannot
  be empty` — a system back gesture followed by a tap on "← Back" while the
  pop animation still runs; the leaving screen is still touchable, pops a
  second time, and nav3 throws on the empty stack. Every pop now goes
  through one guard that never removes the root. (The event-log theory was a
  false lead; CrashLog from the same day would have said so in one line.)
- **"Shutter dead until restart" (field report, not reproduced here).** The
  gesture loop calls the camera from inside `pointerInput`; an exception
  escaping it killed the handler until a key changed, which after a run none
  does. The loop now survives any exception, and a press that is ignored
  says why in the status line (`⚠️ press ignored: …`) — so if it recurs the
  phone names the cause. Emulator note: uiautomator dumps go blind (root
  node only, "Skipping invisible child") while a Compose dialog is up and
  after some capture sequences; taps still land, screenshots still work.
- The local backend had lost its test users (401 everywhere, two jvm tests
  "failing"); `POST /api/debug/recreate-test-users` fixed it.

## Closed on 2026-08-28

- **Position's second stream (`alt_location`).** The one-state rule's open
  half is closed: two streams, swapped on confirmation, the other riding
  along — see the table in [one-state.md](one-state.md). Room v20 (both
  apps' schemas exported, hashes match); the backend already synthesizes
  the field into the UserComment provenance. Device-verified in all three
  states.
- **Viewer: inline pinch-zoom + ↗ to the web app.** This pane zooms and no
  more; the original's promotion threshold (1.15) now decides inline-stays
  vs snap-back, and the zoom view lives in the web app behind an unobtrusive
  chip (server photos only, the share URL's deep-link shape). Verified by a
  Compose test that pinches — adb cannot — which needed
  `kotlinx-coroutines-swing` in jvmTest for a desktop `Dispatchers.Main`;
  every lifecycle-collecting screen is now composable in a jvm test.
- **Motion shoots default to Sports** — interval runs and video — only from
  Auto, only for the shoot's lifetime.
- **Upload: one scheduler, one drain**, as a fence
  ([upload-one-funnel.md](upload-one-funnel.md) + `UploadFunnelArchitectureTest`).

Emulator notes from the session: it needs `-no-window -gpu
swiftshader_indirect` from a shell without a display, and its system_server
can die once after a headless boot (DeadSystemException) — relaunch the app
and carry on. Never run a Gradle build beside it on this box.

## The rule the geo bugs keep breaking (2026-08-20)

Every one of them — the capture pane's private pitch subscription, the
external pane's second heading, MapScreen's duplicated tracking intents,
TrackingPhase hidden in a composition, the service configuring the engine Off
while the activity configured it on — is the same violation: something other
than the one state answered "where am I / which way am I facing".

Written up as [one-state.md](one-state.md), pointed at from
`frontend2/CLAUDE.md`, and enforced for the read side by
`OneStateArchitectureTest`, which walks the source tree and fails the build
on a new side channel. (Its Gradle wiring declares `src/` as a task input;
without that a violation added under androidMain leaves `jvmTest` up to date
and the check silently unrun.)

## The map arrow freezing while the readouts move (open, 2026-08-21)

Reported after the sensor work landed: readouts fine, arrow stuck after
unbackgrounding — and the map still pans on GPS, so the canvas is not frozen.

That combination points away from the geo chain entirely. The arrow is drawn
by osmdroid from a value the `AndroidView` update block copies out of the
bearing state; the GPS follow is coroutine-driven (`snapshotFlow`) and needs
no recomposition. So an update block that stops re-running gives exactly this
picture: every Compose readout tracks, the map still moves, the arrow holds
its last handed value.

NOT reproduced on the emulator — a HOME cycle, and a 45-second backgrounding
behind another app with `send-trim-memory RUNNING_CRITICAL`, both left the
arrow tracking (86k–92k pixels differing across a heading change, against a
71k baseline). So the readout carries the instrument instead:

    🗺 arrow 24s @307.7° Δ0.0°

Δ is the tell, not the age: a still phone legitimately shows a climbing age
with Δ0, because the block only re-runs when something recomposes. A large Δ
means the overlay is holding a bearing the state has moved on from — the
drawing stopped, not the sensors.

## The interval ladder's head is clipped at common splits (2026-08-22)

Found while fixing "i keep missing that the interval mode is about to
start": the 280 dp track plus its head label is taller than the capture pane
at ordinary split positions, so the head — which was the ONLY indicator of
the armed state — renders off-pane. The user was not missing the signal; the
signal was not on screen.

A second finding closed the loop (user-supplied): the gesture accepts ANY
point left of the button (`pos.x < circle.left`) — the thin track is a
picture, not the hit-box — but nothing said so, and precision-aiming at the
line was the real failure mode. While the slider is open, the whole catch
zone now wears a wash that tints with the armed state (neutral / run-green /
video-red), so the affordance is the hit-box rather than the line.

The armed state also moved to the one place that is always visible: the
shutter itself previews what release will do (green ▶ Ns for a run, red ⏺
REC for video, blue 📷 otherwise) with the verdict spelled out under it
("release: start 4s run" / "release: record" / "release: cancel"). The
ladder head keeps only the compact stop label; nothing that must be seen may
live there. The track itself still works while partly clipped — the gesture
has pointer capture, so stops above the pane edge remain reachable by
sliding to the top of the screen — but a shorter track at small pane heights
would be the proper follow-up if it bothers anyone in practice.

**Closed 2026-09-06, the other way round:** not a shorter track but no
separate track at all. The ladder IS the catch zone, so it is exactly as
tall as the pane and cannot be clipped. See the 2026-09-06 entry.

## Deferred decisions

**Marker refresh on capture, vs the original's placeholder markers
(2026-08-20).** A photo just taken is in the database but not in the marker
set, which is refetched on viewport change — so it stayed invisible, and out
of the viewer's ring, until the map happened to move. Fixed by telling the
map that a row landed (`CaptureEvents`), which works because frontend2 writes
the row synchronously in the capture path.

The Tauri app covers the same gap with PLACEHOLDER MARKERS
(`placeholderInjector.ts`): an optimistic photo carrying the id the real one
will get, injected at the shutter, re-embedded into every update, scoped to
the viewport so it cannot become an off-screen ghost, and removed when the
real row arrives. It needs that because a capture there crosses the
JS/native boundary and the row appears much later.

Revisit when optimising for BATTERY: our version costs a refresh per photo,
which in interval mode is a query every couple of seconds for a whole shoot,
where injection costs nothing. Cheapest fixes first: refresh only the device
source rather than the composite; conflate bursts into one refresh; or adopt
placeholders and let the periodic refetch reconcile.

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
0f. **External camera activity — LANDED 2026-08-09.** A PANEL ACTIVITY
   beside capture in the same slot (the app's word for a panel-level
   concept, and the code's: `MapSettings.mainActivity`; "mode" is taken
   several times over — BearingMode, StorageMode, eco mode, sensor
   fusion MODE_*) (user's framing: "just another panel mode
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
   climbing, clean stop on leaving. STILL OPEN here: per-activity sensor/GPS
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
   activity SHIPPED as a panel mode (0f); the per-activity rate defaults are
   what remains of this item — tracked as C4, and blocked in practice on
   the sensor hub (C1), which is where rates would get one owner.

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
4. **PiP float mode — LANDED 2026-08-09.** The map floats in a PiP window
   over the phone's camera app while the external-camera activity records
   position and heading for stamping those photos afterwards. Entry point
   is "Float over camera" in the external pane: it shrinks to PiP and then
   launches the camera app, in that order, so the map is already floating
   when it appears. Offering it ONLY there is what releases our camera —
   that activity holds no stream, so the hand-over is a consequence of the
   design rather than a step that can be forgotten (whoever is TOP evicts
   lower camera clients).
   The float window draws the map and NOTHING else: MainScreen returns a
   bare MapScreen with `showControls = false`, since at PiP size the
   overlay controls cover most of the window and cannot be hit anyway
   (first build had them; the screenshot showed it immediately).
   Two things the device taught: `onPause` must keep the activity
   reference when `isInPictureInPictureMode` (PiP pauses while still
   rendering, and float mode needs that reference); and external-camera
   recording had to move OFF the pane's DisposableEffect onto the ACTIVITY
   — float mode strips the pane out of composition, so a lifetime tied to
   its visibility stopped recording at exactly the moment it mattered
   most. Same rule as the geo engine: the activity decides, panes observe.
   Verified: window `pinned` at 16:9, camera app on top, rows still
   climbing (+56 bearings/+8 fixes in 12 s), and a clean round trip back
   to fullscreen with recording never stopping.
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

## 2026-09-26 — the raw window reaches the server

Phase 5 of **docs/recon-capture-metadata.md**, built and verified end to end.
The samples had stopped at the device: reachable only as a tracking CSV pulled
off the phone by hand, and only with auto-export on. The server got the summary
and nothing else. The user's requirement was that the 6 s window travel with the
photo, and now it does.

- **A second pipe, beside the provenance one.** `imu_samples` is a top-level
  metadata field, DECLARED in `BrowserMetadata` and deliberately absent from
  `PROVENANCE_KEYS` — the only key of which that is true. The worker gzips it
  onto the same road the renditions and DZI pyramids take (`_get_size_url`), and
  `photos.imu_samples_url` keeps a URL. `exif_data` is read wholesale on every
  photo detail request; a time series in there would be paid for by every reader
  of every photo, forever.
- **Columnar, delta-encoded, inspectable.** One object per sensor, `dt_us` with
  n-1 gaps from the MONOTONIC clock (the wall clock can step under NTP), rounded
  to each sensor's real resolution. Measured: a 2 s trimmed window is 40 KB of
  JSON, 13 KB gzipped — 0.3 % of the JPEG. Not base64-packed: about the same size
  after gzip and unreadable when a pipeline misbehaves.
- **A bug the earlier day's tests could not see: `stored_count` was 0 on every
  photo.** The capture path computed it; the pipeline's deferred rewrite of
  `motionJson` rebuilt the window record without it and let it default. That is
  the one number a server needs to concatenate a run without double-counting.
  The fix needed a bound nobody had identified — `storedFromMs`, where a photo's
  claim on the sample stream begins — which turned out to be the thing that makes
  the on-device trim actually reach the wire: without it each photo's payload
  would still carry its whole ±3 s window and the same samples would travel three
  times in an interval run.
- **DECISION: the payload is held on the photo row** (`PhotoEntity.imuSamplesJson`,
  v26), not re-read from the tracking table at send time. That table is cleared
  five minutes back on every dump while an upload can retry hours later on a
  phone that had no network. Costs tens of kilobytes a row; buys the guarantee.
  There is no pruning after upload yet — see "Still open" in the plan.
- **DECISION: the delete sweep changed shape rather than gaining a parameter.**
  Every caller built `[photo.sizes for photo in photos]`, and once a second
  artifact column exists nothing about that line looks wrong. So the unit became
  an artifact record (`photo_artifacts`) and `delete_photo_files_for_sizes`
  became `delete_photo_files_for_artifacts` — a rename cannot be silently
  skipped. New artifact columns go in `_PHOTO_ARTIFACT_URL_COLUMNS`.
- **Verified against the live stack**, not only in units:
  `backend/tests/integration/test_imu_samples_artifact.py` (5 tests) drives the
  real secure upload and asserts the round-trip through the storage pool, the URL
  on both the owner and public endpoints, absence staying absent, a malformed
  payload dropped WITHOUT failing the photo, and that the samples never enter the
  UserComment. Alembic `036_photo_imu_samples_url` is applied to dev.

## 2026-09-26 — attribution becomes data, and a race becomes a condition

Follow-up to Phase 5, and a correction to it. Two bugs in what had just been
committed, both found by tracing what a phone would actually produce rather than
by a failing test.

**The payloads overlapped.** Attribution was DERIVED: each photo claimed
`[first sample it stored, capturedAt + 3 s]`. That looks right and is not — a
capture stored in two bursts (an inline pre-shutter write and a deferred
post-shutter one) and the bursts interleave ACROSS photos, since photo 2's inline
write lands before photo 1's deferred one. Traced on a 2 s interval run, two
consecutive photos' ranges overlapped by three seconds: 44 sample-slots for 32
distinct samples. The on-device trim was saving phone storage and nothing else.

Fixed two ways. The pre-shutter call is now **read-only**
(`summariseImuWindowBefore`), so each capture stores exactly ONE contiguous burst.
And what that burst holds is recorded as a row — **`imu_claims`**, one line per
photo: `capturedAtMs, fromMs, toMs, sampleCount`. GeoTrackingDatabase v3 → v4.

**DECISION: a claim per photo, not an owner column per sample.** Stamping every
sample was the first instinct; the user refused it on bytes and was right. Six
bytes per row is ~33 KB per photo in the tracking database and ~14 more characters
per row in the CSV dump — tens of megabytes an hour at continuous rates. A claim
is ~24 bytes per photo for exactly the same answer, about a thousandth of the
cost. `ImuAttributionTest` (5 tests) is the regression test the derived scheme
would have failed; it also pins that an unowned continuous flush is not inherited
by the next capture.

**The window's later half arrived by luck.** The upload pass waited out the SAME
deadline as the engine's deferred write — `capturedAt + half + settle`, one on the
engine's Handler and one on `Dispatchers.IO`, with no ordering between them — and
then read the table. Now it waits for the claim row to EXIST, and the claim is
written in the same coroutine as the samples and after them, so its presence
proves they landed. A race became a condition.

Cost of the read-only pre-shutter call: if the app dies inside the ~3.15 s after a
shutter, that photo has no samples. It keeps the summary, so peak acceleration and
angular rate survive — the shape of the signal is what is lost, for the last shot
before a crash only.

Also: `stored_from_ms` was added and then removed again. With a claim table the
wire needs only the count, and the payload's own `t0_ms` says where it starts. And
the dump now writes `hillview_imu_claims_<ms>.csv` beside the samples.

**Removed, same day.** ("what is dumping the claims table good for?", then: nobody
looks up an app photo in the dumps at all — the pipeline reconciles them with
EXTERNAL photos.) Both are right, and together they leave the export with no
consumer: claims describe app-photo attribution, `pics` reads the dumps for
external frames, and an app photo carries everything in its own upload. The
reconciliation the export was kept for turned out to be doable entirely
server-side — `motion.imu_window.stored_count` and the payload both arrive, so
they can be checked against each other with nothing from the phone. That is now an
assertion in `test_imu_samples_artifact.py` instead of a CSV, which is strictly
better: automated rather than manual, and it runs on every integration pass.

The original overclaim, for the record:
the justification above was wrong, and the code comment repeating it has been
fixed. Every photo carries `capturedAt`, so slicing the samples CSV by
`capturedAt ± IMU_WINDOW_HALF_MS` gives that photo's window with no claim
involved. Claims solve a WIRE problem — keeping one sample out of three
consecutive photos' payloads — and offline the whole stream is in one file, so
there is no duplication to avoid. What the dumped claims are actually good for is
RECONCILIATION: checking that the per-photo payload the server received matches
what the phone attributed to that exposure. Diagnostic, worth its few dozen bytes
while the upload path is being verified on real hardware, and a candidate for
deletion afterwards rather than a permanent part of the export.

Verified: 399 jvmTest, 421 androidHostTest, 296 API unit, 145 worker unit, 5
end-to-end, `:androidApp:assembleDebug`. GeoTrackingDatabase v4 identityHash
matches across both apps, and both databases' full migration chains were validated
against the exported schemas on real SQLite (`PhotoDatabaseMigrationTest` is an
androidDeviceTest and had never run, so 25→26 was unchecked until this).

## 2026-09-26 — the phone crash: FASTEST needs a permission

First run on a real phone, and the app died on startup:

```
java.lang.SecurityException: To use the sampling rate of 0 microseconds, app
needs to declare the normal permission HIGH_SAMPLING_RATE_SENSORS.
    at cz.hillview.geo.GeoEngine.startImuSensors(GeoEngine.kt:814)
```

`SENSOR_DELAY_FASTEST` is 0 µs, and since Android 12 any rate above 200 Hz needs
`HIGH_SAMPLING_RATE_SENSORS` — a NORMAL permission, granted at install with no
prompt. `registerListener` does not clamp the rate, it THROWS, and
`startImuSensors` runs from `applyConfig` on the main thread, so the whole process
went down. Nothing in the host test suites could see it: it needs real hardware,
and the emulator's synthesized sensors never exercised the path.

Two fixes, because the permission alone is not enough.

- **Declared the permission** in `frontend2/androidApp/src/main/AndroidManifest.xml`.
  This is the intended answer: the high rate is the point of the window — the
  shape of the signal across a 1/60 s shutter, which 200 Hz cannot describe.
- **Guarded the registration.** No sensor this engine opens for a nice-to-have
  may be able to kill the process. `registerImu` tries FASTEST, falls back to
  `IMU_UNPRIVILEGED_PERIOD_US` (200 Hz, the ceiling that needs no permission),
  and gives up with a log if both are refused — catching `SecurityException` and
  `RuntimeException`, and unregistering partial success so a window can never come
  back with an accelerometer and no gyroscope while reading as "this device has no
  gyroscope".

Audited every other `registerListener` while here: the engine's other rates are
30 ms and 100 ms (33 Hz / 10 Hz), well under the threshold, and
`EnhancedSensorService` already logs a refusal. `startMotionSensors` registers at
`active.sensorDelayUs`, which `mergedConfig` can compute as 0 — but
`sensorsWanted()` gates on `active.sensors`, which is only true when a claim
supplied a real rate, so 0 is unreachable. Both IMU configs set `sensors = true`,
so that same gate does not strand the IMU either.

## 2026-09-26 — the window was landing after the upload had left

The crash fix worked (`IMU ring registered at FASTEST (ACCELEROMETER, GYROSCOPE)`)
and the claim machinery worked — `owns 4776 (claim 1790442825945..1790442831944)`,
and `Dumped 1 IMU claims`. But the upload that followed carried
`"imu_window":{"sample_count":2388,…,"stored_count":0}` and **no `imu_samples` key
at all**: the capture-time pre-shutter summary, not the deferred rewrite.

`uploadHoldUntil` had ONE holder. It was set to `now + UPLOAD_HOLD_MS` only
`if (eligible)` — eligibility being the stamp refiner's, nothing to do with the
IMU — and the refiner cleared it to 0 the moment IT finished. So:

- a photo the refiner did not want had **no hold at all**, and its window, written
  ~3.15 s after the shutter, could never reach an upload;
- a photo it did want got freed when the refiner finished, which is earlier than
  the window's deadline, so the row was claimed and re-read before the window
  landed.

The drain's re-read-after-claim is correct and stays; what was missing is that the
row was claimable too early. Now the hold is the LATER of the two deadlines, and
`clearUploadHold` became `releaseUploadHold(photoId, notBefore)` — floor-aware,
because a hold with two holders cannot be released by whichever finishes first.
The refiner is handed the IMU floor and releases to it rather than to 0.

`IMU_UPLOAD_HOLD_MS` is derived, not picked: the window's later half + the
engine's settle margin + the worst-case claim wait + a second for two database
writes. Changing the window changes it. For a refiner-eligible photo this is
strictly FASTER than before (the row frees at ~9 s instead of waiting out the 60 s
refiner hold when the refiner finishes early); for one the refiner ignored it is
9 s instead of 0.

Also seen in the log, not an error: `Method exceeds compiler instruction limit:
17574 in CaptureScreen`. ART declining to optimize one very large composable and
falling back to the interpreter for it. A performance note about a method that has
grown too big, worth splitting, and unrelated to correctness.

**Superseded the same day** — see the next entry. The deadline-only version of
this fix was still a timeout, and the user said so: "this all still seems like a
race condition waiting to happen." They were right twice over.

## 2026-09-26 — the upload hold gets named holders

The previous entry's fix was a longer timeout wearing a dependency's clothes, and
the user called it: *"idk, this all still seems like a race condition waiting to
happen."* It was. The pass started polling for the claim at T+3150, could wait 5 s
for it, and the hold expired at T+9150 — leaving ~850 ms for two database writes.
On a busy device the upload still left first, silently. Tuning that margin makes
the race rarer, not absent.

The second attempt kept one deadline and had each holder release down to the
OTHER's, which is sound arithmetic while the two deadlines differ. **They were
equal** (both `UPLOAD_HOLD_MS`), so neither release lowered anything and every
photo would have waited the full minute. `UploadHoldTest` failed on exactly that
case before the code shipped — the first time in this whole stretch of work that a
test, rather than a phone or a hand-trace, caught the bug.

So the holders are NAMED. `photos.uploadHoldReasons` (v27) is a bitmask —
`UPLOAD_HOLD_REFINER`, `UPLOAD_HOLD_IMU_WINDOW` — each holder clears its own bit
with `releaseUploadHold(photoId, bit)`, and the drain's selection became
`(uploadHoldReasons = 0 OR uploadHoldUntil <= :now)`. The row goes as soon as the
last holder is done, in either order, with no waiting. `uploadHoldUntil` is now
**crash recovery only**: the escape hatch for a holder that died mid-enrichment.

Two holders cannot be encoded in one deadline. That is the whole lesson, and it
took two wrong answers to get there.

`UploadHoldTest` (9 tests) pins it: neither holder frees the row alone, either
order frees it immediately once both are done, a holder clears only its own bit, a
repeated release is idempotent, a photo the refiner ignores is still held for its
window, a row nobody owes is claimable at once, and a dead holder still gets freed
by the deadline.

Verified: 399 jvmTest, 430 androidHostTest, `:androidApp:assembleDebug`,
PhotoDatabase v27 identityHash matching across both apps, and the 26→27 migration
validated against the exported schemas on real SQLite.

## 2026-09-26 — `motion` becomes `inertial`, and `attitude` stays

Asked before deploying whether the attitude/motion split makes sense and whether
`attitude` is the right key. Full reasoning in
**docs/recon-capture-metadata.md**; the short version:

- **`attitude` stays.** It is the A in AHRS and `MadgwickAHRS.kt` is already in
  this tree, so it is house vocabulary. The alternative, `orientation`, collides
  with the `orientation_code` key the same metadata already carries — the EXIF
  `Orientation` tag, about how to rotate an image for display. That collision is
  why the object was renamed away from `orientation` originally.
- **The split stays, but `motion` was misnamed.** Its flagship field is `gravity`,
  which a still phone reports at full strength. An object called "motion" whose
  most important value is largest at zero motion misleads every reader once.
  Renamed to `inertial`, which covers gravity, linear acceleration and the
  window's angular rates honestly.
- **Rejected: moving `gravity` into `attitude`.** Tempting, since gravity
  constrains two rotation degrees of freedom. But every provenance object carries
  one sensor family, one `age_ms` and one trust story, and gravity's timestamp is
  not the fused attitude's — a merged object would have two ages and no way to
  attribute either. Separation also keeps the independence visible: gravity is the
  accelerometer's opinion about down, `attitude.pitch_deg` is the fusion's, and
  comparing them checks the fusion.

Mechanically: `motionJson` → `inertialJson` (PhotoDatabase **v28**, an
`ALTER TABLE … RENAME COLUMN`), `motionProvenanceJson` → `inertialProvenanceJson`,
the metadata key, `BrowserMetadata.inertial`, `PROVENANCE_KEYS`, the API's
`_INERTIAL_FIELDS`/`_inertial`, and both detail responses. Hardware-facing names
keep Android's vocabulary deliberately — `DeviceMotionSample`,
`startMotionSensors`, `GeoEngine._motion` are named for the sensor family
(`TYPE_GRAVITY`/`TYPE_LINEAR_ACCELERATION`), which is legitimate at the hardware
boundary; the rule that names describe what is MEASURED applies to the wire.

Verified: 401 jvmTest, 430 androidHostTest, 296 API unit, 145 worker unit, 6
end-to-end, `:androidApp:assembleDebug`. v28 identityHash matches both apps and
27→28 was validated against the exported schemas on real SQLite.

## 2026-09-26 — the continuous-IMU switch, and what the phone said about lenses

**`lens.intrinsics_available` was already answered** by the log from the real
device, and filed as unanswered by me — the user caught it. It is **false**: no
factory `LENS_INTRINSIC_CALIBRATION`, no `LENS_DISTORTION`,
`focus_distance_calibration` `uncalibrated`.

That vindicates having captured sensor geometry separately from the calibration.
`focal_length_mm` 5.58 with `sensor_physical_size_mm` [7.39, 5.55] and
`sensor_pixel_array` [4624, 3472] derive a pinhole model, and it is
self-consistent to **0.02 %** — fx 3491.5 px against fy 3490.8 px, square pixels,
which is the check that the three numbers are real rather than placeholders. So a
solver gets a usable focal prior on a phone that publishes no calibration at all,
and `intrinsics_available: false` does the job it exists for: distinguishing "this
device publishes none" from "this app did not look". `rolling_shutter_skew_ns` is
also a measured 31.1 ms now, not a hypothetical.

**The continuous-IMU toggle** (`ExternalImuSettings`, prefs-backed, default ON).

The interesting part is not the switch, it is that `imuContinuous` has **two
claimants** — the activity binding and `ExternalCameraService` — and
`GeoEngine.mergedConfig` resolves it with `any { it.imuContinuous }`. So a switch
that only told one of them would appear to do nothing: the other's stale `true`
wins. Both now track the same `StateFlow` and re-claim when it moves, and
`externalCameraConfig` takes the flag as a PARAMETER rather than reading prefs
itself, so the two cannot drift apart silently.

Prefs-backed for the reason `CompassSettings` is: the service can be restarted by
the system without the UI, and the answer has to survive that. Default ON because
that is what the mode is for — an external camera's frames are not ours to
bracket, so there is no shutter to build a window around. Off is a storage
decision, and the UI says the number, because "continuously" sounds free until
you read "roughly 100 MB of CSV an hour".

Placed directly under the "Recorded: N heading rows · N location rows" line,
because that is the readout of what it controls. An earlier note here said "above
the buttons that start a session, a decision to make before recording" — that was
wrong on both counts: the buttons below it are *Open camera app*, *Float over
camera* and *Export CSVs now*, none of which start anything, and there IS no start
button. `MainScreen` calls `setRunning(activity == "external")`, so the session is
already running when the pane appears and the header already reads "● recording".
Which is exactly why the switch has to act LIVE, and why the `any { }` merge trap
above was the whole problem rather than a detail.

`ContinuousImuToggle` is an expect/actual (the setting is Android prefs read by a
foreground service, invisible to commonMain), no-op on desktop, same convention as
`pipSupported()`.

401 jvmTest, 430 androidHostTest, `:androidApp:assembleDebug`.

## 2026-09-26 — the emulator finds three things the host tests could not

`androidDeviceTest` had **never been run** in this work — 376 tests sitting there,
and `PhotoDatabaseMigrationTest` is the only thing that validates a migration
against real SQLite. Booting the local AVD found three real defects within minutes.

**1. The whole-chain test had gone stale by five versions.**
`theWholeChainRunsAndMatchesTheEntities` validated 14 → **23** while the database
went to 28, so it kept passing without ever checking `attitudeJson`, the
fix/lens/inertial trio, `imuSamplesJson`, `uploadHoldReasons` or the rename. A
hardcoded target in the test whose whole job is catching drift is the one place
drift hides. Both databases now expose `PHOTO_DB_VERSION` / `GEO_DB_VERSION`, used
by the `@Database` annotation AND by the test, so it cannot fall behind again.

**2. A rewritten migration, which would have broken every fresh install.**
Targeting 28 immediately failed: `no such column: "motionJson"`. The blanket
`motionJson` → `inertialJson` rename had swept up `MIGRATION_24_25`'s SQL, so a
fresh chain created the column already named `inertialJson` and then v28's RENAME
found nothing. It still worked on a device that had the ORIGINAL v25 — which is
exactly why the hand-written 27→28 sqlite3 check passed: it started at 27. A
migration is history and must not be edited; restored, with the reason at the line.

**3. My upload-hold change silently voided bare-deadline holds.**
`UploadClaimRaceTest` asserts that a row with a future `uploadHoldUntil` is
invisible to the drain. Making the holder bits authoritative
(`reasons = 0 OR deadline <= now`) broke that for every hold set as a deadline with
no bits — including the stale ones `StartupReconciler` exists to clear. The obvious
patch, `AND`, was worse: a holder that DIED would wedge the row forever, since its
bit never clears.

The rule that satisfies all three cases is simpler than either: **the deadline
alone decides, exactly as before the bits existed, and the bits only decide when
the deadline is zeroed.** The last holder to release clears it; a dead holder
leaves it standing and the deadline frees the row. The selection predicate is back
to the `uploadHoldUntil <= :now` it always was, so nothing outside this mechanism
had to learn anything.

Also added `GeoTrackingDatabaseMigrationTest` — that database went to v4
(`fusedSensorAccuracy`, `imu_samples`, `imu_claims`) with no device test at all. Its
first version failed too, because my INSERT guessed the v1 column names; reading
`schemas/…/1.json` showed the heading is `trueHeading` and there is no `elected`
yet.

401 jvmTest, 431 androidHostTest, **376 connectedAndroidDeviceTest**, 296 API unit,
`:androidApp:assembleDebug`.

## 2026-09-26 — the sampling design, written down before the next control lands

**docs/imu-sampling-design.md.** Written because three user-facing controls are
foreseeable — a window-length setting, a fast-mode toggle in the CAPTURE activity,
and battery work generally — and each lands on couplings that are not visible from
the call site. Two of them already cost a fix today.

The headline for anyone adding a control: **the claim merge is `any { }` for the
booleans and `min` for the rates.** A value in `GeoDefaults` is a FLOOR another
live claim can raise, so a toggle wired to one config does nothing while a second
claimant disagrees. That is exactly how the external toggle's first version was
defeated, and why `externalCameraConfig` takes the flag as a parameter instead of
reading the setting itself. A capture-side toggle has to be the same shape and
cannot honestly promise "off".

Also documented: every constant and what it is pinned to. `ImuRing(16_000)` is
`2 × IMU_WINDOW_HALF_MS + margin` at ~1 kHz, so **lengthening the window without
growing the ring silently returns half a window** — which looks like data rather
than an error. The payload caps in two languages are pinned to the same capacity.

**The unused battery lever, flagged prominently: hardware FIFO batching.**
`registerListener` has a five-argument form taking `maxReportLatencyUs`; we pass
the four-argument one, so at 400 Hz every sample is a wakeup instead of a burst of
forty. It is likely the largest available saving and the design is already
compatible — samples carry their own timestamps and the ring assumes nothing about
callback spacing. What to check first is whether the device even has a FIFO
(`getFifoMaxEventCount`, or `dumpsys sensorservice`), and note the interaction: the
latency budget must stay well under `IMU_SETTLE_MARGIN_MS` or the window's tail is
still in the FIFO when it is read.

**Cleanups while there.** The payload cap said "per SENSOR" in the worker while the
app bounded the TOTAL — a factor-of-two disagreement in the permissive direction,
so 16 000 accelerometer plus 16 000 gyroscope rows would have passed a door the
producer can never reach. Now one number, checked as a total, with a per-array
bound kept to fail fast. Two comments still named `stored_from_ms`, removed earlier
today.

## 2026-09-26 — FIFO batching, and the three things it forced

`maxReportLatencyUs` is now passed (`IMU_BATCH_LATENCY_MS`, 1 s), so a sensor with
a hardware FIFO buffers samples and wakes the application processor in bursts
instead of ~1 000 times a second. Full reasoning in
**docs/imu-sampling-design.md**; what matters here is that it was not a one-line
change.

**The wall clock had to move off delivery time.** Every sample's `timestamp` was
`System.currentTimeMillis()` read in the callback — fine while samples arrive
singly, fatal with a FIFO, where forty arrive together and would all have carried
one millisecond. That flattens the timeline the window bounds, the `dt_us` deltas
and the high-water mark all rest on. `imuWallClockFor` derives each sample's wall
clock from its own `SensorEvent.timestamp`. It is strictly more accurate without
batching too, which is the tell the old way was wrong rather than merely
incompatible.

**Six places assumed insertion order was time order.** Two sensors' bursts
interleave, so the last element added can pre-date most of the batch:
`fresh.last().timestamp` as a high-water mark would have gone BACKWARDS and
re-stored samples already written. All `minOf`/`maxOf` now, with a test that fails
against the old form.

**The read flushes.** `SensorManager.flush` before the deferred persist, awaiting
`onFlushCompleted` (the listener is a `SensorEventListener2` now) with a timeout,
because `flush` returning true does not promise the callback arrives.

**The settle margin did NOT grow, and that is the user's correction.** The first
version derived it from the latency, assuming a sample still in the FIFO is lost.
It is not lost from the stream — captures tile, so it lands on the NEXT photo
("a second missing off a 3-second tail doesnt really matter, if it makes it into
the next photo"). So the latency answers to power, the margin stays 150 ms, and the
upload hold is not coupled to a battery setting.

### Measured on a device

    IMU ring registered at FASTEST, batching 1000ms (…fifo=0/0, …fifo=0/0)
    IMU window: 500 samples …564676..…567169 (2493ms span), stored=189

FASTEST and batching coexist, and the timeline holds rather than collapsing — the
regression the clock change exists to prevent. **`fifo=0/0`: the emulator has no
FIFO**, so this proves the registration and the clock, NOT any power saving and not
a real burst. That needs hardware with a non-zero `fifo=`.

Two findings from reading the log rather than the green result:

- **The morning's fallback works.** Before the fix below the run logged
  `IMU registration at 0µs not permitted` and degraded to 200 Hz instead of
  crashing.
- **The test APK is its own package** (`cz.hillview.shared.test`) and inherits none
  of the app's permissions — so every IMU device test had been silently running at
  the fallback rate, a device suite exercising a configuration the product never
  ships. `shared/src/androidDeviceTest/AndroidManifest.xml` now declares it.

401 jvmTest, 433 androidHostTest, 378 connectedAndroidDeviceTest,
`:androidApp:assembleDebug`.

## 2026-09-26 — batching measured on hardware: a 4500-event FIFO

    IMU ring registered at FASTEST, batching 1000ms
      (ACCELEROMETER fifo=4500/3000, GYROSCOPE fifo=4500/3000)

The question only a device could answer, answered. The Armor 22 has a 4 500-event
FIFO with **3 000 reserved per sensor**, so batching is real here rather than
accepted-and-ignored. At the measured ~400 Hz per sensor a 1 s budget needs 400
events — 13 % of reserved, and the reserved depth could hold 7.5 s. **The IMU
stream's AP wakeups drop from roughly 800 a second to about one.**

So `IMU_BATCH_LATENCY_MS = 1000` is conservative, limited by taste rather than
hardware. Raising it costs only tail re-attribution, which the tiling absorbs.

Also confirmed in the same trace: `lens facts: intrinsics=ABSENT ...
physMm=7.39x5.55 pixels=4624x3472 focusCal=uncalibrated` — matching the
`dumpsys media.camera` dump exactly, from a completely different code path.

**An observability gap the trace exposed.** Leaving the capture pane produced
`imu=false` in the merged config and then *nothing at all* about the sensors
actually stopping, because `stopImuSensors` was silent while its registration
counterpart had always logged. "Off" is a claim about power, and a claim about
power has to be checkable from a log — especially since it is the entire point of
the external toggle. Both stop paths log now (`stopMotionSensors` was asymmetric
too).

Not yet exercised on hardware: the window and the payload, because that trace took
no photo. `IMU window for <id>: …` and an `imu_samples` key in the upload metadata
are still unconfirmed on a device.

## 2026-09-26 — batch budget to 2 s, and where the battery actually is

Raised `IMU_BATCH_LATENCY_MS` 1 s → **2 s** for the long interval sessions, and
stopped there for a measured reason rather than a cautious one.

| budget | IMU wakeups/s | inline pre-shutter cover |
|---|---|---|
| unbatched | ~800 | 3.0 s |
| 1 s | 1.0 | 2.0 s |
| **2 s** | **0.5** | **1.0 s** |
| 3 s | 0.3 | **0 — crash floor gone** |

The saving is all in the first step. And a budget at or above `IMU_WINDOW_HALF_MS`
empties the inline pre-shutter summary — the only motion a photo keeps if the
process dies before the deferred pass rewrites it — in exchange for 0.2 wakeups a
second. 2 s is the last value that keeps the floor while taking essentially all of
the saving. The Armor 22's FIFO would allow ~5.6 s; the window is what limits this,
not the hardware.

**The honest total, which is the part worth knowing** ("otoh, there's a lot more
that the app still does anyway" — quite): four sensors run UNBATCHED at
`sensorDelayUs` — rotation vector, magnetometer, gravity, linear acceleration —
which at capture's 30 ms is ~132 wakeups a second regardless of this constant. So
batching took 932/s to 133/s, and the last 0.5 is noise.

The two levers that would actually move an interval session:

- **The GPS interval setting is a no-op** (`GPS_INTERVAL_SETTING_LIVE = false`), so
  every activity asks for a fix every second. An interval capture every ten seconds
  is requesting ten times the fixes it uses, and the receiver costs far more than a
  sensor callback. The control exists and is hidden only because the value never
  reaches `PreciseLocationService` — scoped work, not research, and the biggest
  cheap win available.
- **Gravity and linear acceleration are sampled at 33 Hz to be read once per
  shutter.** The other half of the 132/s floor, with a real trade: batching them
  grows `inertial.age_ms`, and a stale gravity vector during a pan is meaningfully
  wrong.

And the largest term is probably neither — the camera preview runs for the whole
session.

## 2026-09-26 — battery work parked, not started

**docs/todo/frontend2-battery-work.md.** Batching changed enough logic for one
sitting, so the rest is written down instead of built: the GPS interval no-op (the
cheapest real win), slowing gravity/linear-acceleration, duty-cycling the IMU around
scheduled shutters, and measuring the preview — which is probably the largest term
and the least explored.

Each item carries what to WATCH rather than just what to do, because two of them
have non-obvious traps. Duty-cycling saves `interval - 2×half`, so it is worth
nothing below a 6 s interval. And a sparser GPS stream widens the bracket
`StampRefiner` interpolates from, which is a quality trade rather than a free win.

Also recorded as explicitly not worth doing: decimating the IMU rate (it costs the
feature the window exists for) and raising the batch budget further (0.2 wakeups a
second against the inline crash floor).

The analysis stays in docs/imu-sampling-design.md and is cross-linked rather than
copied — three places already had versions of the field-count table earlier today,
which is how they drift.

## 2026-09-26 — the external pane finally shows the inertial data, and that the dump may be off

Asked why the external-camera pane shows no stats about the fast IMU data or the
dumps. Because nobody added them — and looking turned up something worse than a
missing readout.

**`ImuDao.count()` existed from the start and nothing called it.** The pane's
"Recorded:" line had heading rows and location rows and no inertial samples, so the
one mode built around continuous inertial logging gave no evidence of any happening.
As of today it also has a SWITCH for that logging, and a toggle with no feedback is
a toggle you cannot trust. The line now reads
`… · N inertial samples (R/s)`, the rate derived from the existing once-a-second
poll — which is also the cheapest way to see on-device whether FASTEST took (a few
hundred) or the fallback did (a few tens), with no cable.

**And `auto_export` defaults to FALSE.** The tracking tables are cleared five
minutes back on every dump, and the dump only WRITES a file when auto-export is on.
So with it off, continuous logging fills a table that is then thrown away — the
samples never reach a file, and nothing anywhere said so. This is the mode where it
matters most, because an external camera's frames have no other route to a motion
record at all. The pane now says so in error colour, with what to do about it.

Counts moved from `Pair<Int, Int>` to a named `TrackingCounts`, because a third
number in a pair is where readouts start getting mixed up.

No engine logic touched — a readout and a warning.

## 2026-09-26 — the dump had a race, and continuous logging opened it

A device trace caught `dumpAndClear` failing:
`Couldn't read row 5825, col 0 from CursorWindow`, out of
`ImuDao_Impl.getAllSamples`. The thread ids tell the whole story:

    25325  23:49:41.634  Dumped 1653 bearings   -> ..._1790459381317.csv
    25325  23:49:41.807  Dumped 321 locations   -> ..._1790459381317.csv
    25328  23:49:43.411  Dumped 257769 IMU      -> ..._1790459378082.csv
    25328  23:49:43.538  Geo tracking tables CLEARED
    25325  23:49:44.084  FAILED reading imu_samples at row 5825

**Two concurrent dumps**, 3.2 s apart by their own filename stamps. One cleared the
tables while the other was mid-iteration, and the row it wanted was gone.

`dumpAndClear` had **no serialization at all**, and five callers each launch their
own coroutine: app start, the export button, capture teardown, and the external
service's crash-safety timer. Latent for as long as this dumped only bearings and
locations — a couple of thousand rows finish in milliseconds and never overlap.
Continuous inertial logging made a dump 257 769 rows and seconds long, and the
window opened.

**Fixed:** a `Mutex`. A user pressing "Export CSVs now" WAITS, because their action
must not be silently dropped; an opportunistic dump SKIPS, because queueing it
behind the running one would only re-export rows that one just cleared.

**And a second bug found while reading it: the clear ran even when the dump had
failed.** It sat in its own `try` outside the dump's, so an export that threw still
took the data with it. In this trace nothing was lost because the other thread had
already written those rows, but a single failing dump would have deleted five
minutes of samples that reached no file. The clear is now skipped on failure.

**Parked, not fixed** (item 5 in docs/todo/frontend2-battery-work.md): the dump
loads the whole table — ~13 MB of entities and a ~28 MB String at the observed
row count, which is the steady state. It has not OOMed, but those seconds are what
made the race reachable.

## 2026-09-26 — dump stats, because "seconds-long" needs a number

A seconds-long dump is a risk, not just a slowness: **the clear is part of the
dump**, so a dump slower than the interval that triggers it gets skipped by the new
mutex — and the clear is skipped with it, so the tables grow without bound. That
failure is completely silent without a duration to look at.

So `dumpAndClear` is timed now. Every dump logs
`Dump took Nms for R rows (X rows/s), 300s until the next one`, and publishes
`GeoTrackingManager.lastDump` (a `DumpStats`), which the external pane shows as
`Last export: R rows in Nms (X rows/s)` — or, when it failed,
`Last export FAILED after Nms — rows were kept, not cleared`.

The headroom condition, stated plainly: the external service dumps every **5
minutes**, so the dump has 300 s of room. Nothing observed comes close, but it is
now measurable instead of assumed.

**And working that out turned up a real waste.** `getAllSamples()` has no lower
bound while the clear keeps the last five minutes — and the dump interval is *also*
five minutes. So each dump re-exports the previous dump's retained tail: **every
sample lands in two files, and every dump is twice the size it needs to be.** True
of bearings and locations too, and always has been; at 1 653 rows nobody noticed. At
240 000 it is the cheapest available halving of the dump's cost.

Parked with the fix shape in docs/todo/frontend2-battery-work.md rather than done —
the retention window cannot simply shrink, because those five minutes are what let a
capture's deferred window still be read.

## 2026-09-28 — the exposure instant, and every sensor snapshot moved onto it

**What a photo now records about WHEN it was taken.** `capture_timing`, inside the
UserComment, on every capture:

| field | meaning |
|---|---|
| `captured_at_source` | what `captured_at` is — `"press"` today, always emitted |
| `press_to_exposure_ms` | measured, not assumed |
| `exposure_to_jpeg_ms` | to the file landing, same definition on both save paths |
| `exposure_elapsed_ns` | the exposure on `elapsedRealtimeNanos` — **the same clock as `imu_samples.t0_ns`** |
| `exposure_wall_ms` | the same instant in wall time |
| `exposure_source` | `"sensor_timestamp"`, or ABSENT when it was not measured |
| `pose_referenced_to` | `"exposure"` or `"press"` — which instant the attitude/inertial VALUES came from. Not the age reference: that is `exposure_wall_ms` whenever it is present |
| `still_mode` | the capture mode |
| `build` | the APK's `BuildInfo.label()` — **in the wrong object, see below** |
| `refined_to` | written LATER by `StampRefiner`: the instant it interpolated the position and bearing to |
| `refined_position` / `refined_bearing` | present only when that stream was actually replaced |

**Proven on hardware, not asserted.** The exposure lands on ONE IMU sample: residuals
+336 µs and −207 µs against a 2 512 µs sample period, through the frame's
`SENSOR_TIMESTAMP`, a clock bridge, the upload and the artifact's `t0_ns + cumsum(dt_us)`.
Attitude and inertial readings are looked up AT that instant — `|age|` 0.6 ms and 0.5 ms
median, from 50 ms and 315 ms before.

**It needs no server deploy.** `capture_timing` was pre-declared in `BrowserMetadata`
and `PROVENANCE_KEYS` before anything sent it, precisely so the app could iterate alone.
Prod already has alembic 036 + API + worker.

### Reading the build stamp — it cost an hour, twice

The stamp's third field is `GIT_COMMIT_TIME`, **not a build time** (the clock is avoided
deliberately: a config-time timestamp would freeze into the configuration cache and lie).
So `sha · time` says only "built from a tree whose HEAD was that commit", and **two builds
made between the same pair of commits share the sha**, differing only in the dirty hash.

The dirty hash is the discriminator and is reproducible:

```bash
(git status --porcelain; git diff HEAD) | sha1sum | cut -c1-8
```

Reconstruct a candidate tree in a worktree, hash it, compare. That settled which of two
builds a phone had run when age distributions could not.

### DONE — position at the exposure

`StampRefiner` now interpolates to the exposure. `SharedStackUploadPipeline` passes
`upload.captureTiming?.exposureWallMs` when the capture measured one and names which
instant it passed; the refiner records the answer into the photo's `capture_timing` as
`refined_to`, plus `refined_position` / `refined_bearing` when that stream actually
moved. Nested keys, so no worker deploy.

Position needed no ring, unlike attitude and inertial. A ~1 Hz receiver has no sample
AT the exposure to look up — the honest at-exposure position is an interpolation across
the bracketing fixes, which is what the refiner already computed. Only its target was
wrong, and that was the most misleading of the four timing errors precisely because the
machinery was good: interpolation makes a value more PRECISE, and a refinement step
advertises that the stamp has been corrected to match the photo.

`location_age_ms` is measured from the exposure now. Exact addition, not a
re-measurement — the press-time age and the press→exposure gap are both distances from
the same fix instant.

**And ungating the age reference fixed a bug nobody had reported.** `poseReferenceMs()`
returned the exposure only when `pose_referenced_to == "exposure"`, i.e. only when BOTH
rings answered. With the rings empty, the press-time attitude reported ~25 ms when it was
~340 ms stale with respect to its frame. In the MIXED case — one stream found, the other
not — the found sample was at-exposure while the reference fell back to the press, so its
`age_ms` came out negative by the whole gap. Ages are now measured against
`exposure_wall_ms` whenever it is present, and `pose_referenced_to` means only which
stream answered. No new field: the presence of `exposure_wall_ms` IS the reference.

### DONE — the skew fields made honest

Option (a), and deliberately only that. `lens.rolling_shutter_skew_ns` →
`preview_rolling_shutter_skew_ns`, with `frame_values_source: "preview"` and an `age_ms`
for the rest of the per-shot half.

Exactly one key renamed, because the defects differ: the other per-shot values are
STALE, and the age now says how stale. Skew is a DIFFERENT number — readout time scales
with the lines read, and preview and still run different sensor modes — so it is not a
fresher version of the still's. The unqualified name is reserved for the still's own
value if a route to it appears.

The `age_ms` needed the preview values timestamped, so the preview capture callback
bridges each result's own `SENSOR_TIMESTAMP` to wall ms — the same conversion as the
still path, one hop shorter because the destination is wall rather than
`elapsedRealtime`. NOT the callback's arrival time: the still's equivalent dispatch was
104 ms late with ±16 of jitter, so a dispatch-derived age would swap an old guess for a
fresh one. No HAL timestamp → no age emitted.

Server side: two lines in the API's `_LENS_FIELDS` allowlist (`age_ms` and the two new
string/int keys), the old key kept declared for rows written before today. That is an
API deploy, not a worker one, and only affects PUBLIC visibility — the owner endpoint
ships `exif_data` wholesale and sees everything immediately.

### STILL NOT DONE, after this

- **The still's lens values.** Focus distance, intrinsics and distortion remain the
  preview's, now merely labelled and dated. The cheap next step is a ring of
  `FrameLensFacts` keyed by each preview result's `SENSOR_TIMESTAMP`, looked up at the
  exposure like the other two rings — it cannot produce the still's values, but it
  replaces "the preview frame before the press" with "the preview frame nearest the
  exposure", cutting the age from hundreds of ms to tens.
- **The IMU window is still press-centred.** `persistImuWindowAround(capturedAtMs)`
  aims at the button; prod measured the ±3 s window as −4.76 s / +1.24 s around the
  frame in Quality mode (79.3 % of the history before the exposure). The read is
  deferred to `press + 3 s + 150 ms` and the exposure is known at the save, so the
  centre can still be retargeted in flight.
- **`captured_at` itself is still the press**, and says so. Moving it has a filename, a
  DB column and the pics join behind it.

## 2026-09-26 — STATE OF PLAY at end of day

24 commits. Read this entry first if you are picking the work back up; the entries
above are the narrative, this is the position.

### Where the three docs live

- **docs/recon-capture-metadata.md** — the contract. What every provenance field
  means, the four-list rule (app serializer / `BrowserMetadata` / `PROVENANCE_KEYS`
  / typed projection), Phases 0–5, and the decisions with their rejected
  alternatives.
- **docs/imu-sampling-design.md** — the mechanism. When the sensors run, what each
  constant is pinned to, and what breaks if the window length or a toggle changes.
- **docs/todo/frontend2-battery-work.md** — five parked items, scoped and measured,
  deliberately unstarted.

### Built and verified LOCALLY; nothing deployed

Phases 0–5 are complete. The samples reach the server as a gzipped columnar
artifact at `photos.imu_samples_url`, verified end to end by
`backend/tests/integration/test_imu_samples_artifact.py` (6 tests) against the local
stack — including that the payload never enters the UserComment.

**Deployment order matters: alembic `036` → API → worker.** `photo.imu_samples_url`
against a table without the column is a hard failure; the reverse order is safe only
because an old API ignores unknown fields.

**The prod worker is unchanged**, so `inertial` and `imu_samples` are both dropped
silently at pydantic's door. That is why the phone shows no server-side effect and
why no error appears anywhere — the documented behaviour, not a fault.

### Confirmed on the real phone

- The startup crash is fixed (`HIGH_SAMPLING_RATE_SENSORS`), and the fallback is
  demonstrated working.
- **FIFO batching is real here: `fifo=4500/3000`.** ~800 IMU wakeups a second → ~0.5.
- `lens.intrinsics_available` is **false**, cross-checked against
  `dumpsys media.camera`; the derived pinhole (fx 3491.5, fy 3490.8) is
  self-consistent to 0.02 %.
- Claims, tiling and the dumps all work; a dump of 257 769 rows completed.

### CONFIRMED on hardware 2026-09-27 — the last open test passed

**A capture producing a payload.** Four captures on the Armor 22, audited read-only
against the local stack end to end (`/shared/imu/`, records + public responses +
fetched artifacts):

| capture | summary count | artifact = `stored_count` | span | gzip |
|---|---:|---:|---:|---:|
| 08:49:00.906 | 4 774 | 4 774 | 5.995 s | 30 713 B |
| 08:49:02.796 | 4 776 | **1 504** | 1.887 s | 10 336 B |
| 08:49:04.479 | 4 776 | **1 340** | 1.681 s | 10 070 B |
| 09:00:20.633 | 4 776 | 4 776 | 5.998 s | 28 023 B |

**The tiling is the result worth having.** Three captures ~1.9 s apart share one
overlapping ±3 s window, and the burst ships **7 618 samples instead of 14 326** —
each artifact carries only its own tail, with disjoint monotonic ranges, and
`stored_count` matches the artifact exactly every time. That is `imu_claims` doing
the job it replaced derived attribution for. The fourth capture, 676 s later, gets a
full window of its own.

Also confirmed on the way: `inertial` present and `motion` absent; `attitude`, `fix`,
`lens` and `inertial` in the public response equal the stored UserComment; no
`imu_samples` anywhere in a UserComment; every `imu_samples_url` fetched 200 with
valid gzip, unauthenticated; ~398 Hz per sensor with no internal gaps.

**And it found a real bug** — the payload's `dt_us` drifted ~1.2 ms over a 6 s
window because each gap was truncated independently, under a comment claiming that
could not happen. Fixed, with a regression test at the device's real 2 512.5 us
cadence (every prior test used whole microseconds, which is why none caught it). See
docs/imu-sampling-design.md.

**One limitation it documented rather than a failure:** every stamp describes the
button press, not the exposure, which starts 546–2 014 ms later (1 881 ms measured
live in `quality` mode). Pulling that thread found three more — preview-fed lens
values, ages measured to the wrong instant, and a stamp refiner polishing toward
the press — and the answer is one timestamp rather than two. Planned in
**docs/todo/captured-at-is-the-exposure.md**; not built, and it opens with an
experiment.

The pane will also now show inertial counts, a live rate, the last export's cost, and
a red warning if auto-export is off.

### Tooling

`ast-grep` is installed and cooloff-clean. **kotlin-lsp is blocked until
2026-09-27** — JetBrains' standalone builds expire, and the only unexpired one was
12 days old against the 14-day cooloff. Recipe and both traps are in
STRUCTURAL_TOOLS.md.

`androidDeviceTest` had never been run in this work and found three real defects in
minutes; it is worth running for anything touching migrations or the upload hold.
