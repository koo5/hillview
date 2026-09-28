# Recon capture metadata — what a photo should know about how it was taken

Plan, 2026-09-26. Driven by one requirement from the user: **the phone should
store every bit of info it has, both raw and processed**, because the SfM /
3-D reconstruction bench downstream can use all of it, and because a value the
phone had and dropped is unrecoverable.

Status of each phase is marked inline. `docs/frontend2-status.md` carries the
dated record of what actually landed.

## What this grew out of

Roll had never left the device (2026-09-22). The sensor stack computed it from
the first commit, `BearingState` had no field for it, so the stamp could not
carry it and no column existed to receive it. Plumbing roll end to end turned
up a pattern rather than a one-off: **values the platform hands us, captured at
one layer, dropped at the next.** The magnetic heading had sat in the capture
snapshot since the beginning and every writer dropped it. The fused sensor's
own accuracy was read into a commented-out log line and thrown away.

So this plan is mostly not "add new sensors". It is "stop discarding what is
already in hand", plus two genuinely new things (lens calibration, an IMU
window).

## The shape: named objects in the UserComment provenance

One `attitude` object already travels there. The rest follow the same rule —
grouped objects, not a flat sprawl of keys, because the set will keep growing:

| object | what it holds | phase |
|---|---|---|
| `attitude` | device pose: headings, pitch, roll, the two accuracies, fusion, device rotation | DONE |
| `exposure` | the rule asked for and what it resolved to | pre-existing |
| `alt_location` | the position stream the photo did NOT record | pre-existing |
| `lens` | intrinsics, distortion, focus, zoom, focal length, skew | 2 |
| `fix` | the position-quality fields `FixState` currently drops | 3 |
| `inertial` | gravity, linear acceleration, and the IMU window's summary | 3, 4 |
| `imu_samples` | the RAW window — the one field that is **not** provenance and never enters the UserComment | 5 |

The existing FLAT keys (`location_source`, `location_age_ms`,
`location_accuracy_m`, `bearing_source`, `refined`) stay exactly as they are.
They are on the wire and older readers key on them; nothing here renames a
shipped key.

Each object needs, without exception:

1. the app-side serializer, with every field documented for what it means and
   what it does NOT mean;
2. a line in `BrowserMetadata` (worker/app.py) — pydantic drops undeclared
   keys **silently**, and this has already cost this project two keys for
   weeks;
3. an entry in `PROVENANCE_KEYS` (worker/photo_processor.py) — the synthesizer
   copies only what is listed;
4. a **typed projection** in the API (`photo_routes.py`) before it reaches a
   public response. The UserComment is client-written: serving it verbatim
   would put arbitrary JSON of arbitrary size in a public endpoint.

Because the worker declares each object as an untyped dict and passes it
through whole, **renaming a field INSIDE an object needs no worker change** —
only the app's serializer and the API's projection must agree. That is the
one-object design paying for itself, and it is why those two lists cross-
reference each other in their test headers.

## Phase 0 — the two focal lengths stop pretending to be one · DONE

`_curate_exif` collapses two DIFFERENT tags with an `or`:

```python
'focal_length_35mm': positive('FocalLengthIn35mmFormat') or positive('FocalLength35efl'),
```

They are not two readings of one thing:

- **`FocalLengthIn35mmFormat`** is a real EXIF tag (0xA405). The camera's own
  statement of its 35 mm equivalent.
- **`FocalLength35efl`** is not stored in the file at all. It is an **exiftool
  composite**, computed as focal length × exiftool's own guess at the crop
  factor (via `ScaleFactor35efl`, itself derived from sensor-size tags or a
  model lookup).

So the `or` silently picks a manufacturer statement when present and an
exiftool computation otherwise, and the consumer cannot tell which it got. When
both exist and disagree, the disagreement is lost — and the disagreement is
information, exactly as it is for the elected bearing versus the measured one.

The `positive()` guard around each is right and stays: phones write `0` for
"unknown" (every Armor 22 upload does), and a zero focal length is never real.

**Both are stored and served, named for provenance** — the same principle as
`heading_true_deg` beside `heading_magnetic_deg`:

- `focal_length_35mm` — the camera's own tag, and only ever that.
- `focal_length_35mm_computed` — exiftool's derived value, labelled derived.

This also settles `test_dslr_without_35mm_tag` honestly rather than by editing
the assertion to pass. Its intent was "do not present exiftool's sensor-math
AS the camera's number", which is now structurally true: the 5DS case yields a
`_computed` value and no `focal_length_35mm`. Its 68.46 against a 70 mm lens on
a full-frame body is exactly the imprecision the test was complaining about,
and it is now labelled instead of hidden or dropped.

## Phase 1 — the fields already captured and then dropped · DONE

No new sensor reads. Three sites where a value exists one layer up and dies:

- `PreciseLocationData` carries `altitudeAccuracy`, `bearing`,
  `bearingAccuracy`, `speed`, `speedAccuracy`, `provider`. `FixState` keeps
  six fields and drops all six of those.
- `zoomRatio` exists, pinch-to-zoom is wired, the UI prints "1.5×" — and the
  stamp records nothing. **Every zoomed photo therefore has wrong intrinsics
  and nothing says so.** This is the most consequential single gap in the list.
- `focusInfinity` is a user-facing toggle; the photo does not record which
  focus it was taken at.

## Phase 2 — `lens` · DONE

The largest recon win. Nothing in the codebase reads any of it today.

Per-camera, from `CameraCharacteristics` at bind:
`LENS_INTRINSIC_CALIBRATION` (fx, fy, cx, cy, skew — factory calibration),
`LENS_DISTORTION` (5 radial/tangential coefficients),
`SENSOR_INFO_PHYSICAL_SIZE`, `SENSOR_INFO_PIXEL_ARRAY_SIZE` (true pixel pitch),
`LENS_POSE_ROTATION` / `LENS_POSE_TRANSLATION` where present.

Per-shot, from the `TotalCaptureResult` the existing session capture callback
already receives (no new stream — `buildPreviewUseCase` has one for 3A):
`LENS_FOCUS_DISTANCE`, `LENS_FOCAL_LENGTH`, `LENS_APERTURE`,
`SENSOR_ROLLING_SHUTTER_SKEW`, and the dynamic intrinsics/distortion, which
can differ from the static ones because they track focus and zoom.

Together these give an exact intrinsic matrix instead of a 35 mm-equivalent
guess. Two honest caveats to encode rather than paper over:

- **Many phones do not populate `LENS_INTRINSIC_CALIBRATION`.** Its absence
  must be recorded as a fact, not as a gap a reader has to infer.
- Everything here is only checkable on a real phone. The emulator's camera is
  synthetic, and its rotation vector already cannot settle fusion questions.

## Phase 3 — `motion`: gravity and linear acceleration at the shutter · DONE

`TYPE_GRAVITY` gives an unambiguous "up" in the device frame, free of the
quantized remap that makes `attitude.roll_deg` a residual rather than an
absolute rotation. It constrains two rotation degrees of freedom directly,
which is why recon wants it even though pitch and roll exist.

`TYPE_LINEAR_ACCELERATION` magnitude is one float saying how hard the phone
was moving when the shutter fired — a per-frame quality signal to sort on.

## Phase 4 — the IMU window around the shutter · DONE

**Not continuous persistence.** A ring buffer in memory at sensor rate; at each
capture, the window bracketing the exposure is written out. Rows scale with
PHOTOS, not with session length: ~100 rows per shot at 100 Hz for a 1 s
window, against ~720k rows for two hours of continuous logging.

Where it goes, and why not the UserComment: a 1 s window of 6 axes at 100 Hz
is several hundred numbers, tens of kilobytes of JSON per photo, inside a
column that also holds the whole EXIF dump. So:

- **the samples** go to a new table beside `bearings` and `locations`, dumped
  to CSV. That is precisely what those tables and `GeoTrackingManager` exist
  for, and `pics` already reads those dumps and can join on timestamp;
- **a summary** (peak and mean acceleration magnitude, peak angular rate,
  sample count, window bounds) goes in `motion`, so a server-side consumer
  gets the quality signal without needing the CSV at all.

What it buys: motion-blur prediction, shake detection, and rolling-shutter
modelling — the things a single accelerometer sample at the shutter genuinely
cannot give, because one sample conflates gravity with linear acceleration
inseparably. That conflation is why the single-sample version was ranked below
gravity, and why the time series is worth the build.

CSV rule, verified against the consumer: **append columns, never insert.**
`pics` resolves every column by header name (`gps_log.get_column_index`), reads
a missing one as `None`, and sniffs the file type from the header's prefix.

## Phase 5 — the samples payload reaches the server · DONE 2026-09-26

Everything above stopped at the device for the raw samples: the per-photo
`inertial.imu_window` summary was all the SERVER got. This phase is the rest of it,
and it was the user's requirement — "the 6 s window really has to travel with the
photo".

**And the CSV dump was never the answer for an app photo.** An earlier draft of
this section said the samples "reached a workstation as `hillview_imu_<ms>.csv`",
implying that export was the route until Phase 5 replaced it. It was not a route
at all: nothing looks an app photo up in the tracking dumps. Those exist for
EXTERNAL camera frames — the phone as a sensor logger, `pics` reconciling the logs
against frames by time, which is why they land in `a22geo/`. The two consumers are
disjoint and easy to conflate:

| | app photos (frontend2) | external frames (`pics`) |
|---|---|---|
| route | the upload carries everything: `attitude`, `fix`, `lens`, `motion`, and `imu_samples` | the CSV dumps, which are the ONLY route |
| joined by | nothing — it is all one record | time, against the logs |
| needs the dumps | no | yes, entirely |

So Phase 5 did not replace an export path; it built the first one.

**Verified end to end** against the live stack, not only in units:
`backend/tests/integration/test_imu_samples_artifact.py` drives the real secure
upload with an `imu_samples` payload and asserts the artifact round-trips through
the storage pool, the URL is served on both the owner and the public endpoint,
absence stays absent, a malformed payload is dropped WITHOUT failing the photo,
and — the one no unit test can see — that the samples never enter the
UserComment.

### Why not in the UserComment

Because it is a bulk artifact, not provenance. A window is a few thousand
samples; at 400 Hz across two sensors, ±3 s is ~4 800 rows, and even trimmed to
a 2 s interval it is ~1 600. As JSON inside `exif_data` that is tens of
kilobytes added to a column the API already reads on every photo detail request,
and `exif_data` is loaded wholesale. The user's own framing settles it: the
UserComment has become a CHANNEL, and its original meaning — "what else must be
stored with the photo that EXIF has no tag for" — does not stretch to a time
series.

### The shape on the wire

Columnar and delta-encoded, one object per sensor:

```json
{"accel": {"t0_ms": 1700000000000,
           "dt_us": [2500, 2500, 2501, …],
           "x": [0.012, …], "y": […], "z": […]},
 "gyro":  {"t0_ms": …, "dt_us": […], "x": […], "y": […], "z": […]}}
```

- **Columnar, not row-wise.** One key name per ARRAY instead of per sample; a
  row-wise form repeats `{"t":…,"x":…,"y":…,"z":…}` four thousand times, which is
  most of the bytes.
- **`dt_us` deltas, not absolute timestamps.** Consecutive gaps are ~2 500 µs
  and four characters; absolute epoch milliseconds are thirteen, per sample.
  Sub-millisecond, because at 400 Hz a millisecond resolution would quantise
  two or three samples onto the same instant — the same collision the table's
  composite key exists to survive.
- **Rounded** to the sensors' real resolution (accel ~1e-3 m/s², gyro ~1e-4
  rad/s). Rounding to what was measured is not lossy; printing float noise is
  just larger.
- **Inspectable, not packed.** A base64 float32 blob is about the same size
  after gzip and cannot be read by a human debugging a pipeline. For a research
  artifact that trade goes the other way.

**Measured**, on synthetic data with realistic per-sample noise so gzip cannot
cheat: a 2 s trimmed window is 40 KB of JSON and 13 KB gzipped; the full 6 s
window at 400 Hz on two sensors is 120 KB and 36 KB. About 0.3 % of the JPEG it
travels with. (The encoder's own test prints the figure; the estimates this
paragraph replaced were 45 KB / 15 KB, so they were honest.)

### Transport: the existing bulk-artifact path, not a column

The API already takes bulk per-photo artifacts from the worker:
`POST /photos/upload-file`, metadata in headers (deliberately, to keep multipart
parsing off the event loop), written into the configured storage pool, returning
a public URL. That is what image renditions and DZI tile pyramids use. The IMU
window is the same kind of thing and should use the same road.

    app     buildUploadMetadata() -> `imu_samples` — a TOP-LEVEL metadata field,
                                     NOT a member of the provenance blob
    worker  BrowserMetadata.imu_samples: Optional[dict]   (declare or it is
                                     dropped silently — the standing rule)
    worker  DELIBERATELY NOT in PROVENANCE_KEYS: it must not enter the
                                     UserComment. Worth an explicit comment
                                     there, because every other key added to
                                     that model so far belonged in it.
    worker  serialise + gzip -> POST /photos/upload-file
                                     X-Relative-Path: <photo_id>/imu.json.gz
    worker  report the returned URL in ProcessedPhotoData.imu_samples_url
    api     store it (migration below) and serve it

### Size: what the Fly edge actually constrains

Raised 2026-09-26: the prod worker runs on Fly.io, Fly needs to be able to
replay requests, and replay has a size limit. All three are true — and the limit
does not reach this payload, because the design already keeps replay off the
upload.

`fly-replay` is emitted from exactly ONE place in this codebase: the bodyless
`GET /ready` preflight, `backend/worker/app.py:1042`. The upload itself is
steered by PINNING instead — the client reads `fly_machine_id` out of the
preflight and sends `fly-force-instance-id` on the upload
(`PhotoUploadLogic.kt:1033`, `uploadProtocol.ts:242`), which is a routing hint
the edge honours without buffering anything. The reason is already written down
at `app.py:1021`:

> Replay is fine here (GET, no body; uploads themselves exceed the ~1MB replay
> cap and must never carry fly-replay).

And the busy-upload rejection keeps that promise rather than quietly breaking
it: `UploadBackpressureMiddleware` answers 503 at the ASGI layer with
`content-type`, `content-length` and `retry-after` — no replay header — without
reading the request body at all. So there is no path on which a photo body is
asked to be replayed, and adding a field to that body cannot create one.

The arithmetic says the same thing more bluntly. The photo cleared the ~1 MB
replay cap by two orders of magnitude before any of this existed: `MAX_FILE_SIZE`
defaults to 150 MB, and Starlette's per-part cap was explicitly raised to match
(`app.py:43-59`, all three bind sites). A ±3 s window is ~45 KB of JSON, ~15 KB
gzipped; the ring's hard ceiling of 16 000 slots is ~480 KB raw, ~140 KB
gzipped. That is about 0.3 % of a typical JPEG. IMU samples cannot be what pushes
a request past a line the image cleared long ago.

What is worth recording, because the question is the right shape even though this
particular answer is no:

- **The metadata form field is fine.** It arrives as a multipart part on
  `POST /upload_async` (`PhotoUploadLogic.kt:1023`), and the per-part cap there
  is `MAX_FILE_SIZE`, not Starlette's 1 MiB default — that patch exists because
  the default rejected ordinary photos with `400 "There was an error parsing the
  body"`.
- **Never put samples in a header.** `/photos/upload-file` carries its metadata
  in headers by design, and the header block has a hard limit (16 KiB in h11,
  which uvicorn uses) that no amount of raising part sizes touches. The payload
  rides the BODY there; only `X-Photo-Id`, `X-Relative-Path` and
  `X-Client-Signature` go in headers.
- **Keep them out of `validate_json_payload`.** That validator (`app.py:119`)
  recurses per ELEMENT over the whole outgoing `ProcessedPhotoData`. A window
  carried as a JSON field would be 14 000+ Python calls per photo; carried as a
  file it is one URL. A third reason the bulk-artifact route is the right one.
- **Cap in samples, not bytes.** The payload's bound is the window and the
  window's bound is the ring: `IMU_WINDOW_HALF_MS` × two sensors, ceilinged by
  `ImuRing(capacity = 16_000)`. So the worker's door check belongs as a sample
  count matching that capacity — a number with a reason behind it, rather than a
  byte figure someone picked.
- **Continuous mode must never attach to a photo.** `GeoConfig.imuContinuous`
  produces ~100 MB of CSV an hour. It exists to fill the TABLE for a dump; the
  per-photo payload stays window-bounded no matter what it is set to.

### The server changes, concretely

1. **Alembic migration**: `photos.imu_samples_url TEXT NULL`. A URL column and
   not a JSONB payload, for the reason above — the photos row is read constantly
   by the map and must stay lean.
2. **`ProcessedPhotoData`** (both copies — `api/app/photo_routes.py` and
   `worker/app.py` declare the same model) gains `imu_samples_url`, and
   `save_processed_photo` writes it.
3. **The public detail response** gains `imu_samples_url`. A URL is a few dozen
   bytes, so unlike the payload it costs nothing to include; and it is public for
   the same reason `attitude` is — a reconstruction limited to the caller's own
   frames reconstructs nowhere.
4. **DELETION MUST SWEEP IT.** The delete path resolves a pool per stored URL
   and removes each rendition, plus the DZI descriptor and its `_files/` tree. A
   new URL column that nobody taught it about is a permanent leak of one file
   per deleted photo. This is the step most likely to be forgotten and the only
   one that quietly costs money.
5. **Caps, at the worker's door.** The payload is client-supplied and large by
   design, which is a new combination here. Cap the SAMPLE COUNT at the ring's
   capacity (`ImuRing(capacity = 16_000)`) rather than the body at a byte figure
   — see "Size" above for why that is the bound with a reason behind it —
   require the four arrays of a sensor to be the same length, and coerce every
   element to a finite float. The same discipline as `_provenance_object`,
   applied to something big enough that failing to apply it matters.

### What the build decided that the plan had not

Three things the plan left open, settled while building it.

**1. The payload is held on the photo row, not re-read at send time.**
`PhotoEntity.imuSamplesJson` (v26). The alternative — read `imu_samples` out of
the tracking table when the upload runs — loses the window whenever an upload is
delayed, because that table is cleared five minutes back on every dump while a
retry can happen hours later on a phone that had no network. A window that
existed at the shutter and is gone by the time the photo sends is the same
drop-site pattern this whole body of work was about closing. The cost is real —
tens of kilobytes per row in the app's SQLite — and it buys the guarantee.

**2. The payload carries what the photo OWNS, and attribution is DATA.**

The first attempt derived it: each photo took `[first sample it stored,
capturedAt + 3 s]`. That looks right and is not. A capture stored in TWO bursts —
an inline pre-shutter write and a deferred post-shutter one — and the bursts
interleaved ACROSS photos, because photo 2's inline write lands before photo 1's
deferred one. Traced on a 2 s interval run: the two photos' ranges overlapped by
three seconds, 44 sample-slots for 32 distinct samples. The trim would have saved
device storage and nothing else.

Two things fixed it. The pre-shutter call became **read-only**
(`summariseImuWindowBefore`), so there is exactly ONE storing burst per capture
and it is contiguous. And which samples that burst holds is now recorded as a
row: **`imu_claims`**, one line per photo — `capturedAtMs, fromMs, toMs,
sampleCount`.

Stamping every SAMPLE with its owner was the first instinct and the user was
right to refuse it: a 6-byte integer per row is ~33 KB per photo in the tracking
database and another ~14 characters per row in the CSV dump, tens of megabytes an
hour at continuous rates. A claim is ~24 bytes per photo for the same exactness —
about a thousandth of the cost. `ImuAttributionTest` is the regression test the
derived scheme would have failed.

It also turned a RACE into a condition. The upload pass used to wait out the SAME
deadline as the engine's deferred write — `capturedAt + half + settle`, one on
the engine's Handler, one on `Dispatchers.IO`, with no ordering between them — and
then read the table. The post-shutter half of every window was present or absent
by luck. Now the pass waits for the claim row to EXIST, and the claim is written
in the same coroutine as the samples and after them, so its presence proves they
landed.

What the read-only pre-shutter call gives up: if the app dies inside the ~3.15 s
after a shutter, that photo has no samples. It still has the summary, so the peak
acceleration and angular rate survive; the shape of the signal is what goes
missing, and only for the last shot before a crash.

Along the way: **`stored_count` was 0 on every photo.** The capture path computed
it and the pipeline's deferred rewrite of `motionJson` rebuilt the window record
without it. So the one field a server needs in order to concatenate a run without
double-counting always said "this photo added nothing". The tests written earlier
the same day covered the SERIALIZER, which was never wrong; nothing covered the
call site that dropped the value. It is exact now — the size of the claimed
range. `stored_from_ms` was removed again: with a claim table the wire needs only
the count, and the payload's own `t0_ms` says where it starts.

**3. Deleting is a rename, so that forgetting is impossible.**
The plan flagged the sweep as "the step most likely to be forgotten and the only
one that quietly costs money", and adding a parameter would not have helped:
every caller built `[photo.sizes for photo in photos]`, and nothing about that
line looks wrong once a second artifact column exists. So the unit of work
changed from a bare `sizes` dict to an artifact RECORD — `photo_artifacts(photo)`
— and `delete_photo_files_for_sizes` became `delete_photo_files_for_artifacts`.
A rename cannot be silently skipped: it is a missing name at all four call sites.
New artifact columns now go in `_PHOTO_ARTIFACT_URL_COLUMNS`, one line, one
place.

### What still decides the sizing

The on-device trim (`imuHighWaterMs`) is what keeps this affordable: without it,
consecutive ±3 s windows in a 2 s interval run each carry 6 s of samples and the
same sample travels three times. With it they tile, and the server can
concatenate a run into one continuous trajectory — which is the artifact the
workbench actually wants, and the reason the trim is load-bearing rather than
tidiness.

### VERIFIED ON PROD 2026-09-28: the windows tile exactly

The trim's whole purpose, measured end to end. 86 photos from one interval run, build
`da6a8994`, every artifact fetched and its `accel.t0_ns + cumsum(dt_us)` compared
against the next photo's `t0_ns`:

```
gap between consecutive owned windows: 2.513 ms   (78 of 79 boundaries)
sample period:                         2.5133 ms
overlaps: 0    lost samples: 0    duplicated samples: 0
23 310 accel samples, 59.80 s continuous
```

One sample period between slices is the exact result: no sample belongs to two photos
and none falls between them. The single exception is a 4812.9 ms gap, which is the pause
between two bursts rather than a defect.

**And the offset this document predicted is now a number.** It says above that "an
interval run below 6 s has each photo storing post-shutter samples anyway (the previous
window already claimed everything before this shutter)". Quantified: a photo's own array
contains its own exposure in **1 case out of 86**. The slice starts a median **2071 ms
AFTER** the exposure, and the exposure sits **four photos back** in the concatenated run
(74 of 86 cases exactly four). That falls straight out of the claim rule — photo N owns
`[end of N−1's claim, N's press + 3 s]`, and N's press is 3 s before that end, so at a
0.75 s interval N−4 stored it.

Nothing is wrong: the SUMMARY is centred on the exposure (4775 rows over the full ±3 s)
and the PAYLOAD tiles the session, which is the split the design chose. But it has a
consequence worth stating plainly, because it is not what a reader expects:

> **Anything that needs samples AT the exposure — rolling-shutter compensation, blur
> across the 20 ms the shutter was open — cannot be computed from a single photo.** The
> run has to be reassembled first.

**And nothing identifies a run.** Neither the photo detail response nor the provenance
carries a sequence, session or burst id. Adjacency IS inferable — sort by `captured_at`,
then glue slices whose `t0_ns` is one sample period past the previous end — but the field
that makes it inferable lives inside a gzipped artifact you must fetch to discover that
two photos are adjacent at all. A `capture_run_id` nested in `capture_timing` would cost
one line and no worker deploy; see `todo/position-track-artifact.md`.

One naming wrinkle found in the same pass: `sample_count` (4775) and `stored_count` (542)
are ROW counts across both sensors, so the per-sensor array length is half of each
(2388 and 271). The two are consistent with each other, but "sample_count" reads as
samples and a consumer sizing a buffer from it will be out by 2x.

## Pitch has three homes — which is which

Raised as a confusing moment, 2026-09-26, and worth settling in writing because
the confusion is built into stored data and will outlive anyone's memory of it.

| where | what it means | who reads it |
|---|---|---|
| `photos.pitch` (alembic 032) | the tilt that rode along with the elected BEARING — see the correction below | the viewer's up/down navigation, the recon bench's frame manifest |
| `exif_data->'gps'->'pitch'` | the same number one layer earlier, on its way to that column | `docs/todo/pitch-backfill-from-usercomment.md`, `enrich/`'s photo mirror |
| `attitude.pitch_deg` in the UserComment | what the SENSOR read, freshest at the shutter | anything reconstructing, via the public detail endpoint |

The first two are one value with two names. The third is the same quantity read at
a different moment — and the practical rule stands: for anything reconstructing,
use `attitude.pitch_deg`. It exists because of the user's rule for this work:
*"instead of the fake 0f, we should still record actual sensor pitch and roll,
even when bearing is overriden."* Recorded at the call site in
`PhotoEntity.pitch` / `PhotoEntity.attitudeJson`.

### CORRECTION 2026-09-27: there is no pitch election

This section used to call the first two "the ELECTED stamp — what the photo
claims" and the third "a different claim", by analogy with
`bearing` ↔ `attitude.heading_true_deg`. **The analogy does not hold, and "elected
pitch" is the wrong name.** Raised by the user: there is no pitch election UI, and
there isn't one because nothing elects pitch.

What actually happens:

- **Pitch is never chosen.** `BearingState.pitch` is documented as "tilt, when the
  elected source has one" — it rides along with whichever BEARING source won, and
  sources that do not measure tilt write **null**. So in the overridden case (map
  placement, car course) there is no elected pitch to be a claim; there is no
  pitch at all.
- **Both numbers come from one sensor path**, `EnhancedSensorService.sendSensorData`,
  which EMA-smooths every sample and then emits it.
- So the two stored numbers are the same smoothed measurement captured at two
  different moments of that stream: `attitude.pitch_deg` is the freshest at the
  shutter, `gps.pitch` is whatever was attached when the bearing was last set. On a
  real prod photo they differ by **0.07°** (6.9916 vs 6.9223) — two samples of a
  stationary phone, not a decision. The stamp refiner is not involved; it does not
  touch pitch.

  **CORRECTED 2026-09-28.** This bullet used to say the stream is throttled to 1° by
  `PITCH_THRESHOLD`/`HEADING_THRESHOLD`/`ROLL_THRESHOLD` and that every consumer
  therefore sees a signal stepping in ~1° units. **That throttle does not work.**
  `hasSignificantChange` is called with a literal `0` for the accuracy argument while
  `lastSentAccuracy` stores the REAL value, so `accuracyChanged` is
  `|0 − accuracy| >= 1.0` — true for any non-zero compass accuracy, and the gate
  returns `heading || trueHeading || pitch || roll || accuracyChanged`. Every sample
  passes. Measured confirmation: `attitude.age_ms` of 25–41 ms on real captures is
  exactly the 30 ms `SENSOR_DELAY_NORMAL_US` period.

  **Root cause, `358e0ab0` "there is no accuracy", 2026-01-09, in the TAURI app.**
  `ACCURACY_THRESHOLD` was documented as "Minimum accuracy change to trigger update
  (**degrees**)" — accuracy was a float angle. That commit replaced it with
  `magnetometerCalibrationStatus`, a 0–3 LEVEL, and dropped `headingAccuracy`. The
  comparison was never updated, so a threshold meaning "one degree" now reads "one
  calibration level" and the literal `0` argument trips it against any stored level of
  1–3. A units change that outran its threshold, not a stray constant.

  Two things follow from where it came from. `shared-kt` IS that plugin's code, so this
  has been live in the SHIPPED Tauri app since January, writing a bearings row per
  sample there too. And the hysteresis was always meant for the UI — needle jitter —
  which says where it belongs: at the consumer, not at the source.

  **So the shape is three consumers at three rates, currently conflated in one broken
  gate.** The attitude ring wants every sample; the UI wants hysteresis; the tracking
  table wants explicit pacing. Repairing the gate would serve none of them — it would
  throttle the stamp and the ring to fix a row-rate problem that deserves its own
  decision.

  Two consequences. The 0.07° above is sample-to-sample noise rather than
  threshold staggering, so the *conclusion* of this section stands (there is no pitch
  election, and `attitude.pitch_deg` is the one to use) while its stated mechanism was
  wrong. And `GeoTrackingManager.storeOrientationSensorData` has no pacing of its own,
  so a bearings row is written per sample — about **33 rows/second** in capture mode
  and 10/s on the relaxed map rate, each on its own IO coroutine. Whether the throttle
  should be repaired or removed is a real decision, and it is coupled to the attitude
  ring in docs/todo/captured-at-is-the-exposure.md: repairing it would starve the ring
  that wants every sample.

For bearing, elected-versus-measured is a real semantic distinction: a hand-set
arrow or a car course genuinely is a different claim from the compass. For pitch it
collapses into **fresh versus up-to-1°-stale**, which means `gps.pitch` carries no
meaning that `attitude.pitch_deg` lacks — only more staleness.

**Premature, not wrong forever.** User-supplied pitch is on the table (2026-09-27),
for the same reason user-supplied bearing exists: to override noisy sensors. The day
a pitch control ships, the elected/measured split becomes real for pitch exactly as
it is for bearing — and the home for that claim is the `photos.pitch` COLUMN, with
`BrowserMetadata.pitch` already its transport. Which is the argument for removing
`gps.pitch` rather than keeping it against that day: it is a redundant waypoint on
the path the claim will travel anyway, sitting under a key name
(`gps`) that a user-set tilt has even less business being under than a sensor's.

### Removing `gps.pitch` — the audit, 2026-09-27

Audited, then PARKED into **docs/todo/metadata-structure-sanitization.md**: the
removal is right, but it is one of five small changes to this column's shape that
each individually do not justify a migration. Doing them together is the plan.
The audit stands as the evidence — nothing reads it:

- **Zero readers** in `frontend/src`, `frontend2`, `shared-kt` or `enrich`. The
  frontend reads `photo.pitch`, the COLUMN, served by `hillview_routes.py:204` and
  typed in `photoCommon.ts:61`; its consumers are the up/down navigation
  (`mapState.ts:330-344`) and `data.svelte.ts:361-364`.
- **Inside the worker it is a pure waypoint**: written at `photo_processor.py:1750`
  inside `if metadata:`, read straight back at `:1891`. Both sit in
  `process_uploaded_photo`, where `metadata` is a parameter, so the reader becomes
  `(metadata or {}).get('pitch')` and the column is fed exactly as before.
- **Measured redundancy across 12 995 prod rows**, from the backfill plan's own
  query: every row with `gps->>'pitch'` has the column set, and
  `pitch IS NULL AND exif gps.pitch present` is **0**. It has never carried
  information the column lacks.
- **The backfill plan does not need it** — it reads
  `exif_data->'data'->>'UserComment'` for the 4 807-row population, which is the
  only one with anything to recover.
- The code already knew: the comment at `:1747` says "Pitch has no EXIF home the way
  bearing does (GPSImgDirection), so metadata is its only source."

**`gps.bearing` is NOT in the same position** and stays: it has a fallback check at
`:1838`, feeds `compass_angle` at `:1890`, and `GPSImgDirection` is a real EXIF
source for it. So this is a pitch fix, not a `gps` cleanup — the name stays the
misnomer this document already decided to live with.

Old rows keep the key; nothing sweeps it, which also keeps the backfill plan's
measurements valid as history. **Unverifiable from this repo:** the `pics` sibling
project, which is not in this tree. Pitch is measurably redundant with the column,
so the column is the better source there too, but nobody has grepped it.

### Why `gps` is the wrong name, and why it stays

`exif_data->'gps'` is not GPS. It is the geo stamp — latitude, longitude,
altitude, **bearing**, **pitch** — and the last two are not quantities a
receiver produces. `docs/one-state.md` says it plainly: "GPS course has no
pitch, so it writes none." Pitch joined that dict in `ea138734` (2026-08-19)
because that dict was already the one flowing to `ProcessedPhotoData`, not
because it belonged there.

It stays anyway, and this is a decision rather than an oversight:

- it is written into `exif_data` on ~78 000 live rows, so renaming is a data
  migration over every photo to fix a name;
- the pitch-backfill plan's SQL selects on that exact path, and `enrich/` reads
  `exif_data` out of its own mirror, so the readers are in two more places than
  this repo;
- nothing is WRONG in the data — only the label is. A rename would buy clarity
  for the next reader at the price of a migration and three coordinated changes,
  and this table buys the same clarity for free.

So: don't rename it, don't add a fourth home, and when writing something new
about a camera's pose, put it in `attitude`, which is named for what it measures.

### `alt_location` is a different pattern, and there is no `alt_bearing`

Asked directly, 2026-09-26, so: **`alt_bearing` does not exist.** Nothing in the
tree mentions it — not the app, not the worker, not the API. `alt_location` does
exist, and it is position ONLY: `lat, lng, ts, accuracy, source` (`AltLocation`
in `worker/app.py`), the live GPS fix kept beside a photo whose position came
from a manual map pan. It carries no bearing and no pitch, so it adds no fourth
home to the table above.

The two objects look like the same idea — "what the photo did not record" — and
are not:

| | `alt_location` | `attitude` |
|---|---|---|
| exists when | there IS a rejected candidate: a map pan won the election and a fix was available anyway | always, whenever the sensors were live |
| what it is | the RUNNER-UP for the same slot — same kind of value, different provider | the whole measurement the device made; a heading is one of its ten fields |
| shape | four numbers and a source label | pose, both headings, two accuracies, fusion, device rotation |

So `attitude` is not `alt_bearing` under another name, and nobody should add
one. An `alt_bearing` following the existing pattern would be a single
runner-up number, and `attitude.heading_true_deg` already carries that
unconditionally — including in exactly the case the pattern exists for, a
bearing overridden by a manual claim. The gap is filled; it is just not filled
under an `alt_` name, because what the device measured is not a candidate that
lost an election.

### Verified on prod, 2026-09-27 — and the elected pitch is owner-only

An owner-authenticated fetch of a real prod photo settled the three homes on live
data: `exif_data['gps']['pitch']` 6.9223 beside `attitude.pitch_deg` 6.9916,
differing by 0.07° — which turned out to be staleness, not a split. See the
correction above.

But `pitch` is **not a key in either API response**, public or owner — the column
is not projected at all. So the elected pitch reaches consumers ONLY through
`exif_data.gps.pitch`, which the public endpoint withholds along with the rest of
the raw dump. A public reader gets the MEASURED pitch and no elected one. That is
not what "three homes" implied, and it is worth deciding rather than leaving as an
accident of which projections were written. See
docs/todo/what-a-public-photo-publishes.md.

### What this leaves genuinely open

`roll` now reaches the server — `attitude.roll_deg`, served publicly beside
pitch — but there is still **no `photos.roll` column**, while pitch has one. So
roll is per-photo readable and not queryable, which is the state pitch was in
before alembic 032. That is the open decision already parked in
`docs/todo/pitch-backfill-from-usercomment.md`, and this work changes its inputs:
new photos carry roll in a NAMED object with a typed projection, where before it
never left the phone.

## `attitude` and `inertial` — the split, and the names

Asked before deploying, which was the right moment: does the split make sense,
and is `attitude` the right key?

### `attitude` stays, for a reason stronger than taste

It is the term of art — the A in AHRS, and `MadgwickAHRS.kt` is already in this
tree, so it is the house vocabulary rather than an import.

The obvious alternative, `orientation`, is actively unsafe here: the upload
metadata ALREADY carries `orientation_code`, the EXIF `Orientation` tag (1/3/6/8)
that says how to rotate an image for display. Two keys a rename apart, meaning
completely different things, one of them about display and one about where the
camera pointed. That collision is why the object was renamed away from
`orientation` in the first place, and it has not gone away.

### The split stays; `motion` was the defect

`motion` was wrong about its own contents. Its flagship field is `gravity`, which
a STILL phone reports at full strength and a moving one barely changes. An object
called "motion" whose most important value is largest at zero motion misleads
every reader exactly once.

Renamed to **`inertial`**: gravity, linear acceleration and the window's angular
rates are all inertial measurements, and it matches the vocabulary already here
(`imu_window`, `ImuRing`, IMU = inertial measurement unit).

**What was considered and rejected: moving `gravity` into `attitude`.** Gravity
does constrain two of the three rotation degrees of freedom, so co-locating it
with pitch and roll is tempting, and it would make the fusion-vs-accelerometer
comparison a single-object read. Against it, decisively: every provenance object
here carries ONE sensor family, ONE `age_ms`, and one trust story. Gravity's
timestamp is not the fused attitude's, so a merged object would have two ages and
no way to say which field each belonged to — and ambiguous provenance is the exact
failure this whole body of work exists to remove.

Keeping them apart also keeps the INDEPENDENCE visible: `gravity` is the
accelerometer's opinion about down, `attitude.pitch_deg`/`roll_deg` are the
fusion's. A reader comparing them is checking the fusion, not reading one number
twice — the same elected-versus-measured pattern as `bearing` against
`attitude.heading_true_deg`.

So the four objects are grouped by the subsystem that produced them — receiver,
camera, orientation fusion, inertial sensors — and each name now says what it
measures rather than which Android API produced it.

### One acknowledged redundancy

`inertial.linear_acceleration_magnitude` is derivable from the vector beside it.
It stays because the magnitude is what a server-side filter would sort or
threshold on, and computing a vector norm from a JSON array in SQL is not
something to ask of a bounds query. Noted rather than defended as necessary.

## Where the power and window design is written down

When the sensors run, what the constants are pinned to, and what breaks if the
window length or a fast-mode toggle changes:
**[imu-sampling-design.md](imu-sampling-design.md)**. Written because a
window-length setting and a capture-side toggle are both foreseeable, and both
land on the `any { }` claim merge that has already defeated one toggle.

## Rules that hold across all of it

- **Null is not zero.** A value the device did not measure is absent; `0.0` is
  a measurement. The whole reason `storeBearingNamed` exists is that a manual
  bearing row used to invent `0f` for pitch and roll — a phone held perfectly
  level, indistinguishable in the table from one that really was.
- **Raw and processed both travel, named for which they are.** Phase 0 is that
  rule applied to focal length; `heading_true_deg` beside
  `heading_magnetic_deg` is it applied to the compass.
- **Name it for what it measures, not for the API that produced it.** The
  platform calls the magnetometer's calibration status "accuracy"; the field is
  `magnetometer_calibration`, and the fused sensor's own rating, which the
  platform also calls "accuracy", is `fused_sensor_accuracy`.
- **One value, one name, end to end.** That number was briefly spelled three
  ways across the stack.
- **Columns for the high-rate tables, one JSON object for the per-photo
  record.** A row at 5–20 Hz cannot afford to repeat its key names; a per-photo
  blob that nothing queries and that will keep growing cannot afford a
  migration per field.
- **A field the emulator cannot exercise is NOT verified.** Say so.

## What landed, 2026-09-26

All five phases, in one pass. Nothing is phone-verified.

**42 fields across five objects**, agreeing app → worker → API. Checked
mechanically, not by eye: the app's serializers and the API's `_*_FIELDS`
specs are extracted and diffed, and the worker is checked for a
`BrowserMetadata` declaration plus a `PROVENANCE_KEYS` entry per object.

| object | fields |
|---|---|
| `attitude` | 10 |
| `fix` | 7 |
| `lens` | 14 |
| `inertial` | 5, one of them the nested `imu_window` |
| `imu_window` | 7 |

**Three drop sites closed, each the same shape as roll's.** `GeoEngine`'s
`PreciseLocationData` → `Location` conversion silently lost vertical, speed
and bearing accuracy, one hop before a `FixState` that had no fields for them
either. `zoomRatio` and `focusInfinity` existed, were shown on screen, and
never reached a photo. And nothing had ever read a single lens-calibration
key.

**Schemas.** `PhotoDatabase` 23 → 25 (`attitudeJson`, then `fixJson` +
`lensJson` + `motionJson` in one migration, because they are one change with
one reason). `GeoTrackingDatabase` 1 → 3 (`bearings.fusedSensorAccuracy`, then
the `imu_samples` table). Both apps export identical schemas at every version.

**The IMU window.** A `ImuRing` in the engine at `SENSOR_DELAY_FASTEST`, gated
behind `GeoConfig.imu` so only the activities that produce photos pay for it;
`persistImuWindow` writes the ±500 ms slice around each exposure and returns
the summary that travels with the photo. The ring is `internal` in its own file
rather than private inside `GeoEngine` so its wraparound and per-millisecond
sequencing have a host test — they are real logic and were briefly
untestable.

**One limitation worth knowing:** the raw IMU samples are cleared five minutes
back on every dump and only written to a file when tracking auto-export is on,
exactly like `bearings` and `locations`. So the SAMPLES survive a session only
with export enabled. The per-photo `imu_window` summary travels regardless and
is what a server-side reader gets.

**Tests:** 396 app jvm, 403 app android-host (11 of them the ring), 295 API
unit, 111 worker unit, 12 frontend unit. The previously failing
`test_dslr_without_35mm_tag` now passes because the value it objected to is
kept under its own name rather than dropped or disguised.

## The window: symmetric, deferred · DONE 2026-09-26

Settled by a fact neither of us had noticed. **The press is not the exposure.**
`capturedAtMs` is when the button went down; the camera starts exposing
measurably later — the capture path already logs `press→exp`, and Quality mode's
3A lock can push it toward a second. So a window ending at the press contains
*none of the frame it describes*, which is the wrong half for motion blur and
useless for finding a shutter transient in the signal.

That outranks the concatenation argument, which was otherwise a genuine tie:
with butt-to-butt trimming, an interval run below 6 s has each photo storing
post-shutter samples anyway (the previous window already claimed everything
before this shutter), and only an interval over 6 s gives a photo a truly
symmetric window. Correct, and a reason not to *fear* the deferral rather than a
reason to skip it.

How it works, and why the pieces sit where they do:

    capture path   engine.persistImuWindowAround(t)   -- fire and forget
      (allowlisted, owns the engine)                     schedules t+3s+margin
    engine         writes the window's samples to imu_samples
    upload path    delay to t+3s+margin, read imu_samples, summarise,
      (reads the TABLE, never the engine)              update the photo row

`OneStateArchitectureTest` **rejected the first version**, where the upload
pipeline called `GeoEngine.get` directly, and was right to: that file is neither
the hardware boundary, a writer adapter, nor a diagnostic. Splitting it so the
capture path triggers and the upload path reads the table is better than
widening the allowlist would have been.

`summariseImuWindow` is a pure function in shared-kt because two callers need it
— the engine summarises the slice it persisted, the upload path summarises the
slice it reads back — and one implementation means they cannot disagree about
what "peak" meant.

The inline before-shutter half is still taken, as a FLOOR: it is what a photo
carries if the deferred read never runs, and a row that is no longer there
cannot be updated.

## Continuous, full rate, for the external camera · DONE 2026-09-26

`GeoConfig.imuContinuous`, on for the external-camera activity. **Not
decimated** (user: "there are experiments that we will run on the samples, such
as shutter detection"), and that is the right call for the purpose: a mechanical
shutter is a transient a few milliseconds long, so 50 or 100 Hz would alias it
away entirely and the experiment could not run at all.

The price, stated plainly because it is the user's storage: a few hundred hertz
across two sensors is on the order of **100 MB of CSV an hour**. Batched to the
table once a second (`IMU_FLUSH_PERIOD_MS`) rather than a row per sample, which
at 400 Hz would be a write every 2 ms and would spend the session in transaction
overhead. A toggle in the external activity is still wanted and is NOT built.

External mode needs this because nothing there fires an app shutter to trigger a
window — it is the one mode a whole drive might be spent in, and without it that
mode recorded nothing.

## Can the samples reconstruct movement? — the honest answer

No, not as standalone dead reckoning; yes as a motion prior between anchors, and
outright well for relative orientation.

Double integration over a 6 s window, phone-grade MEMS:

| error source | typical | position error over 6 s |
|---|---|---|
| attitude error leaking gravity into horizontal, 1° | 0.17 m/s² | ~3.1 m |
| the same at 0.5° | 0.086 m/s² | ~1.5 m |
| accelerometer bias, 10 mg | 0.098 m/s² | ~1.8 m |

So half a metre to a few metres unanchored — 5–20 % at tens-of-metres scale,
which is not semi-reliable positioning. But anchored at both ends by the fixes
the refiner already brackets, the drift is largely absorbed and the IMU supplies
the SHAPE of the path between anchors, which straight-line interpolation cannot.
Relative ORIENTATION over these spans is ~0.1–0.3°, an order of magnitude better
than the magnetometer, which for bundle adjustment is arguably the bigger prize.
And interval capture parks the phone between shots, which gives accelerometer
bias observability for free.

## What ±3 s cost — the arithmetic that drove the design

Widening the window to ±3 s (user, 2026-09-26) is not a constant change. It
breaks the "persist at the shutter" design, because **half the window has not
happened yet when the shutter fires.**

What landed for now is honest rather than complete:
`persistImuWindowBeforeShutter` takes the 3 s BEFORE the exposure and says so in
its name, and the summary reports `window_start_ms`/`window_end_ms` so nobody has
to guess which half they are holding. Taking the past half and labelling it "the
window" would have been a silent half-measurement.

The symmetric version needs two changes, and the second one answers the
external-camera question for free:

1. **A deferred read.** `StampRefiner` already does exactly this shape for the
   compass — `delay` until `t + halfWindow + settleMargin`, then read the window
   from the table — and already holds the upload (`UPLOAD_HOLD_MS` is 60 s,
   twenty times the 3 s needed), and already updates the photo row after the
   fact. So the IMU window belongs there, not at the shutter.
2. **Continuous persistence, decimated.** A deferred reader reads the TABLE, so
   the future half has to be in it. That means the engine writes continuously
   rather than on demand — and continuous is also the only way the
   external-camera activity gets anything at all, since nothing there fires an
   app shutter to trigger a window.

Arithmetic for continuous, which is the question the user asked ("if you feel
that we can afford storing the samples indiscriminately"):

| rate (both sensors) | rows/hour | CSV/hour |
|---|---|---|
| `SENSOR_DELAY_FASTEST` (~200 Hz each) | ~1.4 M | ~72 MB |
| decimated to 100 Hz each | ~720 k | ~36 MB |
| decimated to 50 Hz each | ~360 k | ~18 MB |

So: **at FASTEST, no — not for a multi-hour external session. Decimated to
100 Hz, yes.** 100 Hz is comfortable for integrating orientation and for
trajectory shape; the fast samples only matter for per-exposure blur, which
external mode cannot analyse anyway because another app takes the photos. The
design that follows is two consumers off one listener: the FASTEST ring for a
shutter's peaks, and a decimated continuous write for the trajectory. A toggle
in the external activity is still worth having, because 36 MB/hour is a
user-visible amount of their storage.

**Dedup survives that change and gets simpler.** With continuous persistence
each sample is written once by construction, so `imuHighWaterMs` stops being
about the table and becomes purely about the PAYLOAD that travels: trim each
photo's window at the previous photo's end so the uploads concatenate into one
trajectory instead of N overlapping copies of most of one.

## Where the data actually travels — the question, answered

The user lost track, reasonably: there are three names for one pipe.

    app  buildUploadMetadata()        -> ONE JSON object, the upload's
                                         `--metadata` field
    ---- the wire ----
    worker  BrowserMetadata (pydantic) -> drops every key it does not DECLARE
    worker  synthesize_provenance()    -> copies PROVENANCE_KEYS out of it into
                                          a JSON string
    worker  exif_data['data']['UserComment'] = that string
                                          (only if no EMBEDDED UserComment)
    ---- the API ----
    api  photo.exif_data = <whole dict>  -> stored verbatim, no filtering
    api  _user_comment() -> _provenance_object() -> the public response

So it travels in the **metadata dict**. The worker *parks* it in the UserComment
slot because that is where the Android EXIF writer would have put it, and
parking both there makes one read path serve both upload routes.

The user's reading of what UserComment is FOR — "what other data do you need to
store with the photo that EXIF doesn't support" — is right, and so is the
conclusion: it is a channel now, and a few thousand samples per photo have no
business in it.

So the samples take a **second pipe**, which is what Phase 5 built. Same metadata
dict, and then it forks:

    app  buildUploadMetadata()        -> `imu_samples`, TOP-LEVEL
    ---- the wire ----
    worker  BrowserMetadata.imu_samples  -> declared, so it arrives
    worker  PROVENANCE_KEYS              -> deliberately DOES NOT list it, so it
                                            never enters the UserComment
    worker  _validate_imu_samples()      -> the only client-supplied BULK
                                            artifact in the pipeline, so the
                                            caps are explicit
    worker  gzip -> _get_size_url()      -> the same road the renditions and the
                                            DZI pyramids take
    ---- the API ----
    api  photos.imu_samples_url          -> a URL, not the payload
    api  both detail endpoints           -> the URL, public

The two pipes differ in exactly one property, and it is the one that matters:
everything in the first is read on every request that touches a photo, and the
second is fetched only by something that wants it.

## Still open

- **Every stamp describes the PRESS, not the exposure — and the fix is one field.**
  `PhotoCapture.android.kt` sets `capturedAtMs = System.currentTimeMillis()` and
  snapshots pose and lens BEFORE `takePicture`, and `persistImuWindowAround(
  capturedAtMs)` centres the +-3 s window on that same instant. `onCaptureStarted`
  then learns when the sensor actually began exposing and only LOGS it
  (`press->exposure` in `CaptureStatsLog`). The 2026-09-27 audit measured the gap
  from the retained camera EXIF at **546, 558, 581 and 2 014 ms** — the long one
  being the isolated capture, i.e. a cold 3A lock rather than a burst.

  Nothing is lost: a +-3 s window covers a 2 s lag comfortably, and this is why the
  window is symmetric. But the pose and lens values belong to the press, the
  reconstruction cannot tell WHERE in the window the shutter fell, and "per-shot
  lens metadata" honestly means "the latest known lens state at press".

  Going deeper made it worse than "the lens values describe the press", and the
  plan is now written up in **docs/todo/captured-at-is-the-exposure.md**. In short:
  `attitude`, `inertial` and `fix` report ages measured to the press, so at the
  1 881 ms the phone actually showed they consume 94 % of `ATTITUDE_MAX_AGE_MS`
  while reporting two digits; the `lens` object is fed by PREVIEW frames, so its
  focus distance is pre-autofocus and its 31.1 ms rolling-shutter skew is the
  preview's readout, not the still's; and `StampRefiner` interpolates the stamp TO
  the press, which makes it more precise without making it more true.

  The fix is one timestamp, not two: `captured_at` becomes the exposure, sourced
  from the still frame's own `SENSOR_TIMESTAMP`, with `captured_at_source` naming
  which rung of the ladder answered. That subsumes the ages, the lens, the refiner
  target and the window centring at once. It needs a clock bridge, because this
  phone reports `timestampSource: UNKNOWN` — and it needs one experiment first,
  because nobody has verified WHICH capture result belongs to the still.

- **`pics` cannot read the new artifact.** Phase 5 lands the samples on the
  server as `photos.imu_samples_url`, a gzipped columnar payload, and the
  workbench still only knows the on-device CSV. That is the natural next
  consumer and the reason the payload was kept inspectable rather than packed.
- **The app's SQLite grows by the payload.** Tens of kilobytes per photo held on
  the row until upload — a deliberate trade (see "What the build decided"), but
  nobody has measured a long interval run's database against it, and there is no
  pruning of `imuSamplesJson` after a successful upload. A row keeps its window
  forever.
- **`lens.intrinsics_available` is answered: FALSE on a real device**
  (2026-09-26, the phone under test). No factory `LENS_INTRINSIC_CALIBRATION`
  and no `LENS_DISTORTION`, and `focus_distance_calibration` is `uncalibrated`.
  Which turns out to vindicate capturing the sensor geometry SEPARATELY from the
  calibration: `focal_length_mm` 5.58, `sensor_physical_size_mm` [7.39, 5.55] and
  `sensor_pixel_array` [4624, 3472] all arrived, and they derive a pinhole model
  that is self-consistent to 0.02 % — fx = 3491.5 px, fy = 3490.8 px, i.e. square
  pixels, which is the sanity check that the three numbers are real. So a solver
  on this phone gets a usable focal length prior without the factory data, and
  `intrinsics_available: false` is the field doing exactly the job it was added
  for: saying "this device publishes none" rather than "this app did not look".
  Also now a measured number rather than a hypothetical:
  `preview_rolling_shutter_skew_ns` 31 089 628 — **31.1 ms** of readout per frame.

  **Renamed 2026-09-28, and the rename is the finding.** It is a PREVIEW frame's
  readout time. Every per-shot key in `lens` is: the session capture callback is
  attached to the preview builder, and the 2026-09-27 experiment established that
  attaching one to `ImageCapture.Builder` yields the preview stream too — CameraX
  does not hand out the still's `TotalCaptureResult`, and `ImageProxy` carries the
  timestamp and the rotation but not the result. Preview and still run different
  sensor modes and resolutions, and readout time scales with the lines read, so the
  still's skew is a DIFFERENT number rather than a staler one — which is why this one
  key is renamed while the rest of the half is merely dated. At walking pace, 31 ms
  of readout is about 4 cm of translation across the frame, so a reconstruction that
  models rolling shutter would be using the wrong constant, silently.

  The rest of the half now says what it is instead: `frame_values_source: "preview"`,
  `frame_values_referenced_to` (`"exposure"` or `"press"`) and an `age_ms` measured
  from the exposure, exactly like `attitude.age_ms` and `inertial.age_ms`. The age
  matters because focus MOVES in the gap — 7.0279527 to 6.9795275 diopters during one
  press→exposure window, measured 2026-09-27 — so `focus_distance_diopters` is a
  pre-autofocus value on any capture where 3A ran.

  **And the age turned out to be the largest of the three.** Measured on 23 prod
  captures, 2026-09-28: the shutter's latch sat **399–470 ms** from the frame, where
  the attitude's press-time staleness was ~50 ms — larger than press→exposure itself.
  Those ages divide by the 66.65 ms preview period to 5.986 … 7.052, i.e. **exactly 6
  or 7 whole frames, mean residual 0.99 ms**, because a capture RESULT arrives well
  after the frame it describes. (That quantization also shows the still's exposure is
  phase-locked to the preview grid to within ~1 ms, which is a separate finding and
  lives in `todo/captured-at-is-the-exposure.md`.) Hence `lensRing`: the per-shot half
  is now looked up at the exposure like the other two streams, `"press"` remaining the
  labelled fallback when no preview frame is within tolerance.

  Getting the still's own values needs a route to its capture result that CameraX
  does not currently offer; until one exists, the honest options were to label or to
  drop, and labelling keeps a usable bound on readout for anything that only needs
  the order of magnitude.

  **Independently verified against the HAL**, `dumpsys media.camera` on the same
  device (`/shared/a22_dumpsys_camera.txt`, 2026-09-26). Every value our `lens`
  object reported matches the HAL's own static characteristics exactly —
  `sensor.info.physicalSize` [7.38999987, 5.55000019], `pixelArraySize`
  [4624, 3472], `availableFocalLengths` [5.57999992], `availableApertures`
  [1.88999999], `focusDistanceCalibration` UNCALIBRATED — and NO intrinsic,
  distortion or lens-pose key appears anywhere in the dump, for any of the three
  cameras. So `intrinsics_available: false` is the device's answer and not a
  mistake in how we asked.

  And the reason is in the capability list:
  `[BACKWARD_COMPATIBLE MANUAL_SENSOR MANUAL_POST_PROCESSING READ_SENSOR_SETTINGS
  RAW BURST_CAPTURE CONSTRAINED_HIGH_SPEED_VIDEO]` — no `DEPTH_OUTPUT` and no
  `LOGICAL_MULTI_CAMERA`, which are the capabilities that make
  `LENS_INTRINSIC_CALIBRATION` mandatory. Its absence is per spec, so expecting it
  on an ordinary phone was the wrong expectation; the derived pinhole is the
  realistic path and it works.

  `sensor.rollingShutterSkew` is correctly absent from that dump too: it is a
  per-frame RESULT key, not a static characteristic, which is why the app reads it
  from `TotalCaptureResult` instead.

  Worth noting for later, from the same list: this device advertises **`RAW`**.
  DNG capture would remove JPEG compression from the reconstruction path
  entirely — a much larger change than anything here, but the capability is
  present and nothing currently uses it.
- **~~A toggle for the external camera's continuous capture.~~ DONE 2026-09-26.** ~100 MB of CSV an
  hour is a user-visible amount of someone's storage, and a multi-hour drive
  deserves an off switch. The config flag exists (`GeoConfig.imuContinuous`);
  what is missing is the control in the external activity that sets it.
- **Nothing is phone-verified**, and most of this cannot be: the emulator's
  camera is synthetic and its rotation vector does not follow injected sensor
  values. `lens.intrinsics_available` in particular needs a real device to
  answer, and it is the field that decides how much the rest of `lens` is
  worth.
- **`pics` reads neither new column nor the new CSV.** `bearings` gained
  `fusedSensorAccuracy` and there is a whole `hillview_imu_<ms>.csv` nobody
  loads yet. Both are additive and safe — that loader resolves columns by name
  and reads a missing one as `None` — so this is new capability waiting for a
  consumer, not a break.
- **Rolling-shutter skew is recorded but unused.** It is in `lens`; nothing
  downstream models it.
