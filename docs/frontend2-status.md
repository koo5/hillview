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

**The remap table was investigated and left alone.** UPRIGHT mode keys a
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

## 2026-08-29

- **Anonymization options** on Device photos (the original's modal: auto /
  none, custom noted): an edit → the drain applies it → targeted re-upload.
  Device-verified end to end.
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
  half is closed: two streams, castled on confirmation, the other riding
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
