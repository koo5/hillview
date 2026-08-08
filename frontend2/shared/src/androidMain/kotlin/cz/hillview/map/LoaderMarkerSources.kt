package cz.hillview.map

import android.content.Context
import android.util.Log
import cz.hillview.core.nowMs
import cz.hillview.plugin.Bounds
import cz.hillview.plugin.DevicePhotoLoader
import cz.hillview.plugin.LatLng
import cz.hillview.plugin.PhotoData
import cz.hillview.plugin.SourceConfig
import cz.hillview.plugin.StreamPhotoLoader
import cz.hillview.settings.MapSettingsRepository
import kotlin.coroutines.cancellation.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * The marker sources are thin adapters over the shared-kt photo-worker
 * loaders — the SAME code the Tauri app's Kotlin photo worker runs
 * (StreamPhotoLoader's SSE machinery, DevicePhotoLoader's bounds+picks
 * queries), graduated to /shared-kt per the one-implementation rule.
 * All this layer adds is the PhotoMarker mapping and a refetch gate for
 * the map's poll cadence.
 */

/** shared-kt worker model → the map's marker. */
internal fun PhotoData.toMarker(): PhotoMarker = PhotoMarker(
    // The raw photo id, not the "<source>-<id>" uid: picks feed straight
    // back into DAO and backend queries, which speak raw ids.
    id = id,
    latitude = coord.lat,
    longitude = coord.lng,
    // 0 is "unset" everywhere in this pipeline (the loaders default to it).
    bearingDeg = bearing.takeIf { it != 0.0 },
    capturedAtMs = captured_at ?: 0L,
    source = source,
    featured = featured == true,
    fileMd5 = fileHash,
    filteredOut = filtered == true,
)

private fun MapViewport.toBounds() = Bounds(
    top_left = LatLng(topLeftLat, topLeftLon),
    bottom_right = LatLng(bottomRightLat, bottomRightLon),
)

/**
 * This device's captures, through the shared-kt DevicePhotoLoader: photos
 * in the viewport with picks pinned; before the map reports a viewport it
 * degrades to most-recent-first — which is exactly what the retired
 * scaffolding source showed.
 */
class DeviceMarkerSource(
    context: Context,
    private val settings: MapSettingsRepository,
) : PhotoMarkerSource {
    private val loader = DevicePhotoLoader(context)
    private val config = SourceConfig(
        id = "device",
        name = "This device",
        type = "device",
        enabled = true,
        color = "#4ae24d",
    )

    // "Device" is the original's toggle label (data.svelte.ts), Tauri-only
    // there and native-only here.
    override val descriptor = MapSourceDescriptor("device", "Device", defaultEnabled = true)

    private val _markers = MutableStateFlow<List<PhotoMarker>>(emptyList())
    override val markers: StateFlow<List<PhotoMarker>> = _markers.asStateFlow()
    override var pinnedId: String? = null
    private var wantedViewport: MapViewport? = null

    override fun setViewport(viewport: MapViewport) {
        wantedViewport = viewport
    }

    override suspend fun refresh() {
        _markers.value = withContext(Dispatchers.IO) {
            loader.loadPhotos(
                source = config,
                bounds = wantedViewport?.toBounds(),
                maxPhotos = settings.settings.value.maxPhotos,
                shouldAbort = { false },
                picks = setOfNotNull(pinnedId),
            )
        }
            // (0,0) is the DB's "no location" — never a real marker.
            .filter { it.coord.lat != 0.0 || it.coord.lng != 0.0 }
            .map { it.toMarker() }
    }
}

/**
 * A backend stream source (hillview; mapillary/panoramax configs slot in
 * the same way) through the shared-kt StreamPhotoLoader. A failed fetch
 * keeps the last good set — a map that flickers empty on every network
 * hiccup is worse than a few seconds of staleness.
 */
class StreamMarkerSource(
    private val source: SourceConfig,
    private val settings: MapSettingsRepository,
    /** Logged-in queries see the user's own private photos too. */
    private val freshToken: suspend () -> String?,
) : PhotoMarkerSource {
    private val loader = StreamPhotoLoader()
    private val gate = RefetchGate(REFETCH_MS)

    override val descriptor = MapSourceDescriptor(
        source.id,
        source.name.ifBlank { source.id },
        defaultEnabled = source.enabled,
    )

    private val _markers = MutableStateFlow<List<PhotoMarker>>(emptyList())
    override val markers: StateFlow<List<PhotoMarker>> = _markers.asStateFlow()
    override var pinnedId: String? = null
    private var wantedViewport: MapViewport? = null

    override fun setViewport(viewport: MapViewport) {
        wantedViewport = viewport
    }

    override suspend fun refresh() {
        val vp = wantedViewport ?: return // the map has not told us where it looks yet
        val s = settings.settings.value
        // Only meaningful when it deviates from the server default; with it
        // false, unanalyzed photos come back flagged `filtered`, not hidden.
        val filters = if (!s.showUnanalyzed) """{"show_unanalyzed": false}""" else null
        val key = "$vp|${s.maxPhotos}|$pinnedId|$filters"
        val now = nowMs()
        if (!gate.shouldFetch(key, now)) return

        try {
            val photos = withContext(Dispatchers.IO) {
                loader.loadPhotos(
                    source = source,
                    bounds = vp.toBounds(),
                    maxPhotos = s.maxPhotos,
                    authToken = freshToken(),
                    shouldAbort = { false },
                    picks = setOfNotNull(pinnedId),
                    queryOptionsJson = filters,
                )
            }
            _markers.value = photos.map { it.toMarker() }
            gate.recordFetch(key, now)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.w(TAG, "${source.id} fetch failed (keeping last set): ${e.message}")
        }
    }

    companion object {
        private const val TAG = "StreamMarkerSource"
        const val REFETCH_MS = 30_000L
    }
}
