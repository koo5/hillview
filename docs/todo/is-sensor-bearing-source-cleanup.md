# Clean up is_sensor_bearing_source hack

## Current state

`device_photos.rs` has a `is_sensor_bearing_source()` function that decides whether to look up the bearing from the Kotlin database (high-frequency sensor path) or use the frontend-provided bearing directly.

It works by keyword-matching on the `bearing_source` string:
```rust
source_lower.contains("sensor")
    || source_lower.contains("compass")
    || source_lower.contains("tauri")
    // ... etc
```

## Why it exists

The Kotlin DB shortcut avoids the Kotlin → frontend → Kotlin round-trip for compass bearings. Without it, the frontend would always attach a stale bearing to captured photos, because compass updates are high-frequency and the JS bridge adds latency. The Kotlin side stores compass readings directly and can look up the closest-in-time bearing for a given capture timestamp.

## Problems

- Fragile keyword matching — adding a new bearing source requires updating this string list
- Car mode (`gps-kalman` source) doesn't need the shortcut because GPS heading updates are infrequent enough that the frontend value is current. But the distinction is implicit and non-obvious.
- The function name implies a clean sensor vs. non-sensor distinction, but the actual logic is "does the Kotlin DB have high-frequency samples for this source?"

## Possible improvements

- Make the contract explicit: the Kotlin DB stores samples tagged with their source, so `determine_final_bearing` could check whether the DB actually has recent samples for the given source, rather than guessing from the source name.
- Or: have each bearing source declare at registration time whether it feeds the Kotlin DB, removing the need for string matching entirely.

## Relevant files

- `frontend/src-tauri/src/device_photos.rs` — `is_sensor_bearing_source()`, `determine_final_bearing()`
- `frontend/src/lib/mapState.ts` — `updateBearing()`, `updateBearingByDiff()` (sends to Kotlin via `update_orientation`)
- `frontend/src/lib/gpsOrientation.svelte.ts` — car mode uses source `'gps-kalman'`
- `frontend/src/lib/compass.svelte.ts` — walking mode uses sources like `'tauri-compass-true'`
