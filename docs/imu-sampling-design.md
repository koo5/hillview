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

## The battery lever that is not being used

**Hardware FIFO batching.** `SensorManager.registerListener` has a five-argument
form taking `maxReportLatencyUs`. With it, a sensor with a hardware FIFO buffers
samples and wakes the application processor in bursts instead of per sample — at
400 Hz that is the difference between ~400 wakeups a second and a handful. We pass
the four-argument form, so every sample is a wakeup.

This is almost certainly the largest available saving, and the design is already
compatible with it: samples arrive with their own `SensorEvent.timestamp`, the ring
is append-only and time-ordered, and nothing assumes callbacks are evenly spaced.
A burst of forty samples with correct timestamps is indistinguishable downstream
from forty individual callbacks.

What to check first, on a real device, because a FIFO that does not exist changes
nothing: `Sensor.getFifoMaxEventCount()` / `getFifoReservedEventCount()`, or
`adb shell dumpsys sensorservice`. A latency budget also interacts with the
deferred window: the read happens at `shutter + half + settle`, so
`maxReportLatencyUs` must be well under `IMU_SETTLE_MARGIN_MS` or the window's tail
is still in the FIFO when it is read.

Other techniques, ranked by what they cost the data:

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
