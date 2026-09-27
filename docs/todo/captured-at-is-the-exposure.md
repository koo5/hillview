# `captured_at` should be the exposure, not the button press

Parked plan, written 2026-09-27. Nothing here is built yet.

The requirement, in the words that set it: **none of the data can be allowed to
lie.** Not "be maximally precise" — a coarse number that says what it is costs
nothing. What costs is a number that reads like a measurement of the photo and
is a measurement of something else.

And its sharper form, which is the one to hold onto (2026-09-27): **stop pretending we
know the exposure moment, if the research ends up showing that we don't.** That is the
deliverable. Shipping an exposure timestamp is only one way to satisfy it; saying
plainly that a value is press-derived satisfies it too, and costs nothing. The failure
mode to avoid is a third experiment that replaces one confident wrong answer with
another.

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
is the only thing that requires a WORKER deploy; keys nested inside one are stored
untouched. So `source`, an exposure value on the monotonic clock, and the
press→exposure lag all go INSIDE `capture_timing` later with no worker deploy.

**The API is a different story, corrected 2026-09-27 against prod.** Only the
OWNER endpoint ships `exif_data` wholesale (`photo_routes.py:986`). The PUBLIC
endpoint does not: it serves the typed `attitude`/`fix`/`lens`/`inertial`
projections plus `_curate_exif`, a deliberately small camera-settings subset that
excludes anything locating, because the raw dump can carry more precise position
than we publish. Verified on a real prod photo — the public response has 35 keys
and `exif_data` is not among them.

So a new field is visible to the photo's owner immediately, and invisible
PUBLICLY until `_IMU_WINDOW_FIELDS` / a `capture_timing` allowlist gets its typed
line. That is an API deploy, not a worker one, and it can be pre-declared the same
way if a second deploy is worth avoiding.

**And rung 3 is already on the server.** The metadata overwrite hits
`DateTimeOriginal` only; the camera's own `SubSecDateTimeOriginal` survives beside
it, which is how the audit could compare the two. So the camera's exposure time is
present for every app photo already, no app change needed — at one-second
granularity, which is the rung's stated weakness.

## The experiment RAN, 2026-09-27 — and the assumption was FALSE

`setSessionCaptureCallback` on `ImageCapture.Builder` is invoked for the **repeating
(preview) request, not for the still**. CameraX's public API does not hand out the
still's `TotalCaptureResult` this way, so harvesting it would have stamped a preview
frame's timestamp — precisely the failure this experiment existed to catch.

The evidence, from one capture in `quality` mode:

- The counter reached **#2476 before the press** and resumed climbing afterwards at
  ~15 Hz — 66.65 ms between results, the preview cadence.
- `exp=19997000ns iso=332` held constant, and `focus`/`skew` were **identical to the
  preview-derived `frameLens` on every single line**. Both callbacks are seeing the
  same frames.
- **The still's own frame is absent.** `onCaptureStarted` fired at 15:15:40.776. The
  results bracket it — #19 at −56 ms, #20 at +11 ms — and their sensor timestamps are
  66.667 ms apart, a uniform preview cadence with nothing extra in the window. The
  repeating request paused for **251 ms** across the capture and then delivered three
  results within 5 ms to catch up, which is the signature of the still INTERRUPTING
  the stream rather than joining it.

The instrumentation is reverted: at 15 Hz it is log spam, and `frameLens` already
harvests everything it saw.

### Three things the run established anyway

1. **The lens lie is confirmed independently.** Focus moved from **7.0279527 to
   6.9795275 during the 1213 ms press→exposure window** (0.6 s after the press). The
   value shipped at press is demonstrably not the frame's.
2. **The clock bridge is sound.** The bridged timestamps bracket `onCaptureStarted` at
   −56 ms and +11 ms, i.e. the exposure lands between two preview frames as it must.
   `elapsedRealtimeNanos − System.nanoTime()` converts this HAL's uptime-base
   timestamps correctly, so that formula is reusable if any monotonic route appears.
3. `press→exposure` was **1213 ms**, `exp→jpeg` 389 ms — quality mode again.

### The ladder, corrected — and I had rung 3 wrong

I called the JPEG's own EXIF "second-granular" and treated it as the weak rung. That
was wrong. `DateTimeOriginal` is second-granular; **`SubSecTimeOriginal` carries
milliseconds**, and the prod photo proves the pair survives the whole pipeline —
`SubSecDateTimeOriginal: '2026:09:27 13:34:16.948'`, written by the HAL for the frame
it exposed, still intact on the server because the app's EXIF rewrite touches
`DateTimeOriginal` and not the SubSec pair.

So the ladder is now:

1. **The JPEG's `SubSecDateTimeOriginal`** — the frame's own exposure time at
   millisecond resolution, from the only component that knows it. Needs the local
   timezone handled, since `OffsetTimeOriginal` is absent (the +02:00 reading is
   self-validating: any other offset puts the delta an hour out).
2. `onCaptureStarted` — ms, dispatch-delayed, and the bracket above at least places it
   inside the correct 66 ms window.
3. The press, labelled.

### Precision needed: milliseconds, and no more

Settled 2026-09-27, because it decides how hard this is worth working. The frame
integrates light for **20 ms** (`exp=19997000ns`) and the sensor reads out over
**31 ms** (`rolling_shutter_skew_ns`). No timestamp can meaningfully place "the
instant the photo is of" more sharply than that, so millisecond resolution is already
a twentieth of the exposure window and sub-millisecond precision is decoration.

That retires the main argument for fighting CameraX: `SubSecDateTimeOriginal`'s
milliseconds are enough. It does NOT retire the correctness question below.

### Let the consumer do the alignment

The preferred division (user, 2026-09-27): the app RECORDS, the consumer ALIGNS. If
the worker and the recon workbench read `SubSecDateTimeOriginal` and look that moment
up in the sample arrays themselves, the app may not need to change at all for
alignment — it already ships both halves, and the server already holds both. That
takes the restructuring of `capturedAtMs` (the filename, the snapshot ordering, the
window centre) off the critical path entirely.

What remains app-side is then only the honesty part: not presenting press-derived
values as frame-accurate.

### ANSWERED 2026-09-27: `SubSecDateTimeOriginal` is NOT the exposure

`exiftool` on the 15:15:40 capture (`hillview_photo_1790514939565.jpg`, whose filename
epoch 15:15:39.565 confirms it is the same press the log describes):

```
Date/Time Original    : 2026:09:27 15:15:40.951
Sub Sec Time Original : 951
OffsetTimeOriginal    : absent
```

| | | vs exposure |
|---|---|---|
| press (`capturedAtMs`, = filename) | 15:15:39.565 | −1211 ms |
| exposure (`onCaptureStarted`) | 15:15:40.776 | — |
| **`SubSecDateTimeOriginal`** | **15:15:40.951** | **+175 ms** |
| saved (`onImageSaved`) | 15:15:41.166 | +390 ms |

**Neither candidate.** It is an intermediate HAL/encode moment — 175 ms after the
exposure began and 215 ms before the file landed. That is 70 IMU samples at 398 Hz and
about nine times the 20 ms the shutter was open, so for attributing motion blur it
points at the wrong 20 ms entirely. It is not usable as the exposure instant, by the
app or by a consumer.

**Which corrects what I wrote an hour earlier.** I said owning the file write "wins
nothing that matters for timing", on the argument that millisecond resolution is
already below the 20 ms/31 ms noise floor. The resolution argument still holds. The
conclusion did not: there is now **no millisecond-accurate source of the exposure
moment at all** except `ImageProxy.imageInfo.timestamp`. Owning the write buys
CORRECTNESS, not precision — a different and much better reason.

So, honestly, the ladder is:

1. **`ImageProxy.imageInfo.timestamp`** via `OnImageCapturedCallback` — the frame's own
   `SENSOR_TIMESTAMP`. Exact, and the only route that actually knows. Costs owning the
   file write.
2. **`onCaptureStarted`** — dispatched to the MAIN executor, so its lag includes
   main-thread queueing and is unmeasured. The preview bracket (−56/+11 ms) places it
   in the right region and no closer.
3. **The press** — 1211 ms early here, 546–1881 ms across everything measured.

`SubSecDateTimeOriginal` is off the ladder. One caveat: n = 1 for the +175 ms, one
device, `quality` mode. If that offset turned out stable across captures and modes it
could in principle be calibrated out — but treating a measured-once HAL constant as
known is precisely the pretending this plan exists to stop, so it would need measuring
per device and mode, not assuming.

### Latency mode, 13 captures, 2026-09-27 — the numbers that close it

An interval run in `Latency` mode with `exiftool` on every file:

| | mean | range |
|---|---:|---:|
| `press→exp` | **376 ms** | 332–426 |
| `exp→jpeg` | 342 ms | 269–475 |
| **EXIF − exposure** | **+139 ms** | +94…+163 (stdev 17) |

Quality mode, for contrast: `press→exp` **1213 ms**, EXIF − exposure **+175 ms**.

**1. EXIF is not the exposure, and the conclusion is robust.** `onCaptureStarted` can
only be LATE relative to the true exposure — it is a main-thread dispatch, and delay
only adds. So the true exposure is at or before our reference, which makes EXIF **at
least** 139 ms after it. The direction of the one unmeasured error cannot rescue this
reading; it can only make the gap wider. n = 13, plus the quality-mode sample.

**2. It is a rough constant, not an encode fraction.** As a fraction of `exp→jpeg` the
offset has relative spread 21 % (40.5 % ± 8.5); as an absolute offset, 12 %
(139 ± 17 ms). The extreme point contradicts the fraction hypothesis outright: the
largest `exp→jpeg` (475 ms) carries the SMALLEST offset (+94 ms), where a fixed
fraction would predict the largest. So it is best read as a HAL pipeline delay of
~140 ms in this mode, ~175 ms in quality.

**3. And no constant can fix it anyway — this is the finding that matters.**
`press→exp` varies **332–426 ms within a single run at constant settings**. Not across
modes, not across devices, not across scenes: within one interval session. So no
calibration, no per-device constant and no per-mode constant can recover the exposure
moment from the press. Only a PER-CAPTURE measurement can. That closes the
"calibrate the offset" idea for good, for both the press and the EXIF timestamp.

**4. The default mode lies too, by 376 ms.** I guessed Latency would collapse the gap
to under 100 ms. It does not — 376 ms is about 150 IMU samples and roughly 19× the
20 ms the shutter is open. So this is not a quality-mode quirk to be avoided by using
the default; `captured_at` is wrong in every mode, only less so.

### THE PROBE SUCCEEDED, 2026-09-28 — the exposure instant is reachable

`ImageProxy.imageInfo.timestamp` from `takePicture`'s in-memory overload is the frame's
own `SENSOR_TIMESTAMP`, it is present and non-zero, and across five captures the delta
against the main-thread reading was **always negative** — which is the proof that it
precedes the callback reporting it rather than being that callback's own clock.

| | |
|---|---|
| dispatch lag (`onCaptureStarted` late by) | **104 ms** mean, 94–126, stdev 14 |
| press→exposure, measured via the dispatch | 370 ms mean, spread 82 |
| press→exposure, **true**, from `sensor_ts` | **267 ms** mean, spread **50** |
| `rotationDegrees` | **0** on every capture |
| format / size | JPEG (256), single plane, 1440×1920, ~530 KB |

**1. The dispatch lag is ~104 ms and varies by ±16.** So `onCaptureStarted` can never be
a precise proxy — not because it is biased, which could be corrected, but because it
jitters by more than the exposure duration.

**2. Measuring through it inflated the variance as well as the magnitude.** True
press→exposure has spread 50 ms where the dispatch-measured figure had 82. Part of what
looked like camera inconsistency was our own main thread. The camera is steadier than
this plan said it was.

**3. The clock bridge is load-bearing, and now measured.** On this device
`elapsedRealtime` runs **2.016 days** ahead of the uptime base `SENSOR_TIMESTAMP` uses —
so treating one as the other would be two days wrong, not milliseconds. The offset was
stable across all five captures to **0.61 ms**, and that figure includes the millisecond
truncation in the log line, so the bridge itself is sub-millisecond. Read the two clocks
back-to-back, as the probe does, and the conversion is exact for our purposes.

**4. `rot=0` removes the risk that worried me most.** No hand-rolled rotation is needed;
the HAL's JPEG carries its own orientation and CameraX asks for no correction.

**5. The direct `File` write to `DCIM/Hillview2` succeeded** on this device, so the
PublicFolder target of the storage chain works from bytes. Only the `MediaStore` target
is unproven from the in-memory path.

#### Corrections to every number this document reported against the dispatch

| | reported | true |
|---|---:|---:|
| Latency press→exposure | 376 ms | **~272 ms** |
| Quality press→exposure | 1213 ms | **~1109 ms** |
| EXIF `SubSecDateTimeOriginal` offset | +139 ms | **~+243 ms** after the exposure |

So `captured_at` is ~270 ms before the frame in the default mode and ~1.1 s in Quality,
and the camera's own EXIF timestamp is nearly a quarter-second LATE — worse than this
document said, and in the direction it predicted the unmeasured error could only go.

#### Unrelated observation, worth a look

Every probe capture was **1440×1920**, ~530 KB, from a sensor whose
`sensor_pixel_array` is 4624×3472. The probe uses the app's own `ImageCapture`, so that
is the configured capture resolution and not a probe artifact — but if full resolution
was intended, something is pinning it down.

### So: we did not know the exposure moment, and now we can

Which is the outcome the requirement was written for. Two honest responses, and they
are not exclusive:

- **Label it** (cheap, no new data, no deploy): stop presenting press-derived values as
  frame-accurate. `captured_at` stays the press and says so; the ages and freshness
  gates say what instant they are relative to. This satisfies "stop pretending"
  completely and on its own.
- **Go and find out** (costs the save path): `OnImageCapturedCallback`, which hands over
  the exact value. Then `captured_at` can BE the exposure and the ages become true
  rather than merely labelled.

What is no longer on the table: consumer-side alignment from `SubSecDateTimeOriginal`.
The worker and the workbench cannot recover the exposure from what is currently
stored, because nothing currently stored is the exposure.

### The superseded assumption, kept for the record

**Nobody has checked what `SubSecDateTimeOriginal` actually timestamps.** The EXIF spec
says "when the image was generated"; HALs interpret that as exposure start OR as the
moment the JPEG was encoded, and on this device those are **390 ms apart**
(`exp→jpeg 389 ms`). Making it rung 1 without checking would repeat the mistake that
just cost an experiment.

It is cheap to settle, and the photo is still on the phone. From the 15:15:40 capture's
log — all device-local, the same clock EXIF uses:

```
press     15:15:39.563     (40.776 − 1213 ms)
exposure  15:15:40.776     onCaptureStarted
jpeg      15:15:41.166     the "saved:" line
```

So `exiftool -SubSecDateTimeOriginal -SubSecTimeOriginal <that file>` answers it
outright: ~`.776` means it marks the exposure and it is rung 1; ~`1.166` means it marks
encode time and is useless for this, leaving `onCaptureStarted` as the best available
and the honest label as the whole of the fix.

### The option that gets the exact value, at a price

`ImageCapture.OnImageCapturedCallback` hands over an `ImageProxy` whose
`imageInfo.timestamp` **is** that frame's `SENSOR_TIMESTAMP`. The app uses
`OnImageSavedCallback`, so it never sees an ImageProxy, and switching means owning the
file write.

That may cost less than it sounds: the app **already** rewrites the whole file for
EXIF afterwards — a 4–25 MB copy, moved off the main thread for exactly that reason —
so writing once from memory could be cheaper than saving and rewriting. Real upside,
real blast radius across the save path. Not decided.

## The original experiment protocol, kept for the record

**Which capture result belongs to the still?** The session capture callback sees
every request on the session. Attaching it to `ImageCapture.Builder` *should*
scope it to the still capture, but that is UNVERIFIED, and getting it wrong means
silently stamping a preview frame's timestamp — a new lie in place of the old one.

**Instrumentation BUILT 2026-09-27** (`PhotoCapture.android.kt`): the callback is
attached to `captureBuilder`, the clock bridge is read back-to-back inside it, and
`StillFrameFacts` is stored but consumed by nothing. Every acceptance check below is
computed INTO the log line rather than left to the reader:

```
still result #N: sensor_ts=… bridged=…ns (−Xms vs onCaptureStarted),
  focus=… (preview …), skew=…ns (preview …ns), exp=…ns iso=…
```

`stillResultCount` resets at each press, so `#N` answers the first check directly:
`#1` once per capture is the pass, and `#N` climbing with preview frames is the
failure that would have made this a new lie instead of a fix.

Protocol: take one capture in `quality` mode and check:

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
