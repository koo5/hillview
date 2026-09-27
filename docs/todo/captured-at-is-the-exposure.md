# `captured_at` should be the exposure, not the button press

Parked plan, written 2026-09-27. Nothing here is built yet.

The requirement, in the words that set it: **none of the data can be allowed to
lie.** Not "be maximally precise" — a coarse number that says what it is costs
nothing. What costs is a number that reads like a measurement of the photo and
is a measurement of something else.

Three fields currently do that, and a fourth mechanism actively polishes one of
them toward the wrong answer. This plan replaces the press with the exposure as
the one timestamp the app records, which subsumes all four.

No backwards compatibility is required (stated 2026-09-27). Existing rows keep
press-based timestamps; the plan does not migrate them.

## What lies today, with the measurement beside it

Two independent sources: the four-photo audit (`/shared/imu/`, 2026-09-27) and
the phone's own 📷 stats dialog the same morning.

**press→exposure is 546–1 881 ms** — 546/558/581/2 014 ms across the audit's four
captures (from the retained camera EXIF), and 1 881 ms measured directly by
`CaptureStatsLog` on a single later capture. The spread is not noise: the stats
line reads `still: quality`, i.e. `MAXIMIZE_QUALITY`, the 3A-lock mode whose lag
was chased down separately. The DEFAULT is `StillCaptureMode.Latency`. So the gap
is a user-switchable menu setting, ranging over roughly 550 ms to 1 900 ms.

1. **Every age and every freshness gate is measured to the press.**
   `attitude.age_ms` (37–152 ms in the audit), `inertial.age_ms` (5–7 ms) and
   `location_age_ms` are all computed against `capturedAtMs`, which is
   `System.currentTimeMillis()` read BEFORE `takePicture`
   (`PhotoCapture.android.kt:1600`). True staleness relative to the frame is that
   age PLUS the lag.

   `ATTITUDE_MAX_AGE_MS = 2_000` (`MapState.kt:262`). At 1 881 ms the lag alone
   consumes 94 % of that budget, so `stampAttitude.freshAt(capturedAtMs)` will
   pass a pose that is ~2 s stale with respect to its own frame while reporting a
   two-digit age. The rule is sound. It is measuring to the wrong instant.

2. **The `lens` object is fed by PREVIEW frames.** `ImageCapture.Builder()`
   (line 609) has no `Camera2Interop` session capture callback; the only two in
   the file are on the preview builder (832) and the video builder (1368). So
   `lensStampNow()`'s `frame?.*` values come from the latest preview result:
   - `focus_distance_diopters` is the PRE-autofocus value. `focus=auto` in the
     stats, and 1 881 ms of 3A between press and exposure, so the focus
     demonstrably moves in between.
   - `rolling_shutter_skew_ns` = 31.1 ms is the PREVIEW's readout time. Preview
     and still run different sensor modes and resolutions; readout scales with
     the lines read, so there is no reason the two match.

3. **`captured_at` is the press** while the camera's own
   `SubSecDateTimeOriginal` is the exposure, and nothing says which is which.

4. **`StampRefiner` refines to the press.** The stats show `refine applied: 1`,
   `Δbearing 1.0°`, `Δpos 18 cm` — the refiner interpolated the stamp to an
   instant 1 881 ms before the frame existed. This is the worst of the four: it
   makes the number more PRECISE without making it more TRUE, and the existence
   of a refinement step advertises that the stamp has been corrected to match the
   photo.

### Not lying, so the floor is known

Window bounds and `stored_count` (they state what they are and claim no
centring), the tiling and `imu_claims`, `dt_us` (as of the fix earlier today),
`intrinsics_available: false`, the static lens geometry (matched to the HAL dump
exactly), and the elected-versus-measured pitch split.

## The timestamp to use, and the clock problem

**`CaptureResult.SENSOR_TIMESTAMP` of the still's own frame** is the right
source: per the Android contract it is the start of exposure of the first row,
which is the physically meaningful instant, and it pairs with
`rolling_shutter_skew_ns` to bound the readout. `onCaptureStarted` is a callback
DISPATCH — millisecond resolution plus queueing latency.

**But it is not on our clock.** All three cameras report
`android.sensor.info.timestampSource: UNKNOWN`
(`/shared/a22_dumpsys_camera.txt:1190, 2535, 3945`). Android specifies that
UNKNOWN timestamps share the timebase of `SystemClock.uptimeMillis()` — the clock
that STOPS during deep sleep — whereas `imu_samples.t0_ns`, the bearings table
and the locations table all use `elapsedRealtimeNanos()`.

So a bridge is required:

```kotlin
val offsetNs = SystemClock.elapsedRealtimeNanos() - System.nanoTime()
val exposureElapsedNs = sensorTimestampNs + offsetNs
```

The two clocks diverge only while the device sleeps, so an offset read during a
capture session is constant for that session — and reading both within
microseconds of each other makes the conversion exact for our purposes.
`System.nanoTime()` is `CLOCK_MONOTONIC` on Android, the same base; `uptimeNanos()`
is the explicit spelling where the API level allows it.

**This pattern is already in the codebase.** `VideoFrameLog` harvests
`SENSOR_TIMESTAMP` through exactly this route, records `timestamp_source` in its
sidecar header, and takes "wall/monotonic anchors as close to the first frame as
possible". Its header even notes that *with* REALTIME the frames share the
tracking tables' clock — the project already learned that REALTIME is the lucky
case and that this phone is not it. Reuse the approach; do not reinvent it.

A curiosity for later, not a plan: the dumpsys shows a MediaTek vendor tag
`0x80150015 (realtimeTimestamp)`. If it means what it says it would remove the
bridge on this SoC. Vendor-specific, so it cannot be the primary path.

## The design

**One timestamp.** `captured_at` becomes the exposure. No second field for the
press — two values that both mean "when the photo was taken" is the confusion
this plan exists to avoid. The press→exposure lag stays where it already is, in
`CaptureStatsLog`, as a diagnostic.

**Plus `captured_at_source`**, naming which rung produced it. This is the
project's own pattern — `location_source`, `bearing_source`, elected versus
measured — and it is what makes a fallback ladder honest rather than a lie with
extra steps:

| rung | source | resolution | note |
|---|---|---|---|
| 1 | still `SENSOR_TIMESTAMP` + bridge | ns | the real exposure start |
| 2 | `onCaptureStarted` | ms | dispatch-delayed |
| 3 | the JPEG's own `DateTimeOriginal` | **1 s** | the camera's answer, but second-granular (two existing code comments say so), so it cannot resolve the very lag we are chasing. Weak rung. |
| 4 | the press | ms | last resort, labelled as such |

With the source named we never have to PROVE a rung is reliable — the data says
which one answered. That is why "delete the fallback" is the wrong question:
deleting it would make a missing callback produce no timestamp at all, which is
worse than a labelled coarse one.

**Then the other three fix themselves.** Ages and freshness gates measured
against the new `captured_at` become true. The same still-result callback that
provides the timestamp also provides the frame's own focus distance and skew.
`StampRefiner` interpolating to `captured_at` starts targeting the exposure. And
the IMU window, centred on `captured_at`, is centred on the exposure by
construction — the centring question disappears rather than being decided.

### Why the frame's timestamp and not "press plus measured lag"

Because the sign is not guaranteed. `StillCaptureMode.ZeroShutterLag` is a real
user-selectable mode; ZSL returns a frame exposed BEFORE the button press. On
this device it is inert — `zsl=no` in the stats is `zslSupported == false`, not
"switched off", and CameraX degrades the choice to Latency silently. On a phone
that supports it, every press-based assumption inverts: `captured_at` would be
late, and `persistImuWindowAround(press)` would centre the window AFTER the frame
it describes. A lag correction assumes a sign. A frame timestamp does not.

## What it touches

`capturedAtMs` has 49 references across 26 files, but most are pass-throughs. The
ones that carry meaning: the filename, the EXIF write, the DB row, `StampRefiner`,
the tracking-table joins, and `persistImuWindowAround`. All of them improve.

**The real work is an ordering problem.** `capturedAtMs` is read before
`takePicture` and three things need it there:

1. the filename (`hillview_photo_$capturedAtMs.jpg`) — just a name; can keep the
   press, or be assigned at save;
2. `snapshotSensors(capturedAtMs, …)` — the pose/lens/fix snapshot;
3. `engine.persistImuWindowAround(capturedAtMs)` — the deferred window.

(2) and (3) can move or be revised, because the read is already deferred past the
exposure: `persistImuWindowAround` posts for `centre + 3 s + 150 ms` and only then
reads `[centre−3s, centre+3s]`, while the exposure is known 0.5–2 s after the
press. The ring holds enough — `ImuRing(capacity = 16_000)` ≈ 20 s at ~796
samples/s — and the upload hold is 60 s from the press, so a ≤2 s shift is free.

### Server side: one line

Checked 2026-09-27. Of the four lists a new provenance field normally has to enter:

| list | change |
|---|---|
| `BrowserMetadata` (`worker/app.py`) | **none** — `attitude`/`fix`/`lens`/`inertial` are `Optional[dict]`, so nested keys pass through |
| `PROVENANCE_KEYS` (`photo_processor.py`) | **none** — top-level only, copies whole objects |
| typed public projection (`photo_routes.py`) | **one line** per field in `_IMU_WINDOW_FIELDS` / the relevant allowlist |
| app serializer | yes |

`captured_at` itself is already a declared top-level field, and its MEANING
changing needs nothing at all: the worker copies `metadata['captured_at']` over
`exif_data.data.DateTimeOriginal` and then derives the stored `captured_at` from
that, so a new value propagates on its own.

**Already done, 2026-09-27, so this plan needs NO server deploy of its own:**
`capture_timing` is pre-declared in `BrowserMetadata` and listed in
`PROVENANCE_KEYS`, as an untyped dict with nothing sending it yet. A top-level key
is the only thing that requires a worker deploy; keys nested inside one ride
through untouched, and `exif_data` ships wholesale in the API response (the typed
`attitude`/`fix`/`lens`/`inertial` projections are a convenience on top of it, not
the route). So `source`, an exposure value on the monotonic clock, and the
press→exposure lag all go INSIDE `capture_timing` later, for free. A line in the
typed projection's allowlist remains optional — for type-checking, whenever.

**And rung 3 is already on the server.** The metadata overwrite hits
`DateTimeOriginal` only; the camera's own `SubSecDateTimeOriginal` survives beside
it, which is how the audit could compare the two. So the camera's exposure time is
present for every app photo already, no app change needed — at one-second
granularity, which is the rung's stated weakness.

## Do this experiment first — everything rests on it

**Which capture result belongs to the still?** The session capture callback sees
every request on the session. Attaching it to `ImageCapture.Builder` *should*
scope it to the still capture, but that is UNVERIFIED, and getting it wrong means
silently stamping a preview frame's timestamp — a new lie in place of the old one.

Protocol: add the callback to `captureBuilder` behind a log, take one capture in
`quality` mode, and check:

- it fires once per still, not once per preview frame;
- its bridged timestamp lands slightly EARLIER than `onCaptureStarted`'s wall time
  (dispatch delay) and before the JPEG arrives — the stats give
  `exposure→jpeg 349 ms` as the bound;
- its focus distance DIFFERS from the preview-derived value when AF ran;
- its `rolling_shutter_skew_ns` differs from the preview's 31.1 ms — if it does,
  that number has been wrong in every photo so far.

**Second experiment, cheap and independent:** a short-interval run of ~20
captures. It produces real `n` for `onCaptureStarted` (the `no onCaptureStarted`
counter appears in the stats dialog only if it ever happens — note that whether
those counters survive a process restart is unverified, so read them in the same
session), and it simultaneously stresses the upload-hold race, which the audit
flagged as still unexercised because its uploads all happened long after capture.

## Explicitly not in this plan

- Migrating existing rows. No backwards compatibility is required.
- Re-centring the window as a goal in itself. It falls out of `captured_at`.
- Re-reading the POSE at the exposure. Changing the gates to measure against the
  exposure makes the reported ages true; actually sampling the pose closer to the
  frame is a further improvement, and `StampRefiner` already exists for that kind
  of after-the-fact correction.
- The MediaTek vendor timestamp tag.

## Assumptions that are not yet measurements

Listed so they are not mistaken for findings:

- that `setSessionCaptureCallback` on `ImageCapture.Builder` yields exactly the
  still's result (experiment 1);
- that this HAL's `SENSOR_TIMESTAMP` is the start of exposure of the first row —
  the documented contract, not something verified here;
- that `UNKNOWN` means `CLOCK_MONOTONIC`/uptime on this HAL (documented, and the
  bridge should be sanity-checked empirically rather than trusted);
- that `onCaptureStarted` fires reliably. Evidence so far: **n = 1**.
