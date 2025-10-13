package cz.hillview.plugin

import android.content.Context
import android.util.Log
import kotlinx.coroutines.*

/**
 * Photo Operations - Pure Business Logic
 *
 * Faithful translation of photoOperations.ts from TypeScript to Kotlin.
 * Handles the actual photo loading and processing operations.
 */
class PhotoOperations(private val context: Context) {
    companion object {
        private const val TAG = "PhotoOperations"
    }

    private val deviceLoader = DevicePhotoLoader(context)
    private val streamLoader = StreamPhotoLoader()
    private val sourceCache = mutableMapOf<String, SourceCache>()
    private var maxPhotosInArea: Int = 200

    /**
     * Source cache for each source - matches TypeScript interface
     */
    private data class SourceCache(
        val photos: List<PhotoData>,
        val isComplete: Boolean, // true = no more photos available, false = partial load
        val cachedBounds: Bounds? = null // The geographic bounds that were completely cached
    )

    fun setMaxPhotosInArea(maxPhotos: Int) {
        maxPhotosInArea = maxPhotos
    }

    /**
     * Process config update - translation of processConfig from photoOperations.ts
     */
    suspend fun processConfig(
        processId: String,
        messageId: Int,
        config: ConfigData,
        shouldAbort: () -> Boolean,
        authTokenProvider: suspend () -> String?
    ): List<PhotoData> {
        Log.d(TAG, "PhotoOperations: Processing config update ($processId)")

        if (shouldAbort()) return emptyList()

        if (config.sources.isEmpty()) {
            Log.d(TAG, "PhotoOperations: PROCESSCONFIG: No sources in config ($processId)")
            return emptyList()
        }

        val sources = config.sources
        val allLoadedPhotos = mutableListOf<PhotoData>()

        // Get enabled sources
        val enabledSources = sources.filter { it.enabled }
        val enabledSourceIds = enabledSources.map { it.id }.toSet()

        Log.d(TAG, "PhotoOperations: PROCESSCONFIG: enabledSourceIds: ${enabledSourceIds.joinToString(", ")}")

        // Clear cache for disabled sources
        val sourcesToRemove = sourceCache.keys.filter { !enabledSourceIds.contains(it) }
        sourcesToRemove.forEach { sourceCache.remove(it) }

        // Process each enabled source
        for (source in enabledSources) {
            if (shouldAbort()) break

            try {
                Log.d(TAG, "PhotoOperations: Processing source ${source.id} of type ${source.type}")

                val photos = when (source.type) {
                    "device" -> {
                        deviceLoader.loadPhotos(source, null, maxPhotosInArea, shouldAbort)
                    }
                    "stream" -> {
                        val authToken = authTokenProvider()
                        streamLoader.loadPhotos(source, null, maxPhotosInArea, authToken, shouldAbort)
                    }
                    else -> {
                        Log.w(TAG, "PhotoOperations: Unknown source type: ${source.type}")
                        emptyList()
                    }
                }

                if (!shouldAbort()) {
                    allLoadedPhotos.addAll(photos)

                    // Cache the loaded photos
                    sourceCache[source.id] = SourceCache(
                        photos = photos,
                        isComplete = true, // For config processing, we consider this complete
                        cachedBounds = null
                    )

                    Log.d(TAG, "PhotoOperations: Loaded ${photos.size} photos from source ${source.id}")
                }

            } catch (error: Exception) {
                Log.e(TAG, "PhotoOperations: Error loading source ${source.id}: ${error.message}", error)
                // Continue with other sources
            }
        }

        Log.d(TAG, "PhotoOperations: PROCESSCONFIG: Config processing complete ($processId) - loaded ${allLoadedPhotos.size} photos")
        return allLoadedPhotos
    }

    /**
     * Process area update - translation of processArea from photoOperations.ts
     */
    suspend fun processArea(
        processId: String,
        sources: List<SourceConfig>,
        bounds: Bounds,
        shouldAbort: () -> Boolean,
        authTokenProvider: suspend () -> String?,
        onSourceLoadingStatus: ((sourceId: String, isLoading: Boolean, progress: String?, error: String?) -> Unit)? = null
    ): Map<String, List<PhotoData>> {
        Log.d(TAG, "PhotoOperations: Processing area update ($processId) with ${sources.size} sources")

        val sourcesPhotosInArea = mutableMapOf<String, List<PhotoData>>()

        for (source in sources.filter { it.enabled }) {
            if (shouldAbort()) break

            try {
                // Send loading status for this individual source
                onSourceLoadingStatus?.invoke(source.id, true, "Loading photos...", null)

                Log.d(TAG, "PhotoOperations: Processing area for source ${source.id}")

                // Check if we have cached data that covers this area
                val cache = sourceCache[source.id]
                val canUseCache = cache != null && cache.isComplete &&
                    cache.cachedBounds?.let { isAreaWithinCachedBounds(bounds, it) } == true

                val photos = if (canUseCache) {
                    Log.d(TAG, "PhotoOperations: Using cached data for ${source.id}")
                    filterPhotosByArea(cache!!.photos, bounds)
                } else {
                    Log.d(TAG, "PhotoOperations: No cache for ${source.id}, performing bounded load")

                    when (source.type) {
                        "device" -> {
                            deviceLoader.loadPhotos(source, bounds, maxPhotosInArea, shouldAbort)
                        }
                        "stream" -> {
                            val authToken = authTokenProvider()
                            streamLoader.loadPhotos(source, bounds, maxPhotosInArea, authToken, shouldAbort)
                        }
                        else -> {
                            Log.w(TAG, "PhotoOperations: Unknown source type: ${source.type}")
                            emptyList()
                        }
                    }
                }

                if (!shouldAbort()) {
                    sourcesPhotosInArea[source.id] = photos
                    Log.d(TAG, "PhotoOperations: Area load complete for ${source.id}: ${photos.size} photos")

                    // Send completion status for this individual source
                    onSourceLoadingStatus?.invoke(source.id, false, "Loaded ${photos.size} photos", null)
                }

            } catch (error: Exception) {
                Log.e(TAG, "PhotoOperations: Error loading source ${source.id}: ${error.message}", error)

                // Send error status for this individual source
                onSourceLoadingStatus?.invoke(source.id, false, null, "Error: ${error.message}")

                // Continue with other sources
            }
        }

        Log.d(TAG, "PhotoOperations: Area processing complete ($processId) - ${sourcesPhotosInArea.values.sumOf { it.size }} photos in area")
        return sourcesPhotosInArea
    }

    /**
     * Check if requested bounds is completely contained within cached bounds
     * Translation from photoOperations.ts
     */
    private fun isAreaWithinCachedBounds(requestedBounds: Bounds, cachedBounds: Bounds): Boolean {
        return requestedBounds.top_left.lat <= cachedBounds.top_left.lat &&
               requestedBounds.top_left.lng >= cachedBounds.top_left.lng &&
               requestedBounds.bottom_right.lat >= cachedBounds.bottom_right.lat &&
               requestedBounds.bottom_right.lng <= cachedBounds.bottom_right.lng
    }

    /**
     * Filter photos by area bounds
     * Translation from workerUtils.ts filterPhotosByArea
     */
    private fun filterPhotosByArea(photos: List<PhotoData>, bounds: Bounds): List<PhotoData> {
        return photos.filter { photo ->
            photo.coord.lat <= bounds.top_left.lat &&
            photo.coord.lat >= bounds.bottom_right.lat &&
            photo.coord.lng >= bounds.top_left.lng &&
            photo.coord.lng <= bounds.bottom_right.lng
        }
    }

    /**
     * Clean up all resources
     */
    fun cleanup() {
        Log.d(TAG, "PhotoOperations: Cleaning up all resources")
        sourceCache.clear()
    }
}
