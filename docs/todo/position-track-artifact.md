# The position track as an artifact

Parked plan, opened 2026-09-28. Nothing here is built.

It comes out of a specific question — *would reconstruction benefit from arrays of the
other sensor values, the way it already gets one for the IMU?* — and the answer was
mostly no. Writing down why is half the point of this document, because the temptation
will come back.

## Why the other streams are NOT worth an array

| stream | verdict | why |
|---|---|---|
| gravity | **no** | derived from the accelerometer, which already ships raw at 398 Hz |
| linear acceleration | **no** | same |
| fused attitude (rotation vector) | **mostly no** | gyro at 398 Hz describes rotation across an exposure better: no fusion lag, no magnetometer error. What fusion uniquely adds is drift-corrected ABSOLUTE orientation, which changes slowly enough that one sample per photo already bounds gyro drift across a run |
| lens / focus | **no** | reconstruction needs the intrinsics for that frame, which is one value. A series would only document that 3A was moving — and the delta between the two bracketing preview frames says that in one number |
| **position** | **YES** | see below |

So this is not "ship arrays for everything". It is one stream, for one reason that does
not apply to any of the others.

## Why position is different

**It is the only stream whose per-photo value is a DERIVED ESTIMATE rather than a
measurement.** Everything else in the provenance is a reading the device actually took:
the attitude is a sample, the gravity vector is a sample, the lens values are a frame's
own. The position is an interpolation between the two ~1 Hz fixes bracketing the
exposure, computed by `StampRefiner` — and computed for each photo INDEPENDENTLY of its
neighbours.

That independence is the waste. A reconstruction fitting a trajectory through 86 photos
receives 86 separately-interpolated points, each with its own error, when the underlying
evidence is a single ~60-fix track that a smoother could fit once. The photos' positions
are correlated observations on one path; the pipeline is told they are 86 guesses.

And unlike the IMU it is nearly free: **~60 rows a minute**, against 23 310 accel samples
for the same minute. The data already exists in the tracking tables (`LocationEntity`)
and today leaves the phone only as a manual CSV export.

## What to ship

The RECEIVER's fixes — source `gps` — not the elected stream. The election answers "what
does this photo claim", which the columns already say; this artifact answers "where was
the device, measured", which is a different question and the one a solver wants. Per row:

- `t_ms` and `t_ns` (`elapsedRealtimeNanos`, so it joins the IMU artifact and
  `exposure_elapsed_ns` with no wall-clock quantization in the way — the same reason
  `imu_samples` carries `t0_ns`)
- latitude, longitude, altitude
- `accuracy_m`, `altitude_accuracy_m`
- `speed_mps`, `speed_accuracy_mps`, `course_deg`, `course_accuracy_deg`
- `provider`

Columnar like `imu_samples`, for the same reasons: it compresses, and a consumer reads
one array per field rather than parsing 60 objects.

### No claim table, and that is the interesting difference

`imu_samples` needs `imu_claims` because at 398 Hz a ±3 s window overlapping its
neighbours makes the same sample travel three times — kilobytes per photo, multiplied.
At 1 Hz the same window is **six rows**. An 80-photo run would carry ~480 rows where 60
are unique: 8x duplication of a payload that is already negligible, and gzip eats most
of it.

So ship the window, let the consumer dedupe by timestamp, and do not build the
machinery. The claim table earned its place by measurement; copying it here without the
measurement would be cargo cult.

## Step 0, independent and much cheaper: `capture_run_id` — **DONE 2026-09-28**

Verified 2026-09-28: **nothing identifies a capture run.** Not the photo detail
response, not the provenance. Adjacency IS inferable — sort by `captured_at`, then glue
slices whose `t0_ns` is one sample period past the previous end — but the field that
makes it inferable lives inside a gzipped artifact you have to fetch in order to
discover that two photos are adjacent at all.

That matters more than this whole plan, because of what the tiling verification found: a
photo's own IMU array contains its own exposure in **1 case out of 86** (at a 0.75 s
interval the exposure sits four photos back). **Rolling-shutter compensation and blur
analysis therefore require the run**, and the run is currently something a consumer has
to guess at.

A `capture_run_id` nested inside `capture_timing` costs one line and **no worker
deploy** — that object is already declared server-side as an untyped dict, the same
property that let `build` ship without one.

**Built the same day, and the RULE turned out to be the interesting part.** A run is not
"the interval session": what a consumer needs is contiguous inertial coverage, and that
is arithmetic. Photo N's window opens at `press − half` while photo N−1 stored up to
`press(N−1) + half`, so coverage is continuous exactly while consecutive presses are no
more than `2 × half` apart. A hand-pressed shot three seconds after another tiles with
it and belongs in the same run; two interval captures either side of a long pause do
not — which is precisely what the 4812.9 ms hole in the measured batch was.

`CaptureRunTracker` (commonMain, host-tested) mints a UUID at the press whenever the gap
exceeds one full window, and both save paths carry it. It is a HINT about where to look,
never a guarantee: a run can still be broken by sensors that were not running. The arrays
remain the proof; the id only says which ones to fetch.

## Server side

Unlike `capture_run_id`, the track is a TOP-LEVEL metadata field and therefore the
expensive kind. It follows the `imu_samples` route exactly (see
`recon-capture-metadata.md`, Phase 5), which is the argument for doing it this way rather
than inventing a second shape:

1. alembic: `photos.position_track_url TEXT NULL`
2. `BrowserMetadata.position_track: Optional[dict]` — declare it or pydantic drops it
   silently, which is the failure this project has already had twice
3. the worker gzips it into the storage pool and reports the URL
4. `_PHOTO_ARTIFACT_URL_COLUMNS` gains the column, so the delete sweep cannot forget it —
   the rename-rather-than-a-parameter lesson from the IMU artifact
5. it must NOT enter `PROVENANCE_KEYS`: a time series has no business in `exif_data`,
   which is read wholesale on every photo detail request
6. owner and public detail responses gain `position_track_url`

Deploy order is the usual one: alembic, then API, then worker.

## What this does NOT solve

- **Altitude.** Measured on the same batch: `altitude_accuracy_m` is **2.27 m mean**
  (1.42–3.29), which is BETTER than the 3.17 m horizontal — so the barometer idea this
  plan nearly grew is a modest win rather than an urgent one. (A single earlier photo
  read 18.5 m and an argument was about to be built on it; the distribution said
  otherwise. Recorded here so the wrong number is not re-derived.) The stamped altitude
  still wanders 4.5 m across a 60 s walk, which is about its own noise floor, so a
  barometer would buy decimetre RELATIVE height for a sequence. Whether the device has
  one is a separate question.
- **Scale.** Accelerometer double-integration is not a position source at these noise
  levels; GPS remains the only one. The track makes the GPS better used, not better.
- **The independence of the estimate itself.** This ships the evidence; fitting a smooth
  trajectory through it is the consumer's job, and deliberately so — the app records,
  the consumer aligns.
