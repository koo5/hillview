# frontend2 rewrite plan — KMP/CMP app

Status: agreed framing as of 2026-08-04. The clock-video recorder (first
vertical slice) is built and emulator-verified; this doc plans the rest.

Progress 2026-08-04 (same day): **P0 complete** (Nav3 1.1.1 + Koin 4.2.2 +
AMOLED theme; auth domain with transient-vs-definitive refresh classification;
login screen; session persists across process death; all four test layers
green — 8 commonTest state-machine tests, 2 desktop Compose UI tests, 3 JVM
contract tests against the live backend, emulator login smoke). **P1 capture
slice built and emulator-verified** (CameraX ImageCapture + LocationManager +
rotation-vector bearing → EXIF via PhotoExifWriter; EXIF golden checked
against an injected emulator GPS fix). P1 residue: codify the EXIF golden as
an instrumentation test; declination correction lands with P4.

## Vision and sequencing

Full rewrite of the Tauri mobile app in Kotlin Multiplatform + Compose
Multiplatform, **built as the whole app from day one, filled in
capture-first**. The initial deliverable is a poweruser photo capture tool —
battery-efficient, capture screen at the center, auth, the offline-first
upload pipeline, and an orientation map — but every structural decision
(modules, navigation, data layer, DI, test harness) is made for the complete
app, so later phases furnish rooms instead of remodeling.

The Svelte web app **stays** as the website + admin console (SEO, moderation,
admin dashboards are browser workflows; CMP-Wasm would hurt all three). Its
Playwright suite stays with it in maintenance mode. The Tauri Android app
remains installed/parallel during the transition; both apps share the backend
and accounts, so there is no cutover moment.

## Phases

- **P0 — walking skeleton**: app shell with real navigation, DI, theme,
  full-vision module layout; login against local backend; all four test
  layers standing with at least one real test each.
- **P1 — capture slice**: CameraX capture + sensor snapshot (GPS, bearing,
  orientation from the ported EnhancedSensorService) → EXIF → local
  persistence. EXIF golden tests (see Testing).
- **P2 — upload pipeline**: offline-first queue in commonMain; coalescing,
  retry, storage prefs, notifications; deterministic ports of the chaos
  tests BEFORE the queue is called done.
- **P3 — orientation map**: narrow `OrientationMap` seam (center/zoom/
  bearing, photo markers w/ optional bearing ticks, tap callback); cheap
  interim backing (osmdroid in AndroidView). Nearby-photos markers so
  coverage gaps are visible while shooting.
- **P4 — tracking & battery**: foreground-service geo tracking, car mode /
  Kalman port, GPS duty cycling, battery measurement harness (see Testing).
- **P5 — field-tool completion**: settings subset, share intents, FCM,
  relogin notification.
- **P6+ — browse & the rest** (planned when reached, held open by the
  architecture): serious map library evaluation (MapLibre Compose the
  leading candidate) and full map browse, photo detail + info, timeline,
  annotations + sync, filters, activity/contributions, device photos.
  iOS becomes a realistic target at any point after P2 (keep commonMain
  clean of Android types).

## Architecture decisions (made now, for the whole app)

- **Modules**: single `shared` module for now, but package-by-domain from the
  start: `auth`, `capture`, `upload`, `map`, `photos`, `tracking`,
  `clockvideo`, `settings`, `notifications`, `core` (design system, net,
  db, util). Split into Gradle modules only when build times demand it.
- **Navigation**: Navigation 3 (back-stack based, multiplatform since CMP
  1.10) from P0 — replaces the hand-rolled screen enum. Route model designed
  alongside deep links: `cz.hillview://photo/<uid>`, auth callback, share
  targets. Debug builds use the `cz.hillview.debug` scheme (the prod app on
  the same device owns `cz.hillview://`); backend OAuth redirect allowlist
  needs both.
- **DI**: Koin (KMP-standard, used by JetBrains' own template). Every screen
  is a ViewModel (androidx lifecycle KMP) taking constructor-injected
  service interfaces — this is what makes the desktop test layer possible,
  and it is a hard rule, not a preference.
- **Data**: Room (KMP, commonMain — per current JetBrains guidance) for
  photo/upload-queue/tracking persistence; DataStore for prefs; entities
  modeled for the full domain (Photo, User, Annotation, UploadTask, Track)
  even where P1–P5 only partially use them.
- **Network**: Ktor 3 + kotlinx-serialization, one service interface per
  backend domain; check generated-from-OpenAPI clients (FastAPI serves
  `openapi.json`) vs hand-written — either way, schema-drift tests against
  the running backend.
- **Images**: Coil 3.
- **Map**: `OrientationMap` interface in commonMain designed as the seed of
  the eventual full map component (general marker model: photo markers with
  bearing, selection state). Backing implementations are swappable; the real
  library evaluation is a P6 gate, not a P3 blocker.
- **Battery is a requirement with numbers**: adaptive GPS duty cycling,
  sensor batching, WorkManager charge/network-aware upload scheduling,
  camera bound only while the capture screen is resumed, static map
  rendering, AMOLED-dark default theme.

## Testing strategy

The pyramid inverts relative to the web app: the fast layer moves from
Playwright to JVM.

1. **commonTest (JVM, ms)** — state machines: auth/token refresh, upload
   queue, sync, tracking. Ktor MockEngine + scripted fault injection. The
   Appium chaos specs (`chaos-photos-recovery`,
   `chaos-worker-upload-recovery`) become deterministic tests here — this is
   a quality upgrade, not a port.
2. **Desktop Compose UI tests (JVM, seconds)** — `runComposeUiTest` over real
   screens with fake services; selectors are `testTag`s (same discipline as
   the web app's `data-testid`). This layer replaces most Playwright UI
   scenarios. Golden screenshots via ImageComposeScene where the
   `playwright.screenshots` suite has equivalents.
3. **JVM integration vs real backend (seconds)** — Ktor client against
   `docker compose` backend on `localhost:8055`, `test/...` credentials;
   auth, photo CRUD, upload contract. No emulator, no browser.
4. **Android instrumentation (thin)** — camera capture, EXIF writing,
   permissions, deep links, SAF storage, FCM plumbing.
5. **E2E on emulator (thinnest)** — adapt the existing wdio/Appium harness:
   `testTagsAsResourceId` is already wired and proven; selector swap
   (data-testid → resource-id), backend-connectivity + fail-fast config
   survives. Consider Maestro if Appium flakiness persists on Compose.

**EXIF goldens (P1 gate)**: capture on emulator with known fake sensor
values → pull JPEG → assert exact tags against what the backend parser and
the pics pipeline expect. EXIF is the contract between this app and
everything downstream.

**Battery harness (P4 gate)**: scripted long-run session on device/emulator,
`dumpsys batterystats` deltas per subsystem, tracked over time so power
regressions read like test failures.

**Scenario inventory**: the porting spec is the union of the Appium suite
(27 specs — all in scope) and the mobile-relevant subset of the Playwright
suite (~10 of ~60; the rest cover the web app and stay Playwright). Track as
a table (spec → target layer → phase → status) and update as features land.
Initial classification:

| Source spec | Target layer | Phase |
|---|---|---|
| appium: auth, deep-link-auth, native-expiry-weblogout, native-refresh-5xx, native-transient-refresh, session-expiry-reconcile, relogin-notification | commonTest (state machine) + JVM-vs-backend + thin E2E | P0–P2 |
| appium: photo-workflow, camera-capture | instrumentation + E2E | P1 |
| appium: upload-queue-offline, upload-coalescing, upload-notification, chaos-photos-recovery, chaos-worker-upload-recovery, storage-method-pref | commonTest (fault injection) + instrumentation | P2 |
| appium: background-location-tracking, car-mode-gps-kalman, geo-tracking-export | commonTest (Kalman/duty-cycle logic) + instrumentation | P4 |
| appium: fcm-broadcast, test-notification-plugin, share-intent-outgoing, intent-incoming | instrumentation | P5 |
| appium: map-interaction | desktop Compose UI test | P3/P6 |
| appium: android-simple-health-check, app-resilience, screenshots, settings-persistence | E2E + desktop goldens | P0+ |
| playwright: camera-capture, browser-capture-upload, photo-upload, auto-upload-on-login | commonTest + desktop UI | P1–P2 |
| playwright: sign-in-modal, auth-integration, auth-scenarios | desktop UI + JVM-vs-backend | P0 |
| playwright: photo-markers, map-panning, map-turning, bearing-url-param | desktop UI (map) | P3/P6 |
| playwright: sync-status, resilience-* | commonTest | P2 |
| playwright: everything else (admin-*, sitemap, about, bestof, timeline, moderation, users, …) | **stays Playwright** against the Svelte web app | — |

Progress 2026-08-04 (later): **P2 core built and protocol-verified.**
`UploadQueue` (commonMain, offline-first, sequential drain, retryable/
permanent/worker-busy/session-loss classification, md5 dedup) + 8 passing
fault-injection tests porting the chaos/coalescing/session-expiry Appium
semantics; ECDSA P-256 signer + file queue store in the new `jvmShared`
source set; live end-to-end JVM test uploads a real JPEG through
register-client-key → authorize → signed worker `/upload_async` (green,
returns photo_id). Contract findings encoded: license vocabulary is
`ccbysa4+osm`/`full1`; dev `WORKER_URL` is the Caddy https origin —
`mapWorkerUrl` platform hook rewrites it (localhost:8056 / 10.0.2.2:8056)
until backend URLs become a setting. NOT yet done: Koin wiring of the queue
into the capture flow + drain triggers (next session's first item), status
sync, WorkerManager orchestration/coalescing windows, Room swap for the
JSON store.

Progress 2026-08-05: **shared-kt live** (`/shared-kt/`, rules in its README):
ClientCryptoManager + MadgwickAHRS + HeadingFilter moved verbatim, compiled
by BOTH builds (tauri plugin srcDirs + frontend2 androidMain srcDir).
frontend2 signs uploads with the shared Keystore-backed ClientCryptoManager.
**Capture→upload verified on device end-to-end**: emulator capture →
"uploads: 1 done" → backend processing_status=completed
(photo 5c2fa771-acd1-4f91-bd8f-fcdf9a86b96a). Also: Tauri Play-compliance
pass executed & verified (see tauri-play-store-upgrade memory). Next
candidates: PhotoUploadLogic-family convergence (needs Appium safety net
first — touches working prod upload logic), in-app status sync, WorkManager
coalescing windows, sensor-cluster adoption in frontend2 capture bearing.

Progress 2026-08-05 (later): **upload-family convergence COMPLETE at the
compile level** — the full PhotoUploadLogic family (logic + Manager/Workers/
ForegroundService + PhotoDatabase/entities/DAOs + AuthenticationManager +
NotificationHelper + PhotoUtils) lives in `shared-kt/src` and compiles in
BOTH apps; the Tauri bridge is carved out to the plugin's
PhotoUploadCommands.kt (same-package extension functions, call sites
unchanged). frontend2 gained Room 2.8.4/KSP 2.3.11, WorkManager 2.10.5,
okhttp, core-ktx 1.17.0, lifecycle-process. All moves pure `git mv`
(auditable-refactor method, see shared-kt/README). frontend2 does not RUN
the shared stack yet — its Ktor UploadQueue remains the live path; next:
wire WorkManager/Koin/notification channel, switch capture to
PhotoUploadManager.schedule, retire the queue, retarget its 8 chaos tests.

## P2 starting point

Upload contract (from the live OpenAPI): `POST /api/photos/authorize-upload`
(JSON `UploadAuthorizationRequest`) → then `POST /api/photos/upload-file`
(multipart) and `POST /api/photos/status` for polling. Mine the exact schemas
from `http://localhost:8055/openapi.json` and the old app's
`PhotoUploadManager.kt` + upload-queue Svelte stores before designing the
queue; port `chaos-photos-recovery` / `chaos-worker-upload-recovery` and
`upload-coalescing` semantics as commonTest fault-injection first.

## Assets carried over

- `tauri-plugin-hillview` Kotlin ports nearly wholesale:
  `EnhancedSensorService`, `GeoTrackingManager`, `PhotoUploadManager`
  (and `ClockVideoWriter`'s contract already reimplemented natively).
- Backend unchanged; test credentials and docker workflow unchanged.
- Established this session: testTag→resource-id bridge, GeoTrackingDumps
  conventions, sidecar contract, emulator driving playbook, JBR/AGP9/CMP
  toolchain (see frontend2/README.md).

## Risks / honest caveats

- ~48k lines of Svelte/TS hide accumulated behavior only partially pinned by
  tests; the scenario inventory doubles as the discovery tool for what's
  untested. Expect archaeology, especially in `data.svelte.ts` and the
  upload/power-saving logic.
- Map library evaluation (P6) is deliberately deferred, not dismissed — the
  `OrientationMap` seam is the insurance.
- Multi-month effort at steady part-time pace; each phase ships something
  usable in the field, which is the point of capture-first sequencing.
