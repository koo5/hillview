# Photo sources: independent loading

Every map has several photo sources — device, hillview, mapillary, panoramax —
and three pipelines draw them: the Svelte web worker (`frontend/src/webworkers/
new.worker.ts`), the Tauri/Android Kotlin worker (`frontend/tauri-plugin-hillview/
android/.../PhotoWorkerService.kt`), and frontend2's `CompositeMarkerSource`.
All three used to load the sources one after another and publish the marker
set once, after the last one finished: time-to-first-marker was the *sum* of
every enabled source's latency, and one stalled stream blanked the map.

They now share one contract.

## The contract

1. **Every enabled source loads concurrently**, and each publishes as it
   lands — stream sources per SSE batch, device/panoramax on completion.
2. **The merged set is re-culled on every arrival** with `CullingGrid`
   semantics (10×10 viewport grid, per-cell round-robin across sources in
   priority order device < hillview < other < mapillary, md5 dedup, picks
   always kept, cap = "max photos"). Equal-priority sources tie-break on id,
   so the final set is a pure function of the per-source contents — **never of
   arrival order**. That is the answer to "first source wins vs. eviction":
   a late source takes its fair share of slots deterministically, and the map
   converges to the same picture however the network timed it.
3. **Publish policy**: the first arrival for a viewport publishes immediately
   (that is the time-to-first-marker); later arrivals are trailing-edge
   throttled at 300 ms (`PARTIAL_PUBLISH_THROTTLE_MS` /
   `CompositeMarkerSource.PUBLISH_THROTTLE_MS`); the final publish when every
   source has settled is never throttled. Publishes carry `complete`
   (false = partial, true = settled).
4. **Errors are isolated per source.** A failing source contributes nothing
   (web worker) or keeps its last good set (frontend2); it never blocks or
   blanks the others. A stream that goes silent is cut off by a watchdog
   (`STREAM_INACTIVITY_TIMEOUT_MS`, 60 s) instead of wedging the worker.
5. **A newer viewport supersedes the one still loading**: its loaders are
   cancelled, late batches from it are dropped (process id / generation),
   and what was already published stays on screen until the new data
   replaces it.
6. **The renderer diffs by photo uid** (`frontend/src/lib/markerDiff.ts`,
   `OptimizedMarkerSystem.updateMarkers`) instead of rebuilding every marker,
   so a late source arriving only touches the slots it takes.

Panoramax is on by default in both apps as a consequence: a slow or throttled
Panoramax no longer delays anyone else's markers.

## Where it lives

| | web worker | Tauri/Kotlin | frontend2 |
|---|---|---|---|
| concurrent loads | `photoOperations.ts` `processArea` | `PhotoOperations.kt` | `CompositeMarkerSource.refresh` (job per source) |
| per-source publish | `photosAdded` → `schedulePartialPublish` | `PhotoOperations.onSourcePhotos` → `PartialPublishGate` → `PhotoWorkerService.publishArea` | children's `markers` flows → conflated publish loop |
| cross-source cull | `CullingGrid.ts` | shared-kt `CullingGrid.kt` | `MarkerCuller` ← `SharedMarkerCuller` (shared-kt `CullingGrid.kt`) |
| per-batch streaming | `StreamSourceLoader` | shared-kt `StreamPhotoLoader.loadPhotos(onBatch=…)` | same, via `StreamMarkerSource` |
| settled signal | `photosUpdate.complete` | `photosUpdate.complete` + `generation` | `CompositeMarkerSource.loading` (empty = settled) |

`CullingGrid` has three hand-synced implementations (`CullingGrid.ts`, and
`shared-kt/CullingGrid.kt` compiled into both Android apps). Change the
semantics in all of them, and their tests (`CullingGrid.test.ts`,
`frontend2/.../androidHostTest/.../CullingGridTest.kt`).

## Testing it

- **Web worker**: `new.worker.test.ts` — `manual-…` sources never emit on
  their own; drive them with `emitPhotos` / `completeStream` / `failStream`.
  `sendMessage` resolves on the *settled* (`complete: true`) publish issued
  after the send; use `waitForUpdate(from, pred)` to catch partials.
  `streamInactivityTimeoutMs` in the config message shortens the watchdog.
- **Tauri/Kotlin**: plugin JVM tests (`bun run test:plugin-unit`; needs
  `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`, not the Android Studio JBR):
  `PhotoOperationsIncrementalTest` drives fake loaders through the injected
  `DeviceLoading`/`StreamLoading`/`PanoramaxLoading` seams;
  `PartialPublishGateTest` pins the throttle/settle policy. The main-thread
  relay (`KotlinPhotoWorker.test.ts`) checks several publishes per generation.
- **frontend2**: `CompositeMarkerSourceTest` — `FakeSource.refresh()` gated by
  a `CompletableDeferred`, so `runTest` virtual time controls per-source
  latency. The composite runs in `backgroundScope`; advance with
  `advanceTimeBy(THROTTLE + 1); runCurrent()`, not `advanceUntilIdle()`.
- **End to end** (`tests-playwright/sources-incremental.spec.ts`): the backend
  debug knob `POST /api/internal/debug/delays {"name": "hillview_stream" |
  "mapillary_stream", "seconds": N}` (helper `setDelay`) makes one stream slow
  *and still succeed* — unlike `armFault`, which always fails after its delay.
  Panoramax is fetched browser-side from the public instance, so
  `fixtures.ts` routes `api.panoramax.xyz/api/search` to an empty result for
  every test; a spec that wants photos registers its own route on top
  (`helpers/panoramaxMocks.ts`; later routes win). Marker source is on the
  inner element: `.optimized-photo-marker:has(.marker-container[data-source="…"])`.
