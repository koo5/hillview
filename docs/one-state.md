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
ring and its neighbours, the external-camera pane, the marker fade. All of
them read the state. None of them samples hardware to answer a question the
state already answers.

## The hardware boundary

`GeoEngine` owns every registration — sensors and fixes — and publishes
samples. It is the ONLY component that talks to `SensorManager` or the fused
location provider. Its samples reach the app in exactly one way: a writer
turns them into `updateBearing` / `updateSpatial` calls.

Owners ASK the engine for what they need (`configure(config, owner)`) and
stop asking (`release(owner)`); they never turn it off, because more than one
owner exists — the visible activity, and the external-camera foreground
service that outlives it. What runs is the union of live claims.

Two exceptions, both narrow, both stated at their call site:

- **Diagnostics** — the Stats dialog's liveness line, the geo debug readout.
  These ask *is the hardware alive*, which the state cannot answer by
  construction: a frozen sample and a still phone look identical in it.
  Nothing a photo records may come from here.
- **The writer adapter** — `MapSensorController` subscribes to the engine to
  turn samples into funnel calls. That is what a writer is.

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

## The position side: two streams, castled on confirmation

Position has two streams — the receiver's fix and the map's centre — and a
photo records ONE of them as primary. The original swaps them (the user's
word: castles them) the moment the map is panned; frontend2 swaps them only
when the pan is CONFIRMED, through the pill's accepted claim or the no-fix
hatch (`MapSession.manualPositionElected`). Panning by itself is
exploration and changes nothing a photo records.

Whichever stream is not primary rides along as `alt_location` — the
original's field, same JSON, synthesized by the backend into the UserComment
provenance — so a reviewer can promote it later. `altLocationFor` is the
rule:

| state | primary | `alt_location` |
| --- | --- | --- |
| following (map = fix) | fix, `gps` | none — one stream |
| exploring, prompt up, unclaimed | fix, `gps` | map centre, `map-unclaimed` |
| claimed | map centre, `manual` | live fix, `gps-background` |
| no-fix hatch | map centre, `manual` | none — no fix exists |

The claimed row is the original's exact case. The unclaimed row is one the
original never has (it would already have swapped), and the rule extends to
it symmetrically, tagged so nobody mistakes an unconfirmed pan for a
measurement. The capture pane reads `exploring` and `manualLocationElected`
as mirrors of session state, exactly as it reads the bearing — it samples
no stream of its own.

## Auditing it

These greps are the whole audit. Both should return only the boundary and the
two documented exceptions:

```bash
# reads of raw hardware outside the engine
grep -rn "GeoEngine.get(\|\.orientation\.collect\|\.location\.collect" \
    frontend2/shared/src --include=*.kt | grep -v geo/GeoEngine.kt

# writers — every one must be a funnel call
grep -rn "updateBearing(\|updateSpatial(" frontend2/shared/src --include=*.kt
```

`OneStateArchitectureTest` runs the first of these as a test, so a new side
channel fails the build rather than waiting to become a bug report.
