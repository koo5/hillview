# Replace PhotoData with minimal struct + raw JsonObject passthrough

The Kotlin photo worker only needs a few fields for spatial culling and dedup:
- `coord`, `bearing`, `uid`, `id`, `source`, `range_distance`, `fileHash`

Everything else (`featured`, `pyramid`, `sizes`, `creator`, `filename`, `url`, `captured_at`, `is_pano`, ...) is just passed through to the frontend unchanged.

Currently, every field must be threaded through three places:
1. `PhotoWorkerTypes.kt` — data class definition
2. `StreamPhotoLoader.kt` — manual extraction from backend JSON
3. `PhotoWorkerService.kt` — manual serialization back to frontend JSON

This has already caused bugs (`featured` and `pyramid` silently dropped on Android).

## Proposed approach

Keep a minimal typed struct for the fields Kotlin operates on. Carry the original `JsonObject` alongside it. On output, overlay the few fields Kotlin modifies (`uid`, `range_distance`) onto the original JSON and pass it through.

Adding a new backend field would then require zero Kotlin changes.
