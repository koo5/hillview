# One state

**There is one user-facing location/orientation state. Everything either
writes it or reads it. Nothing talks to the hardware behind its back.**

This is the load-bearing idea of the original Tauri app, extracted by reading
its source, and it is not a style preference — every geo bug this port has
produced has been a violation of it. Read this before adding anything that
touches position or heading.

## The state

`MapStateHolder` (frontend2) — the port of the original's `mapState.ts`:

- `spatial` — where the user is: latitude, longitude, zoom, range, map
  orientation, the source that last set it, and when.
- `bearing` — where the user faces: the bearing, the source, the photo uid if
  a photo set it, the magnetometer accuracy, the magnetic heading and the
  pitch when the elected source measures them, and when.

"Which way am I facing" has exactly one answer at any instant, and it is
`bearing.bearing`. Not one answer per screen, and never a fresher one
available to whoever asks the sensor directly.

## Writers

Every source of position or heading writes through the ONE funnel,
`updateSpatial` / `updateBearing`:

| writer | source string | where |
| --- | --- | --- |
| compass (walking) | `android-compass-true` | `MapScreen.android.kt` |
| GPS course + mount offset (car) | `gps-kalman` | `MapScreen.android.kt` |
| dragging the bearing arrow | `arrow_drag` | `MapScreen.android.kt` |
| turning to a photo in the viewer | `photo_navigation` | `ViewerState.kt` |
| panning the map / claiming a position | `map`, `manual` | `MapScreen.android.kt` |
| the GPS fix | `gps` | `MapScreen.android.kt` |

`updateBearing` does three things in one call — set the value, publish the
election, write the tracking-table row — so that a recorded row cannot
disagree with what the user was shown. Adding a fourth job is fine; adding a
second way to do any of the three is not.

A writer that has no value for a field writes `null`, and means it: a
GPS course has no pitch, so it writes none, rather than letting a compass
sample ride along under its name.

## Readers

The map arrow, the capture pill, what a photo is stamped with, the viewer's
ring and its neighbours, the external-camera pane, the marker fade, and the
fix's freshness. All of them read the state. None of them samples hardware
to answer a question the state already answers, and none of them keeps a
stored copy of an answer that has a clock in it (see "Derived, not
stored").

## The hardware boundary

`GeoEngine` owns every registration — sensors and fixes — and publishes
samples. It is the ONLY component that talks to `SensorManager` or the fused
location provider. Its samples reach the app in exactly one way: a writer
turns them into `updateBearing` / `updateSpatial` calls.

Owners ASK the engine for what they need (`configure(config, owner)`) and
stop asking (`release(owner)`); they never turn it off, because more than one
owner exists — the visible activity, and the external-camera foreground
service that outlives it. What runs is the union of live claims.

Three exceptions, all narrow, all stated at their call site:

- **Diagnostics** — the Stats dialog's liveness line, the geo debug readout.
  These ask *is the hardware alive*, which the state cannot answer by
  construction: a frozen sample and a still phone look identical in it.
  Nothing a photo records may come from here.
- **The writer adapter** — `MapSensorController` subscribes to the engine to
  turn samples into funnel calls. That is what a writer is.
- **The device-pose sensor** — a different question and a different sensor;
  see "The device pose is its own state" below.

## What went wrong when this was violated

Each of these cost a debugging session, and each is the same mistake:

- The capture pane kept its own subscription for the stamped **pitch** and the
  magnetometer accuracy while taking the bearing from the state — so a
  photo's heading and pitch came from two different instants, and under a
  manual claim or car mode they described different things entirely.
- The external-camera pane printed the engine's **raw heading** beside the
  elected one. Two numbers, both called "the compass", disagreeing in
  public — which is what made "the compass is stuck in capture but fine in
  external" a mystery for a morning rather than a sentence.
- `MapScreen` kept its own copies of the tracking intents and mirrored them
  back to `MapSession`, so one intent had two homes and either could win.
- `TrackingPhase` lived in one screen's composition, so "want ON, phase
  Error" — a diagnosis — was invisible to everything else.
- The external-camera service configured the engine **Off** on the way out
  while MainScreen was configuring capture on the way in. Whoever went second
  won, so the capture pane's compass worked or did not, at random.
- The capture pane's **`hasFix`** was a boolean computed once, at the
  instant a fix arrived, and never asked again — while the overlay's stale
  warning derived the same question live from `fixAtMs` and a clock. Two
  answers to "is there a fresh fix", disagreeing in public: the warning
  counted the fix's age up past a minute while the gate and the no-fix offer
  still read it as fresh. So the offer built for losing signal could never
  appear once signal was lost. This is the pitch bug in the time dimension:
  a stored value derived from a timestamp is a copy of the state at an
  instant, and a copy is a second state. (Found 2026-09-09 by a test that
  believed the doc; see "Derived, not stored".)

## The position side: two records, one claim

Position is two records in the state, each a position and the time it was
set:

- **`lastFix`** — the receiver's latest. Session-scoped: a measurement does
  not survive a relaunch, because its age would be a day and its `gps` word
  a lie. Carries `elapsedRealtimeNanos`, which is what the stamp's age is
  measured against.
- **`lastPan`** — the map centre, and when a person last put it there.
  Persisted, as the map is.

And one bit of intent, the claim (`MapSession.manualPositionClaimed`): the
user has said the map centre is where they are, overriding the fix. The
original swaps the streams the moment the map is panned; frontend2 swaps only on the claim. Panning by itself is
exploration and changes nothing a photo records — *while there is a fix to
record*. When there is no fix, the map centre is not an alternative, it is
the only position there is, and it is what a photo records. Nothing is
refused, and nothing decides freshness for the user: the age is on the
stamp and downstream filters on it (see "Derived, not stored").

The stamp picks by this table and nothing else. `altLocationFor` is the
rule; the other record rides along as `alt_location` — the original's
field, same JSON, synthesized by the backend into the UserComment
provenance — so a reviewer can promote it later:

| `lastFix` | `lastPan` | claimed | primary | `alt_location` |
| --- | --- | --- | --- | --- |
| yes | any | no | fix, `gps` | pan, if exploring |
| yes | yes | yes | pan, `map` | fix |
| no | yes | — | pan, `map` | none |
| no | no | — | none — `null`, and meant | none |

Two words, `gps` and `map`, which is the original's contract exactly. The
row says the rest: a `map` primary with a fix in `alt_location` is a
confirmed override; a `map` primary with none is the map standing in for a
receiver that has said nothing this session. The last row is the doc's own
null rule applied to position — a writer with no value writes `null` and
means it — and it is the ONLY case with no position: a blank first run
before any fix or pan. (`alt_location`'s own source words, `gps-background`
and `map-unclaimed`, are the backend's existing shape and stay.)

The capture pane reads the two records, `exploring` and the claim as
mirrors of the state, exactly as it reads the bearing. It samples no stream
of its own and decides nothing; the shutter's only gate is camera readiness.

**Status (decided 2026-09-09; readers not yet moved).** Today one
`SpatialState` holds one position with a `source` and `ts`, the fix
overwrites it in following mode and a pan overwrites it otherwise, so
neither record is recoverable once the other has written — which is why the
capture pane keeps a private `lastLocation`, the allowlisted "second
stream" in `OneStateArchitectureTest`. Under this section that subscription
goes: `lastFix` lives in the state, the allowlist entry shrinks to the Stats
liveness line and the device-pose sensor, and the doc's "three exceptions"
become the truth again. Still embodying the old shape: `shutterEnabled`
(gates on `hasFix`), the no-fix offer in `CaptureScreen` (offered on
`!hasFix`; under this rule there is no hatch, the claim is the only
button), `MapSession.mapPositionWithoutFix` (the hatch's flag — deleted),
the snapshot's position selection in `PhotoCapture.android.kt`, the
`manual` word it writes, and the upload pipeline's `?: 0.0` for a null
coordinate, which the last row makes reachable on purpose and which must
therefore carry `null` honestly. The tracking tables' `manual` is a
separate vocabulary (beside `android`, `gps-kalman`) that pics reads; it is
not touched by this.

## Derived, not stored

This page is mostly about WHERE a value comes from. `hasFix` was about WHEN
a value is true, and the rule is the same: a boolean derived from a
timestamp and then stored is a copy of the state at one instant, and every
reader of the copy is reading a second state, displaced in time instead of
in source.

So freshness is derived at read, never stored. `fixAtMs` (and the
monotonic `elapsedRealtimeNanos` the stamp needs) live in the state; "is it
fresh" is a function of them and a clock, computed by whoever asks, with
ONE definition. The overlay's `staleFixWarning(fixAtMs, nowMs, …)` is that
function's shape. Anything that wants to know "have we ever had a fix" may
keep a boolean, because that question has no time in it.

Freshness and accuracy INFORM — the pill, the warning, the readout — and
never refuse. Both are recorded on the stamp (`location_age_ms`, the EXIF
positioning error, the upload metadata), which is what makes refusing
unnecessary: downstream can filter on a number the app would otherwise have
had to guess a threshold for.

## "In front" has one computation

The PICK is one state — a tapped or navigated-to photo rides in
`bearing.photoUid`, written through the funnel like everything else — and
the ANSWER "which photo is in front" has one computation: the viewer's
derivation (`deriveViewerState`). The map's enlarged marker is a READER of
it (`MapScreen` collects the holder's `front` while the view activity is
up), not a second computation; the map's own copy of the rule
(`frontPhoto`) is deleted. Outside the view activity both are dark — the
viewer by WhileSubscribed, the marker styling by the original's capture
gate — so the map's collector doubles as the subscription switch.

One consequence, deliberate: the enlarged marker now obeys the same hunter
and filter rules the viewer does, because it IS the viewer's answer. A
marker the viewer would not front no longer enlarges.

## The device pose is its own state

"Which way am I facing" and "which way up is the phone" are different
questions, and the original keeps them in different stores —
`mapState.ts` for the first, `deviceOrientationExif.ts` for the second. This
port does the same, and for the reason that matters here: a pose is not a
heading, and folding it into `bearing` would put portrait-vs-landscape into
the bearing election.

The rule it does share is the one this page is about. The pose has ONE home,
`DevicePoseState`, and ONE writer: the capture engine's
`MyDeviceOrientationSensor`, which exists because CameraX has to be told
where "up" is. Everything else reads it — the JPEG's orientation, and the
floating camera button, whose icon turns so it stays upright in the world and
thereby shows the orientation the next photo will be understood to have
(the original: "icon rotates with `relativeOrientationExif`").

The second input is the DISPLAY's own rotation (`rememberScreenAngleDeg`, the
original's `screenOrientationAngle`). The two turn in opposite senses, so
under auto-rotate they cancel and the icon sits still; under a rotation lock —
the normal state for someone out shooting — the icon is the only thing that
moves. `devicePoseUiRotation` is that subtraction, and it is checked against
every row of the original's table.

`null` means nothing is sensing the pose, because the sensor runs only while
the camera is bound. That is the original's shape too: it mounts the listener
with the camera view and resets the store on unmount.

## Auditing it

These greps are the whole audit. Each should return only the boundary and the
documented exceptions:

```bash
# reads of raw hardware outside the engine
grep -rn "GeoEngine.get(\|\.orientation\.collect\|\.location\.collect" \
    frontend2/shared/src --include=*.kt | grep -v geo/GeoEngine.kt

# a second device-pose listener (the one home is DevicePoseState)
grep -rn "OrientationEventListener\|MyDeviceOrientationSensor(" \
    frontend2/shared/src --include=*.kt

# writers — every one must be a funnel call
grep -rn "updateBearing(\|updateSpatial(" frontend2/shared/src --include=*.kt
```

`OneStateArchitectureTest` runs the first two as a test, so a new side
channel fails the build rather than waiting to become a bug report. It greps
the source with comments and string literals blanked out (`kotlinCodeOnly`),
which is what lets a rule be explained in the file it governs.
