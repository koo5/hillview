# The single position/bearing stream — how Tauri does it, what frontend2 must do

Design note for concern **C1/C2** in `frontend2-status.md`. Written after
reading the original rather than reasoning from memory, because the port
had drifted into three parallel data paths and the drift was invisible
from the inside.

The user's statement of the requirement:

> the user controls a single pos/bearing stream. that's the one the user
> influences, the one that initial stamping reads, the one (conceptually)
> that the interpolator uses, the one that map (usually) shows, the one
> that the foreground service writes, the one that goes into room tables,
> the one that's dumped into csvs. not literally, but conceptually, the
> user has one value pair to deal with. **maybe it's not as simple as I
> make it sound.**

It is not, quite — and the "not literally" is load-bearing. The original
resolves it with **one value pair, two materializations, and an explicit
rule for which one wins per source.** All three parts are needed.

## What the Tauri app actually does

### 1. One hardware owner, fanning out from one callback

`ExamplePlugin` holds exactly ONE `EnhancedSensorService` and ONE
`PreciseLocationService` (both `if (x == null)`-guarded singletons,
started/stopped by JS commands). The JS layer never touches hardware — it
*cannot*, the process boundary forbids it.

Each sensor sample, in a single callback (`ExamplePlugin.kt:723`):

```
onSensorUpdate = { sensorData ->
    trigger("sensor-data", data)                          // → the state
    geoTrackingManager.storeOrientationSensorData(data)   // → the table
}
```

Each location fix, in a single callback (`ExamplePlugin.kt:820`):

```
sensorService?.updateLocation(lat, lng)                   // declination feed
geoTrackingManager.storeLocationPreciseLocationData(d)    // → the table
val kalman = geoTrackingManager.feedLocationForHeadingFilter(d)
if (kalman != null) trigger("gps-kalman-bearing", …)      // → the state
trigger("location-update", data)                          // → the state
```

Two things to notice. The table row and the JS event are **the same
sample emitted together**, so they cannot describe different worlds. And
the **car-mode Kalman bearing is derived right here**, in the plugin, on
the location service's callback — *not* in the map component.

### 2. One state pair, one write funnel

`spatialState` + `bearingState` (`mapState.ts:50,60`) are the pair the
user deals with. Every writer — GPS, compass, map pan, arrow drag, URL,
photo navigation, car mode — goes through `updateSpatialState()` or
`updateBearing()`. Those two functions do three jobs at once:

1. update the state;
2. push the ELECTION when it changes — *"whoever wrote the bearing last
   IS the elected source… a stream that has produced no reading has not
   called this function, so it cannot have been elected"*;
3. write the tracking-table row — **but only for sources Kotlin does not
   already own** (`kotlinOwnsSource`), since an echo of a high-rate
   stream would file a second row for a sample already recorded.

Because the row write is a *side effect of the state write*, the state
and the table cannot disagree about a user-set value. There is no
ordering hazard to manage: the pan row carries its own election because
one function does both.

### 3. Two materializations, and the rule for which wins

This is the part that is "not literal". The single conceptual stream
exists in two forms:

| | fidelity | role |
|---|---|---|
| **state pair** | UI rate, stale by bridge latency | what the user sees, influences, and what a LIVE capture stamps from |
| **tracking tables** | full sensor rate, time-indexed | the authoritative record; what retroactive pairing and the CSVs read |

Which is authoritative depends on the source, and the rule is written
down twice on purpose — `kotlinOwnsSource()` in `mapState.ts` and
`is_sensor_bearing_source()` in `device_photos.rs`, explicitly declared
one invariant that must move together:

- **Kotlin-owned** (`android*`, `gps-kalman`): the table wins. The
  frontend value crossed a bridge and is stale; the table has the sample
  at its own timestamp.
- **User-set** (map, arrow_drag, url, featured, photo_navigation): the
  frontend value IS the answer — and it is in the table too, because
  `updateBearing` put it there in the same call.

So: live capture stamps the state; retroactive pairing reads the table;
the interpolator is the bridge between them, improving a state-stamped
photo from the table's higher-fidelity record. That is why "conceptually
the interpolator uses the same stream" is true even though it physically
reads a different store.

### 4. The vocabulary split that makes the election a plain equality

`bearingState.source` is fine-grained (`map`, `arrow_drag`,
`android-compass-true`, …) because the UI and the EXIF `bearing_source`
want that detail. `toTableSource()` collapses it to the coarse elect-able
vocabulary (`android` | `gps-kalman` | `manual`) **only at the boundary
where a row is persisted**, so "re-query for the elected source" stays
`sourceId = electedSourceId` instead of a lookup table.

## What frontend2 did instead, and why it happened

frontend2 has the state pair (`MapStateHolder.spatial` / `.bearing`,
already process-wide) — but not the other two parts:

- **Three hardware owners.** `EnhancedSensorService` is constructed in
  `MapScreen.android.kt:785`, `PhotoCapture.android.kt:320` and
  `ExternalCameraService.kt:94`; `PreciseLocationService` in the same
  three files. Tauri has one of each.
- **Table writes are NOT side effects of the state write.** Capture
  writes rows from its own sensor callbacks; the external service writes
  rows from its own; the map writes the *state* but not rows. So three
  independent streams reach the tables, and only one of them also feeds
  the value the app stamps with.
- **Car-mode derivation sits in the map component** — every
  `state.updateBearing(...)` in frontend2 is inside
  `MapScreen.android.kt`, so the Kalman composition rides the UI thread,
  behind marker rendering. Tauri derives it in the plugin callback.

**Why it happened, and the lesson:** in Tauri the plugin boundary was
doing architectural work for free. "Kotlin owns hardware, JS owns state"
is not a convention there, it is a wall — JS *cannot* open a sensor. In
CMP everything is Kotlin in one process, the wall is gone, and nothing
stops a pane from constructing its own `EnhancedSensorService`. Three
times, nothing did. The symptom the user saw from the outside — *"the
external camera page shows some compass feed"* — is exactly this: a
third instance rendering its own numbers, which can differ from the
number the app would stamp at that instant.

> Port the *constraints* the original's structure enforced, not only the
> behaviour it produced. A boundary that is impossible to cross in the
> source architecture becomes a discipline that must be made explicit in
> the target one.

## The shape frontend2 needs

**A `GeoEngine`: one process-wide object, the CMP analog of
ExamplePlugin's hardware half.**

- Owns the single `EnhancedSensorService` and single
  `PreciseLocationService`. Starts/stops by reference count or mode, not
  by whoever composed last.
- Runs its callbacks off the UI thread, and does there exactly what the
  plugin does: write the table at full rate, feed declination, derive the
  Kalman car bearing, publish samples as flows. **This alone fixes C2** —
  bearing derivation stops sharing a thread with marker rendering.
- Publishes flows; owns no policy.

**`MapStateHolder` becomes the single write funnel**, the analog of
`updateSpatialState`/`updateBearing`: state update + election push +
table echo for non-engine-owned sources, all inside the one call. Those
side effects live in `MapScreen.android.kt` today and move here.

**Every pane becomes a pure observer.** Map renders the state; capture
stamps the state (already does, via `stampBearing`) and drops its own
sensor/location instances; the external pane displays the state instead
of its own feed.

**The foreground service hosts the engine instead of duplicating it.**
External mode then means "keep the engine alive with a notification while
another app is in front" — a *lifetime* concern, not a data one. That is
the correct reading of the user's *"nice if we can synchronize the UI
with the live data, while also having the foreground service
active/available for when the app is backgrounded"*: one engine, one
state pair, a service that owns the process rather than a second copy of
the data path.

**C4 falls out.** Per-mode sensor/GPS rates become a property of the one
engine (`engine.setProfile(External | Capture | Gallery)`) — which is why
per-mode defaults were blocked on this: today there is no single place a
rate could even be set.

**What this does NOT fix: C3.** The refiner/upload claim race is a
separate defect (the drain claims a row in two steps). But the engine
does remove the ambiguity underneath it — with one writer, "the table
holds the same stream the stamp came from" becomes structurally true
rather than coincidentally true.

## Open questions for the review session

1. **Engine lifetime.** Ref-counted by observers, or explicitly driven by
   the active mode? Tauri sidesteps this: JS issues explicit
   start/stopSensor commands. A ref count is more automatic but makes
   "who is keeping the GPS awake" harder to answer — which matters for a
   battery-sensitive app.
2. **Does the capture pane still need its own location read?** Today it
   keeps `lastLocation` for the stamp and the fix-age. As an observer it
   would read the engine's latest sample — equivalent, but the fix-age
   arithmetic (`elapsedRealtimeNanos`) must survive the hop.
3. **Should the state funnel live in commonMain?** `MapStateHolder` is
   commonMain; the table echo is Android-only. Probably a seam
   (`TrackingSink`) that is a no-op on desktop, keeping the funnel itself
   testable in `jvmTest` where the rules belong.
4. **Migration order.** Extracting the engine while three owners exist is
   the risky step. Safest sequence is probably: engine created and owning
   the sensors → map observes it (kills the UI-thread derivation) →
   capture observes it → external service hosts it, its own instances
   deleted last, since that pane is newest and least load-bearing.
