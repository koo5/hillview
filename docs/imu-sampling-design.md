# Inertial sampling: what runs when, and what breaks if you change it

Written 2026-09-26, before any of it is deployed, because three user-facing
controls are already foreseeable — a window-length setting, a fast-mode toggle in
the CAPTURE activity, and battery work in general — and each one lands in a
mechanism with non-obvious couplings. Two of them already bit this work twice in
one day.

Companion to [recon-capture-metadata.md](recon-capture-metadata.md), which covers
what the samples MEAN and where they travel. This file is only about when the
sensors are on and what that costs.

## What runs when

Two gates, both of which must pass, and neither is per-activity:

```
sensorsWanted()   =  active.sensors && (foreground || active.sensorsInBackground)
startImuSensors() =  … && active.imu
```

`active` is not any one screen's wish. It is `mergedConfig()` over every live
CLAIM, and the merge is deliberately greedy — a faster stream satisfies a slower
claim, so:

| field | merge |
|---|---|
| `sensors` | `any { it.sensors }` |
| `sensorDelayUs` | `min` |
| `locationIntervalMs` | `min` |
| `sensorsInBackground` | `any` |
| `imu` | `any` |
| `imuContinuous` | `any` |

There are exactly two claimants: `OWNER_ACTIVITY` (the composable binding) and
`OWNER_EXTERNAL_SERVICE` (the foreground service). The three configs:

| config | `sensors` | `sensorDelayUs` | `imu` | `imuContinuous` | background |
|---|---|---|---|---|---|
| `captureGeoConfig` | true | 30 ms | **true, always** | false | no |
| `externalCameraConfig` | true | 30 ms | **= toggle** | = toggle | **yes** |
| `mapOnlyGeoConfig` | true | 100 ms | false | false | no |

So fast sampling runs when the capture activity is in the foreground, or when the
external activity is running with its toggle on — and in the external case it
keeps running with the screen off, which is the case worth a switch.

**The IMU registers at `SENSOR_DELAY_FASTEST` (0 µs)**, which needs the
`HIGH_SAMPLING_RATE_SENSORS` manifest permission above 200 Hz. Without it
`registerListener` THROWS rather than clamping, which crashed the app on its first
real phone. `registerImu` now falls back to `IMU_UNPRIVILEGED_PERIOD_US` (5 000 µs
= 200 Hz) and gives up rather than propagating.

## The constants, and what each is pinned to

Nothing here is a free parameter. Every number answers to another one.

| constant | value | pinned to |
|---|---|---|
| `IMU_WINDOW_HALF_MS` | 3 000 | the user's choice of a ±3 s window |
| `IMU_SETTLE_MARGIN_MS` | 150 | how long after the window closes the read is safe |
| `IMU_FLUSH_PERIOD_MS` | 1 000 | batching writes so SQLite is not hit per sample |
| `ImuRing(capacity)` | 16 000 | **2 × half + margin, at ~1 kHz across two sensors** |
| `IMU_PAYLOAD_MAX_SAMPLES` | 16 000 | **the ring capacity** — a payload cannot exceed its buffer |
| `IMU_MAX_SAMPLES_TOTAL` (worker) | 16 000 | **the same number, in the other language** |
| `IMU_UPLOAD_HOLD_MS` | = `StampRefiner.UPLOAD_HOLD_MS` | crash recovery only; the bits free the row |
| `IMU_CLAIM_WAIT_MS` | 5 000 | worst case for the engine's write to land |

## Interdependencies — what breaks if you change X

**Lengthen the window (`IMU_WINDOW_HALF_MS`).** Four things follow, and only one
of them follows automatically:

- **The ring must grow.** It is sized `2 × half + margin` at roughly a thousand
  samples a second. A 10 s half with a 16 000-slot ring silently returns HALF a
  window — and a partial window looks like data, not like an error. This is the
  coupling most likely to be missed.
- **The payload grows linearly.** 6 s is ~120 KB of JSON, ~36 KB gzipped, measured.
- **The upload waits longer.** `IMU_UPLOAD_HOLD_MS` is derived from the window, so
  this one tracks by itself — the only one that does.
- **The two caps must grow with the ring**, in two languages, or honest payloads
  start being rejected at the worker's door.

**Add a fast-mode toggle to the CAPTURE activity.** The trap is the merge: `imu`
is `any { it.imu }`, so a toggle that only edits the capture claim does nothing
whenever the external service is also running. This is not hypothetical — the same
`any { }` defeated the external toggle's first version, and is why
`externalCameraConfig` takes the flag as a PARAMETER rather than reading the
setting itself. A capture toggle has to be the same shape, and the honest UI
cannot promise "off" while another claim can say yes.

Second trap: `imu = true` in `captureGeoConfig` is the per-shutter window, which is
the feature. A toggle there is a choice to record photos with no motion record at
all — different in kind from the external toggle, which only chooses whether to
log BETWEEN shutters.

**Reduce the rate.** Cheapest battery win and the most expensive to the data: the
window exists to describe a 1/60 s exposure, and shutter detection in the signal
needs the undecimated stream. `sensorDelayUs` is a `min` across claims, so a
"power saving" claim cannot slow anything down — only a claim that wants MORE can
speed it up. Lowering the floor means lowering it everywhere.

**Make windows work while backgrounded.** `captureGeoConfig` has
`sensorsInBackground = false`, which is correct today (a backgrounded capture pane
fires no shutters). Changing it needs a foreground service of the right type, the
way the external mode already has one.

## Batching — implemented 2026-09-26, and what it forced

`maxReportLatencyUs` is now passed (`IMU_BATCH_LATENCY_MS`, 1 s). What made this
more than a one-line change:

**The wall clock had to move.** Every sample's `timestamp` was
`System.currentTimeMillis()` read AT DELIVERY. That is correct only while samples
arrive one at a time: with a FIFO, forty samples arrive in one callback and would
all have been stamped with the same millisecond, flattening the timeline that the
window bounds, the `dt_us` deltas and the high-water mark are all built on.
`imuWallClockFor` now derives each sample's wall clock from its own
`SensorEvent.timestamp` against a periodically re-taken anchor. This is strictly
more accurate WITHOUT batching too — delivery time carries scheduler jitter, the
sensor's own timestamp does not — which is the tell that the old way was wrong
rather than merely incompatible.

**Six places assumed insertion order was time order.** Two sensors deliver their
bursts one after the other, so the last element added can pre-date most of the
batch. `fresh.last().timestamp` as a high-water mark would have gone BACKWARDS and
re-stored samples already written; `samples.first()/.last()` as window bounds
would have been arbitrary. All now `minOf`/`maxOf`, with
`ImuAttributionTest.aBatchedBurstIsBoundedByTimeNotByArrivalOrder` failing against
the old form.

**The read flushes.** `SensorManager.flush` before the deferred persist, awaiting
`onFlushCompleted` (so the listener is a `SensorEventListener2`) with a timeout
fallback, because `flush` returning true does not promise the callback ever
arrives. This makes the tail deterministic rather than probable.

**And the settle margin did NOT have to grow.** The first version derived
`IMU_SETTLE_MARGIN_MS` from the latency, on the theory that a sample still in the
FIFO at read time is lost. It is not lost from the STREAM — consecutive captures
tile, so it is past the high-water mark and gets claimed by the NEXT photo (user:
"a second missing off a 3-second tail doesnt really matter, if it makes it into the
next photo"). Only a session's final capture can truly lose a tail, which was
already accepted. So the latency answers to power, the margin stays at 150 ms, and
the upload hold is not coupled to a battery setting.

### Verified on a device, and what a device could not verify

    IMU ring registered at FASTEST, batching 1000ms
      (Goldfish 3-axis Accelerometer fifo=0/0, Goldfish 3-axis Gyroscope fifo=0/0)
    IMU window: 500 samples 1790456564676..1790456567169 (2493ms span), stored=189

FASTEST and batching coexist, and the timeline holds — 500 samples across 2493 ms
rather than collapsed onto one instant, which is the regression the clock change
prevents.

### And then on real hardware (Armor 22, 2026-09-26)

    IMU ring registered at FASTEST, batching 1000ms
      (ACCELEROMETER fifo=4500/3000, GYROSCOPE fifo=4500/3000)

**A 4 500-event FIFO with 3 000 reserved per sensor.** So batching is real here, not
merely accepted: at the measured ~400 Hz per sensor a 1 s budget needs 400 events,
13 % of what is reserved, and the reserved depth could hold **7.5 s** per sensor.
The IMU stream's wakeups go from roughly 800 a second to about one.

The budget is therefore conservative rather than optimistic, and it is bounded by
taste rather than by the hardware — the tiling argument means a longer one costs
nothing but tail re-attribution. There is room to raise it if a measurement ever
justifies the bother.

**`fifo=0/0` on the emulator**, by contrast, so the budget is accepted and
ignored there. A pass proves the registration is valid and the derived clock is sane; it
does NOT prove any power saving, and it does not exercise a real burst. Only a
device with a non-zero `fifo=` can, and that log line is where to look.

Two things this run found by reading the log rather than the result:

- **The fallback works.** Before the fix below, the device test logged
  `IMU registration at 0µs not permitted` and degraded to 200 Hz instead of
  crashing — the morning's `HIGH_SAMPLING_RATE_SENSORS` guard, demonstrated.
- **The test APK is its own package** (`cz.hillview.shared.test`) and does not
  inherit the app's permissions, so every IMU device test had been silently running
  at the fallback rate — a device suite testing a configuration the product never
  ships. `shared/src/androidDeviceTest/AndroidManifest.xml` now declares it.

## Other battery levers, still unused

Ranked by what they cost the data:

- **Duty-cycle around scheduled shutters.** Interval capture KNOWS its cadence, so
  the sensors could be registered only around each expected shutter rather than
  continuously. Free for interval runs, useless for single shots, and it needs the
  ring to survive the gaps or accept a cold start per window.
- **Drop the gyroscope when only shake matters.** `accel_peak_deviation_mps2` needs
  no gyroscope; `gyro_peak_rad_s` and rotation blur do.
- **Rate by motion.** The accelerometer can tell a stationary phone, and a
  stationary phone needs no 400 Hz. Costs the ability to detect the moment motion
  starts.

## Costs currently accepted

- **`imuSamplesJson` is never pruned.** Tens of kilobytes per photo, held on the
  row until upload and then kept forever. No sweep exists.
- **`imu_samples` / `imu_claims` are cleared five minutes back on every dump.**
  Safe for app photos, whose payload is copied to their own row as soon as the
  window closes; the table is a staging buffer, not the home.
- **Continuous mode is ~100 MB of CSV an hour.** The reason the external toggle
  exists, and why its label states the number.
