# Test: Picks survive rapid panning (chase-the-marker)

## What we're testing

When the user pans the map, each pan triggers an area reload from the backend. The currently selected photo (the "pick") must survive these reloads even when `maxPhotosInArea` limits how many photos the backend returns.

The fix (`await tick()` in `spatialState.subscribe` in `simplePhotoWorker.ts`) ensures `picksUpdated` is posted to the worker before `areaUpdated`, so the worker's main loop drains both messages and has current picks before starting the backend fetch.

## Test design

1. Seed many photos (e.g. 100 via `upload_random_photos` or a new debug endpoint).
2. Set `maxPhotosInArea` to 2 via localStorage.
3. Zoom in so that ~5 photos would be in view if there were no limit.
4. Pan to the first visible marker. It becomes the front photo (pick).
5. Loop:
   - Find a marker that is currently visible but is NOT the current pick.
   - Record its photo ID and coordinates.
   - Pan the map to that marker's coordinates.
   - Wait for the area reload to complete.
   - **Assertion**: if the marker was visible right before we panned, it must still be visible after the reload (it should have become a pick when we panned to it).
   - If a marker wasn't visible before panning, we don't require it to be visible after.
6. Repeat for N iterations (e.g. 20).

## Why this catches the race

Without `await tick()`, rapid panning can cause `areaUpdated` to arrive at the worker before `picksUpdated`. The worker starts the backend fetch without the current pick, and the backend (constrained by `maxPhotosInArea=2`) may not return it. The photo disappears from the map.

With `await tick()`, the picks store flushes first, `picksUpdated` is posted before `areaUpdated`, and the worker's main loop (which drains all queued messages before starting processes) always has current picks.

## Implementation notes

- Need a fast way to seed many photos from Playwright. Options:
  - Add a `/api/debug/seed-photos` endpoint that creates photos with geometry directly in DB (no image upload/processing needed — just needs `geometry`, `processing_status='completed'`, `is_public=true`, `owner_id`, `compass_angle`).
  - Call `backend/tests/utils/debug_utils.py upload_random_photos` via subprocess.
  - Use `uploadPhoto` helper for a smaller count (slower but works today).
- The test photo coordinates should be spread out enough that panning between them triggers distinct area reloads, but close enough to be visible at the same zoom level.
- Use `page.evaluate` to read marker coordinates from `data-photo-id` elements and their Leaflet positions for programmatic panning.
