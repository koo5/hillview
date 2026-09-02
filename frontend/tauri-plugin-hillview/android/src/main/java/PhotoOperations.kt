package cz.hillview.plugin

import android.content.Context
import android.util.Log
import kotlinx.coroutines.*


/**
 * The three loaders behind the narrowest surface processArea/processConfig use.
 * PhotoOperations constructs the real ones by default; JVM unit tests hand in
 * fakes with controlled timing (see PhotoOperationsIncrementalTest).
 */
interface DeviceLoading {
    suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, picks: Set<String>): List<PhotoData>
}

interface StreamLoading {
    suspend fun load(
        source: SourceConfig, bounds: Bounds?, maxPhotos: Int, authToken: String?, shouldAbort: () -> Boolean,
        picks: Set<String>, queryOptionsJson: String?, onBatch: ((List<PhotoData>) -> Unit)?
    ): List<PhotoData>
}

interface PanoramaxLoading {
    suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, hillviewBackendUrl: String?, authToken: String?): List<PhotoData>
}

private class RealDeviceLoading(context: Context) : DeviceLoading {
    private val loader = DevicePhotoLoader(context)
    override suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, picks: Set<String>) =
        loader.loadPhotos(source, bounds, maxPhotos, shouldAbort, picks)
}

private class RealStreamLoading : StreamLoading {
    private val loader = StreamPhotoLoader()
    override suspend fun load(
        source: SourceConfig, bounds: Bounds?, maxPhotos: Int, authToken: String?, shouldAbort: () -> Boolean,
        picks: Set<String>, queryOptionsJson: String?, onBatch: ((List<PhotoData>) -> Unit)?
    ) = loader.loadPhotos(source, bounds, maxPhotos, authToken, shouldAbort, picks, queryOptionsJson, onBatch)
}

private class RealPanoramaxLoading : PanoramaxLoading {
    private val loader = PanoramaxPhotoLoader()
    override suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, hillviewBackendUrl: String?, authToken: String?) =
        loader.loadPhotos(source, bounds, maxPhotos, shouldAbort, hillviewBackendUrl, authToken)
}

/**
 * Photo Operations - Pure Business Logic
 *
 * Faithful translation of photoOperations.ts from TypeScript to Kotlin.
 * Handles the actual photo loading and processing operations.
 */
class PhotoOperations(
    private val context: Context,
    private val deviceLoader: DeviceLoading = RealDeviceLoading(context),
    private val streamLoader: StreamLoading = RealStreamLoading(),
    private val panoramaxLoader: PanoramaxLoading = RealPanoramaxLoading(),
    private val backendUrlProvider: () -> String? = { defaultHillviewBackendUrl(context) }
) {
    companion object {
        private const val TAG = "PhotoOperations"
        private const val doLog = false
        private const val MAX_PHOTOS_IN_AREA = 400  // Should match photoWorkerConstants.ts

        private fun defaultHillviewBackendUrl(context: Context): String? {
            // The frontend pushes its backend URL via set_backend_url (ExamplePlugin),
            // persisted to the shared "hillview_upload_prefs" prefs. Reused here so the
            // Panoramax loader can call /api/hidden/{photos,users} against it.
            return context
                .getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
                .getString("server_url", null)
        }
    }

    private fun hillviewBackendUrl(): String? = backendUrlProvider()
    private val sourceCache = mutableMapOf<String, SourceCache>()
    private var maxPhotosInArea: Int = MAX_PHOTOS_IN_AREA
    private var picks: Set<String> = emptySet()
    private var queryOptionsJson: String? = null  // Pre-serialized analysis filters

    /** Timestamp (System.currentTimeMillis()) recorded immediately before the most recent
     *  successful DevicePhotoLoader.loadPhotos() call. The frontend uses this to prune
     *  placeholder markers: if placeholder.savedAt < lastDeviceQueryStartedAt, the DB row
     *  was visible to the query, so the placeholder is redundant. */
    @Volatile
    var lastDeviceQueryStartedAt: Long? = null
        private set


    fun setPicks(newPicks: Set<String>) {
        picks = newPicks
    }

    fun setQueryOptionsJson(json: String?) {
        queryOptionsJson = json
    }

    /** Drop a single photo from the per-source cache so subsequent area loads
     *  don't resurrect it. Returns true if the photo existed. */
    fun removePhotoFromCache(photoId: String, sourceId: String): Boolean {
        val cache = sourceCache[sourceId] ?: return false
        val filtered = cache.photos.filterNot { it.id == photoId }
        if (filtered.size == cache.photos.size) return false
        sourceCache[sourceId] = cache.copy(photos = filtered)
        return true
    }

    /** Drop all photos by a given creator id from a source's cache. Returns the
     *  number of photos removed. */
    fun removeUserPhotosFromCache(userId: String, sourceId: String): Int {
        val cache = sourceCache[sourceId] ?: return 0
        val filtered = cache.photos.filterNot { it.creator?.id == userId }
        val removed = cache.photos.size - filtered.size
        if (removed > 0) sourceCache[sourceId] = cache.copy(photos = filtered)
        return removed
    }

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
        if (doLog) Log.d(TAG, "PhotoOperations: Processing config update ($processId)")

        if (shouldAbort()) return emptyList()

        if (config.sources.isEmpty()) {
            if (doLog) Log.d(TAG, "PhotoOperations: PROCESSCONFIG: No sources in config ($processId)")
            return emptyList()
        }

        val sources = config.sources
        val allLoadedPhotos = mutableListOf<PhotoData>()

        // Get enabled sources
        val enabledSources = sources.filter { it.enabled }
        val enabledSourceIds = enabledSources.map { it.id }.toSet()

        if (doLog) Log.d(TAG, "PhotoOperations: PROCESSCONFIG: enabledSourceIds: ${enabledSourceIds.joinToString(", ")}")

        // Clear cache for disabled sources
        val sourcesToRemove = sourceCache.keys.filter { !enabledSourceIds.contains(it) }
        sourcesToRemove.forEach { sourceCache.remove(it) }

        // Process each enabled source
        for (source in enabledSources) {
            if (shouldAbort()) break

            try {
                if (doLog) Log.d(TAG, "PhotoOperations: Processing source ${source.id} of type ${source.type}")

                // Extract picks for this specific source
                // picks contain UIDs like "hillview-abc123", we need to extract "abc123" for the backend
                val sourcePrefix = "${source.id}-"
                val sourcePickIds = picks
                    .filter { it.startsWith(sourcePrefix) }
                    .map { it.substring(sourcePrefix.length) }
                    .toSet()

                val photos = when (source.type) {
                    "device" -> {
                        val queryStart = System.currentTimeMillis()
                        val result = deviceLoader.load(source, null, maxPhotosInArea, shouldAbort, sourcePickIds)
                        lastDeviceQueryStartedAt = queryStart
                        result
                    }
                    "stream" -> {
                        val authToken = authTokenProvider()
                        streamLoader.load(source, null, maxPhotosInArea, authToken, shouldAbort, sourcePickIds, queryOptionsJson, null)
                    }
                    "panoramax" -> {
                        val authToken = authTokenProvider()
                        panoramaxLoader.load(source, null, maxPhotosInArea, shouldAbort, hillviewBackendUrl(), authToken)
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

                    if (doLog) Log.d(TAG, "PhotoOperations: Loaded ${photos.size} photos from source ${source.id}")
                }

            } catch (error: Exception) {
                Log.e(TAG, "PhotoOperations: Error loading source ${source.id}: ${error.message}", error)
                // Continue with other sources
            }
        }

        if (doLog) Log.d(TAG, "PhotoOperations: PROCESSCONFIG: Config processing complete ($processId) - loaded ${allLoadedPhotos.size} photos")
        return allLoadedPhotos
    }

    /**
     * Process area update - translation of processArea from photoOperations.ts
     *
     * Every enabled source loads concurrently (supervisor semantics: one
     * source failing or stalling never touches the others), and each one
     * reports through [onSourcePhotos] as it lands — stream sources on every
     * SSE batch (the accumulated list so far), every source once more on
     * completion — so the caller can put markers on the map per source
     * instead of after the slowest one. The returned map is the settled set.
     */
    suspend fun processArea(
        processId: String,
        sources: List<SourceConfig>,
        bounds: Bounds,
        shouldAbort: () -> Boolean,
        authTokenProvider: suspend () -> String?,
        onSourceLoadingStatus: ((sourceId: String, isLoading: Boolean, progress: String?, error: String?) -> Unit)? = null,
        onSourcePhotos: ((sourceId: String, photos: List<PhotoData>) -> Unit)? = null
    ): Map<String, List<PhotoData>> {
        if (doLog) Log.d(TAG, "PhotoOperations: Processing area update ($processId) with ${sources.size} sources")

        val sourcesPhotosInArea = java.util.concurrent.ConcurrentHashMap<String, List<PhotoData>>()

        supervisorScope {
            for (source in sources.filter { it.enabled }) {
                if (shouldAbort()) break

                launch {
                    try {
                        // Send loading status for this individual source
                        onSourceLoadingStatus?.invoke(source.id, true, "Loading photos...", null)

                        if (doLog) Log.d(TAG, "PhotoOperations: Processing area for source ${source.id}")

                        // Check if we have cached data that covers this area
                        val cache = sourceCache[source.id]
                        val canUseCache = cache != null && cache.isComplete &&
                            cache.cachedBounds?.let { isAreaWithinCachedBounds(bounds, it) } == true

                        // Extract picks for this specific source
                        // picks contain UIDs like "hillview-abc123", we need to extract "abc123" for the backend
                        val sourcePrefix = "${source.id}-"
                        val sourcePickIds = picks
                            .filter { it.startsWith(sourcePrefix) }
                            .map { it.substring(sourcePrefix.length) }
                            .toSet()

                        val photos = if (canUseCache) {
                            if (doLog) Log.d(TAG, "PhotoOperations: Using cached data for ${source.id}")
                            filterPhotosByArea(cache!!.photos, bounds)
                        } else {
                            if (doLog) Log.d(TAG, "PhotoOperations: No cache for ${source.id}, performing bounded load (picks: ${sourcePickIds.size})")

                            when (source.type) {
                                "device" -> {
                                    val queryStart = System.currentTimeMillis()
                                    val result = deviceLoader.load(source, bounds, maxPhotosInArea, shouldAbort, sourcePickIds)
                                    lastDeviceQueryStartedAt = queryStart
                                    result
                                }
                                "stream" -> {
                                    val authToken = authTokenProvider()
                                    streamLoader.load(source, bounds, maxPhotosInArea, authToken, shouldAbort, sourcePickIds, queryOptionsJson) { batch ->
                                        // A batch of a superseded area is nobody's news.
                                        if (!shouldAbort()) onSourcePhotos?.invoke(source.id, batch)
                                    }
                                }
                                "panoramax" -> {
                                    val authToken = authTokenProvider()
                                    panoramaxLoader.load(source, bounds, maxPhotosInArea, shouldAbort, hillviewBackendUrl(), authToken)
                                }
                                else -> {
                                    Log.w(TAG, "PhotoOperations: Unknown source type: ${source.type}")
                                    emptyList()
                                }
                            }
                        }

                        if (!shouldAbort()) {
                            sourcesPhotosInArea[source.id] = photos
                            if (doLog) Log.d(TAG, "PhotoOperations: Area load complete for ${source.id}: ${photos.size} photos")

                            // Send completion status for this individual source
                            onSourceLoadingStatus?.invoke(source.id, false, "Loaded ${photos.size} photos", null)
                            onSourcePhotos?.invoke(source.id, photos)
                        }

                    } catch (cancelled: CancellationException) {
                        // Ours (a newer area superseded this one) — never report it as a source error.
                        throw cancelled
                    } catch (error: Exception) {
                        Log.e(TAG, "PhotoOperations: Error loading source ${source.id}: ${error.message}", error)

                        // Send error status for this individual source
                        onSourceLoadingStatus?.invoke(source.id, false, null, "Error: ${error.message}")

                        // Continue with other sources
                    }
                }
            }
        }
        /* The sequential loop this replaces (one source after another; the map
           only updated after the last one):
        for (source in sources.filter { it.enabled }) {
            if (shouldAbort()) break
            try {
                onSourceLoadingStatus?.invoke(source.id, true, "Loading photos...", null)
                ...
                val photos = if (canUseCache) { ... } else { when (source.type) { ... } }
                if (!shouldAbort()) {
                    sourcesPhotosInArea[source.id] = photos
                    onSourceLoadingStatus?.invoke(source.id, false, "Loaded ${photos.size} photos", null)
                }
            } catch (error: Exception) {
                Log.e(TAG, "PhotoOperations: Error loading source ${source.id}: ${error.message}", error)
                onSourceLoadingStatus?.invoke(source.id, false, null, "Error: ${error.message}")
            }
        }
        */

        if (doLog) Log.d(TAG, "PhotoOperations: Area processing complete ($processId) - ${sourcesPhotosInArea.values.sumOf { it.size }} photos in area")
        return sourcesPhotosInArea.toMap()
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
        val crossesAntimeridian = bounds.top_left.lng > bounds.bottom_right.lng
        return photos.filter { photo ->
            photo.coord.lat <= bounds.top_left.lat &&
            photo.coord.lat >= bounds.bottom_right.lat &&
            if (crossesAntimeridian) {
                photo.coord.lng >= bounds.top_left.lng || photo.coord.lng <= bounds.bottom_right.lng
            } else {
                photo.coord.lng >= bounds.top_left.lng && photo.coord.lng <= bounds.bottom_right.lng
            }
        }
    }

    /**
     * Clean up all resources
     */
    fun cleanup() {
        if (doLog) Log.d(TAG, "PhotoOperations: Cleaning up all resources")
        sourceCache.clear()
    }
}
