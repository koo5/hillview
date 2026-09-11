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
  onDetach() on dispose (rememberMapView). Not yet rotation-tested on a
  device.
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

## 2026-09-11

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
  - **One gutter constant, 8 dp, at screen edges and nothing at the divider.**
    The tracking pair loses its 16 dp top in portrait (the divider is above
    it) and keeps its end gutter in both, which is the one the user called
    critical: a mis-tap there turns tracking off. Zoom likewise.
  - **The hunter corner takes no gutter at all**, by request — the toggle and
    the two toolbars that unfold from it sit where the system insets put them
    and no further.
  - The right-edge source tabs' top and bottom are CLEARANCES, not gutters —
    they keep out of the tracking row and the hunter row — so they are now
    derived from the same constants rather than being two hardcoded numbers
    that had to be kept in step by hand.
  - `movableContentOf` needed care: the map panel is ONE instance that travels
    between the portrait Column and the landscape Row, so the orientation is
    read through a `rememberUpdatedState` rather than captured, which would
    have frozen it at whichever orientation the app started in.
  - NOT phone-verified — no device reachable from this machine.

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
    grab zones", now annotated).
  - Panning and marker taps over the ring are UNAFFECTED, which they would
    not have been under the first cut of this: it consumed the press to time
    the hold, and a ring-wide dead band across the map is too high a price
    for a gesture nobody makes most of the time.
  - NOT phone-verified — no device reachable from this machine.

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
  - NOT yet phone-verified — no device reachable from this machine. What to
    check: `Documents/Hillview2/photos.csv` after backgrounding the app, and
    that it is still there after an uninstall.

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
  - NOT yet phone-verified — no device reachable from this machine.

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
  - NOT yet phone-verified — no device reachable from this machine. The pure
    parts (rung list, labels, band mapping, band colours) are covered by
    `IntervalLadderTest`.

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
