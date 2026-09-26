# Battery work for long interval sessions

Parked 2026-09-26, deliberately unstarted. FIFO batching landed the same day and
changed enough logic for one sitting; everything below is scoped and measured but
not built.

**The measurements and the mechanism live in
[../imu-sampling-design.md](../imu-sampling-design.md)** — this file is only the
work, in the order worth doing it. Nothing here is repeated from there.

## Where things stand after batching

Sensor wakeups in capture mode went from ~932/s to ~133/s. What remains is **not**
the IMU: four sensors run unbatched at `sensorDelayUs`, which at capture's 30 ms is
~132/s on its own. Raising `IMU_BATCH_LATENCY_MS` past 2 s is rounding error and
costs the inline pre-shutter crash floor — see the design doc's table.

So the IMU is done. The items below are, in descending order of payoff per unit of
risk.

## 1. Wire the GPS interval setting · the cheapest real win

`GPS_INTERVAL_SETTING_LIVE = false` in `SettingsScreen`, so the control is hidden
and every activity gets `GPS_INTERVAL_DEFAULT_MS` = **1 s**. An interval capture
every ten seconds therefore asks the receiver for ten times the fixes it uses, and
a GNSS receiver costs far more than a sensor callback.

The control already exists. It is hidden for one reason: the value never reaches
`PreciseLocationService`.

**Shape of the work**: an interval parameter on `PreciseLocationService`, passed
from both `GeoEngine.startLocation` and the external service's claim, then flip the
flag. Scoped work, not research.

**What to watch**: `mergedConfig` takes `min` across claims, so a slow claim cannot
slow anything down while a faster claim is live — the setting is a floor, and the
UI should not imply otherwise. And `StampRefiner` interpolates between fixes; a
sparser stream widens the bracket it works from, which is a quality trade the
refiner's own margins may or may not absorb. Measure the refinement outcomes
before and after.

## 2. Slow or batch gravity and linear acceleration · the other half of the floor

`TYPE_GRAVITY` and `TYPE_LINEAR_ACCELERATION` are registered at `sensorDelayUs`
(33 Hz in capture) and their only consumers are the shutter stamp and the map's
motion readout. A shutter needs ONE recent sample, not thirty a second.

**Two options, different trades.** A slower rate is simple and makes the sample up
to that period old. Batching keeps the rate and delivers in bursts, which is
strictly worse here — the shutter reads synchronously, so a batched sample is stale
by up to the budget with no flush opportunity.

**What to watch**: `inertial.age_ms` already records the staleness, so the cost is
measurable rather than invisible — that is the number to look at after a change. A
gravity vector 200 ms old is fine on a held phone and meaningfully wrong mid-pan,
so judge it on a moving trace, not a still one.

## 3. Duty-cycle the IMU around scheduled shutters · real, and only for interval runs

Interval capture knows its own cadence, so the sensors could be registered only
around each expected shutter instead of continuously. Free for a long interval run
and useless for single shots.

**What to watch**: the ring would start cold each time, so the pre-shutter half of
the window needs the sensors up `IMU_WINDOW_HALF_MS` BEFORE the shutter — which
means the saving is `interval - 2×half`, i.e. nothing at all below a 6 s interval.
Worth it only for the long sessions this document is about, and worth checking
whether registration latency (the first samples after `registerListener`) makes the
early part of the window untrustworthy.

## 4. The preview · probably the largest term, and the least explored

The camera preview runs for the whole of an interval session. Nothing here has
measured it, and it is plausibly larger than every item above combined.

**Before designing anything**: measure. `dumpsys batterystats` per-UID, or a
before/after on a fixed-length run with the preview stopped between shots. An
interval capture arguably does not need a live preview between exposures at all,
but that is a capture-path change with framing and 3A consequences, not a power
tweak — `SceneMeter` meters continuously, and the exposure rules depend on it.

## 5. Stream the IMU dump instead of loading the table · robustness, not battery

Not battery work, parked here because it was found by the same session and has the
same cause: continuous logging made this table two orders of magnitude bigger than
anything else the dump handles.

`ImuDao.getAllSamples()` loads the WHOLE table, and `imuSamplesToCsv` builds one
String from it. Measured on a device, 2026-09-26: **257 769 rows** in a single dump
— which is the steady state, since five minutes at ~800 samples/s is 240 000.

    entity objects held at once   ~13 MB
    the joined CSV String         ~28 MB   (Kotlin String is UTF-16)
    the StringBuilder mid-build   roughly the same again

It has not OOMed. It did take seconds, and those seconds are what let two dumps
overlap and corrupt each other (fixed separately with a mutex — see the same day's
status entry).

**Shape of the work**: page the query (`LIMIT`/`OFFSET` by timestamp, or a
`Cursor`-returning DAO method) and append to the file per page rather than
composing one String. `writeExportCsv` currently takes the whole content and
resolves a destination that may be a `DocumentsContract` tree URI, so it needs an
append-or-stream variant rather than a signature change.

**What to watch**: the CSV contract is `pics`-facing and columns may only be
APPENDED, which a chunked writer must not disturb — the header is written once, not
per page. And paging by OFFSET over a table that is still being written to at
800 rows a second will skip or repeat rows; page by `timestamp > last` instead, the
way the high-water mark already does.

## Not worth doing

- **Decimating the IMU rate.** The window exists to describe a 1/60 s exposure and
  the shutter-detection experiments need the undecimated stream. This is the one
  saving that costs the feature.
- **Raising `IMU_BATCH_LATENCY_MS` further.** See the design doc's table: 0.2
  wakeups a second, against the inline crash floor.
