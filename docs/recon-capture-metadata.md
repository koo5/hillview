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
| `motion` | gravity, linear acceleration, and the IMU window's summary | 3, 4 |
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
`motion.imu_window` summary was all the SERVER got. This phase is the rest of it,
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

## Pitch has three homes — which is which

Raised as a confusing moment, 2026-09-26, and worth settling in writing because
the confusion is built into stored data and will outlive anyone's memory of it.

| where | what it means | who reads it |
|---|---|---|
| `photos.pitch` (alembic 032) | the ELECTED stamp — what the photo claims | the viewer's up/down navigation, the recon bench's frame manifest |
| `exif_data->'gps'->'pitch'` | the same number one layer earlier, on its way to that column | `docs/todo/pitch-backfill-from-usercomment.md`, `enrich/`'s photo mirror |
| `attitude.pitch_deg` in the UserComment | what the SENSOR read at that instant | anything reconstructing, via the public detail endpoint |

The first two are one value with two names. The third is a **different claim**
that happens to carry the same number most of the time, and the distinction is
the whole point of the user's rule for this work: *"instead of the fake 0f, we
should still record actual sensor pitch and roll, even when bearing is
overriden."* When a stamp was overridden by a map placement or a car course, the
elected pitch is a claim and only `attitude.pitch_deg` is still a measurement.
It is exactly the relation `bearing` has to `attitude.heading_true_deg`, and it
is recorded at the call site in `PhotoEntity.pitch` / `PhotoEntity.attitudeJson`.

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

### What this leaves genuinely open

`roll` now reaches the server — `attitude.roll_deg`, served publicly beside
pitch — but there is still **no `photos.roll` column**, while pitch has one. So
roll is per-photo readable and not queryable, which is the state pitch was in
before alembic 032. That is the open decision already parked in
`docs/todo/pitch-backfill-from-usercomment.md`, and this work changes its inputs:
new photos carry roll in a NAMED object with a typed projection, where before it
never left the phone.

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
| `motion` | 5, one of them the nested `imu_window` |
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

- **`pics` cannot read the new artifact.** Phase 5 lands the samples on the
  server as `photos.imu_samples_url`, a gzipped columnar payload, and the
  workbench still only knows the on-device CSV. That is the natural next
  consumer and the reason the payload was kept inspectable rather than packed.
- **The app's SQLite grows by the payload.** Tens of kilobytes per photo held on
  the row until upload — a deliberate trade (see "What the build decided"), but
  nobody has measured a long interval run's database against it, and there is no
  pruning of `imuSamplesJson` after a successful upload. A row keeps its window
  forever.
- **A toggle for the external camera's continuous capture.** ~100 MB of CSV an
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
