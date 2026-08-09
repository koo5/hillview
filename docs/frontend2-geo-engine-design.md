# The single position/bearing stream — how Tauri does it, what frontend2 must do

**STATUS: implemented 2026-08-09.** `cz.hillview.geo.GeoEngine` is the one
owner; `MapStateHolder` is the funnel (election + row as side effects of the
state write, via `TrackingSink`); map, capture and the external pane are
observers; `BindGeoToActivity` in MainScreen is the single place that decides
when hardware runs and with what. Device-verified: engine start/stop per
activity with per-activity rates, one writer per table, elections flowing on
a map pan, a capture stamped and refined. What follows is the design and its
reasoning, kept because the reasoning is the valuable part.

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

**Terminology.** The panel-level concept is an **ACTIVITY** — the user's
word, and the code's (`MapSettings.mainActivity`, values `capture` /
`external` / `view`). This note said "mode" throughout its first draft;
that was drift, and "mode" is already the most overloaded word in this
codebase (`BearingMode` walking/car, `StorageMode`, eco mode, the sensor
fusion `MODE_*` constants). Where "activity" could be confused with
Android's `Activity` class, the Android one is named in full.

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

**Correction to an earlier claim in this note (measured 2026-08-09):**
the plugin's callbacks are NOT off the UI thread. `PreciseLocationService`
hardcodes `Looper.getMainLooper()` and `EnhancedSensorService` calls
`registerListener(this, sensor, SENSOR_DELAY)` with no handler — so in
BOTH apps the geo callbacks land on the Android main thread. The user's
worry is still exactly right, but the mechanism is the port, not the
plugin: in Tauri the map's drawing happens in the WebView's renderer
process, so however slow marker rendering gets it cannot hold up the
native main looper; in frontend2 osmdroid and Compose draw on that very
looper, so a heavy marker pass CAN delay a fix — and therefore delay the
value a capture stamps. The engine must therefore do better than the
original rather than merely copy it: it takes its own `HandlerThread`, so
geo is independent of UI work in a way neither app manages today. The
shared-kt services gain a caller-supplied looper/handler (defaulting to
main, so the Tauri app is byte-for-byte unaffected).

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
  `PreciseLocationService`. Starts/stops with the ACTIVITY (the app's own
  word: `mapSettings.mainActivity` — capture / external / view), not by
  whoever composed last.
- Runs its callbacks on its OWN `HandlerThread`, and does there exactly
  what the plugin does: write the table at full rate, feed declination,
  derive the Kalman car bearing, publish samples as flows. **This fixes
  C2** — and note it goes further than the original, which delivers on
  the main looper and gets away with it only because its map draws in
  another process (see the correction above).
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
The external-camera ACTIVITY then means "keep the engine alive with a notification while
another app is in front" — a *lifetime* concern, not a data one. That is
the correct reading of the user's *"nice if we can synchronize the UI
with the live data, while also having the foreground service
active/available for when the app is backgrounded"*: one engine, one
state pair, a service that owns the process rather than a second copy of
the data path.

**C4 falls out.** Per-activity sensor/GPS rates become a `GeoConfig`
passed at the call site that starts the engine for that activity (see
choice A) — which is why per-activity defaults were blocked on this: today there is no single
place a rate could even be set, and no single owner to apply it to. The
GPS interval slider and the eco sub-flags are then values in that config,
not new machinery.

**What this does NOT fix: C3.** The refiner/upload claim race is a
separate defect (the drain claims a row in two steps). But the engine
does remove the ambiguity underneath it — with one writer, "the table
holds the same stream the stamp came from" becomes structurally true
rather than coincidentally true.

## Open questions for the review session

1. **Engine lifetime.** Ref-counted by observers, or explicitly driven by
   the active activity? Tauri sidesteps this: JS issues explicit
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

## The choices, in code

The questions above were mostly mine to answer, not the user's. Recorded
here as concrete sketches so the decision is judged on what it LOOKS
like, with the recommendation stated. Class names are the real ones.

### A. Engine lifetime and rates — recommend A2 (the ACTIVITY drives WHEN, the caller supplies WHAT)

**A1, ref-counted.** Each observer acquires; the engine stops when the
last one releases.

```kotlin
class GeoEngine {
    private var holders = 0
    fun acquire(): Handle { if (holders++ == 0) startHardware(); return Handle { release() } }
    private fun release() { if (--holders == 0) stopHardware() }
}
// in a pane:
DisposableEffect(Unit) { val h = engine.acquire(); onDispose { h.close() } }
```

Automatic, and wrong for this app: nothing can answer *"why is the GPS
awake right now"* — the answer is a count. Battery behaviour becomes
emergent, which is precisely what a power-sensitive app must not have.

**A2, activity-driven, with the VALUES PASSED IN.** The user's correction,
and it is the right one: *"if it was up to me, I'd be setting these
values from wherever I'd be starting the engine."* The engine takes a
config; it does not own an enum of baked-in numbers.

```kotlin
data class GeoConfig(
    val sensors: Boolean,
    val sensorRateMs: Int,
    val locationIntervalMs: Long,
) {
    companion object { val Off = GeoConfig(sensors = false, sensorRateMs = 0, locationIntervalMs = 0) }
}

class GeoEngine(context: Context) {
    /** Retunes the ONE sensor/location pair. Off stops them. */
    fun configure(config: GeoConfig) { … }
}

// MainScreen, where the activity already lives (mapSettings.mainActivity).
// The numbers are HERE, at the call site, not inside the engine:
LaunchedEffect(activity, trackingWanted, mapSettings.gpsIntervalMs) {
    engine.configure(
        when (activity) {
            // Continuous: never a gap while another camera app is in front.
            "external" -> GeoConfig(sensors = true, sensorRateMs = 10,
                                    locationIntervalMs = mapSettings.gpsIntervalMs)
            // Optimize around the shutter (eco sub-flags land here).
            "capture"  -> GeoConfig(sensors = true, sensorRateMs = 10,
                                    locationIntervalMs = mapSettings.gpsIntervalMs)
            else       -> if (trackingWanted) {
                GeoConfig(sensors = true, sensorRateMs = 50, locationIntervalMs = 2_000)
            } else GeoConfig.Off
        }
    )
}
```

Two properties worth stating, because they are why this beats the enum:

- **The engine owns no policy.** It is told what to run; it never decides.
  Same rule as "publishes flows, owns no policy" above.
- **A user-facing control feeds it directly.** The GPS interval slider
  (item 0c) is `mapSettings.gpsIntervalMs` in the snippet above — already
  wired, because the value arrives from the call site. With rates frozen
  inside a `GeoProfile` enum, that slider would have needed the whole path
  re-plumbed. The eco sub-flags (sleep the bearing sensors until near
  capture time) are likewise just a different `GeoConfig` from the capture
  branch, not a new mechanism.

Defaults live next to their call sites (and, once the sliders exist, in
`MapSettings` so they persist). **This is C4**: per-activity rates now have a
place to live, and it is a place the user can reach.

### B. How a pane reads — recommend B2 (pure observer)

**B1, today.** The pane owns hardware and its own copy of the truth:

```kotlin
private val sensorService = EnhancedSensorService(context) { data ->
    lastOrientation = data
    geoTracking.storeOrientationSensorData(data)   // ← a third writer
}
```

**B2.** The pane observes; the engine already wrote the table:

```kotlin
LaunchedEffect(Unit) {
    engine.orientation.collect { lastOrientation = it }
}
```

The fix-age arithmetic must survive the hop — `locationAgeMs` is computed
from `elapsedRealtimeNanos`, so the engine publishes the `Location`
itself (or a sample carrying that nanos field), never a lat/lng pair.
That is the one detail that makes B2 a real port instead of a rewrite.

### C. The funnel's side effects — already commonMain, just incomplete

`MapStateHolder.updateBearing()` in `MapState.kt` ALREADY has
`mapState.ts`'s signature shape (source, photoUid, accuracyLevel,
setTimestamp). It is the funnel; it simply does not yet do the two things
the original does in the same call. They move in behind a seam, so the
rules stay testable in `jvmTest` and desktop stays a no-op:

```kotlin
/** The persist boundary (Android: rows + election; desktop: nothing). */
interface TrackingSink {
    fun electBearingSource(source: String)
    fun writeBearingRow(bearing: Double, source: String, detail: String, accuracyLevel: Int?, now: Long)
}

class MapStateHolder(private val sink: TrackingSink = NoopSink) {
    fun updateBearing(bearing: Double, source: String = "map", /* … */ now: Long) {
        _bearing.value = /* … as today … */
        val table = toTableSource(source)                     // android | gps-kalman | manual
        if (table.source != lastElected) {                    // push on change only
            lastElected = table.source
            sink.electBearingSource(table.source)
        }
        if (!engineOwnsSource(source)) {                      // == kotlinOwnsSource
            sink.writeBearingRow(bearing, table.source, table.detail, accuracyLevel, now)
        }
    }
}
```

`toTableSource` and `engineOwnsSource` are ports of the TS functions of
those names — and `mapState.test.ts` already pins their semantics, so the
Kotlin twins get the same tests.

### D. Where the foreground service sits — recommend D2 (host, don't duplicate)

**D1, today.** `ExternalCameraService` constructs its own sensor and
location services — a data path.

**D2.** The service owns *process lifetime*, the engine owns data:

```kotlin
class ExternalCameraService : Service() {
    override fun onStartCommand(…): Int {
        startForeground(NOTIFICATION_ID, notification, FOREGROUND_SERVICE_TYPE_LOCATION)
        GeoEngine.get(this).setProfile(GeoProfile.External)   // no hardware here
        return START_STICKY
    }
    override fun onDestroy() { GeoEngine.get(this).setProfile(GeoProfile.Off) }
}
```

The pane then shows `engine`/`MapStateHolder` state like every other
pane, and the "some compass feed" wart disappears by construction — there
is no second feed left to show.
