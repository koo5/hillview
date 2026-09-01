package cz.hillview.map

import android.content.Context
import android.util.Log
import cz.hillview.core.nowMs
import cz.hillview.plugin.Bounds
import cz.hillview.plugin.DevicePhotoLoader
import cz.hillview.plugin.LatLng
import cz.hillview.plugin.PanoramaxPhotoLoader
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
    // The loaders keep 0.0 as the wire default for a missing heading and say
    // so in has_bearing; testing for 0.0 here used to turn a photo shot due
    // north into "no bearing" (grey, no arrow, out of the viewer ring).
    //bearingDeg = bearing.takeIf { it != 0.0 },
    bearingDeg = bearing.takeIf { has_bearing },
    // Already nullable upstream, so it passes through untouched — unlike
    // bearing, this one never used 0 to mean "unset".
    pitchDeg = pitch,
    capturedAtMs = captured_at ?: 0L,
    source = source,
    featured = featured == true,
    fileMd5 = fileHash,
    // The whole rendition set travels with the photo: the slot that shows it
    // decides which one to fetch, and the same photo is a neighbour in one
    // slot and the front photo in another.
    sizes = sizes.orEmpty().mapValues { (_, s) ->
        cz.hillview.map.PhotoRendition(url = s.url, width = s.width, height = s.height)
    },
    url = url,
    isDevicePhoto = is_device_photo,
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
        // The loader rethrows, and this source is first in the composite's
        // list — so without this a Room failure used to abort the whole
        // sweep. Same rule as the network sources: keep the last set.
        try {
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
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.w(TAG, "device query failed (keeping last set): ${e.message}")
        }
    }

    companion object {
        private const val TAG = "hv-DeviceMarkerSource"
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
                    // Every SSE batch goes straight to the map: the composite
                    // re-merges on each publish, so markers fill in while the
                    // stream is still open instead of at stream_complete.
                    onBatch = { partial -> _markers.value = partial.map { it.toMarker() } },
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
        private const val TAG = "hv-StreamMarkerSource"
        const val REFETCH_MS = 30_000L
    }
}

/**
 * Panoramax, through the shared-kt PanoramaxPhotoLoader (the Tauri
 * plugin's own): STAC search against the public instance, hidden-content
 * filtering resolved through our backend when a token exists. Default
 * OFF, as the original's data.svelte.ts ships it — the toggle wakes it.
 */
class PanoramaxMarkerSource(
    private val source: SourceConfig,
    private val settings: MapSettingsRepository,
    /** Our backend — the hidden-content list rides on it, not Panoramax. */
    private val backendUrl: String,
    private val freshToken: suspend () -> String?,
) : PhotoMarkerSource {
    private val loader = PanoramaxPhotoLoader()
    private val gate = RefetchGate(StreamMarkerSource.REFETCH_MS)

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
        val key = "$vp|${s.maxPhotos}"
        val now = nowMs()
        if (!gate.shouldFetch(key, now)) return

        try {
            val photos = withContext(Dispatchers.IO) {
                loader.loadPhotos(
                    source = source,
                    bounds = vp.toBounds(),
                    maxPhotos = s.maxPhotos,
                    shouldAbort = { false },
                    hillviewBackendUrl = backendUrl,
                    authToken = freshToken(),
                )
            }
            _markers.value = photos.map { it.toMarker() }
            gate.recordFetch(key, now)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.w(TAG, "panoramax fetch failed (keeping last set): ${e.message}")
        }
    }

    companion object {
        private const val TAG = "hv-PanoramaxMarkerSource"
    }
}
