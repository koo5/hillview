package cz.hillview.map

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Merges the device source with the backend source(s) into the one marker
 * list the map draws. A photo captured on this device and its uploaded twin
 * from the backend collapse by content hash — the backend copy wins, since
 * it carries what only the server knows (featured, analysis filtering,
 * everyone-visible identity).
 */
class CompositeMarkerSource(
    private val sources: List<PhotoMarkerSource>,
) : PhotoMarkerSource {
    private val _markers = MutableStateFlow<List<PhotoMarker>>(emptyList())
    override val markers: StateFlow<List<PhotoMarker>> = _markers.asStateFlow()

    override var pinnedId: String? = null
        set(value) {
            field = value
            sources.forEach { it.pinnedId = value }
        }

    override fun setViewport(viewport: MapViewport) {
        sources.forEach { it.setViewport(viewport) }
    }

    override suspend fun refresh() {
        // Each source guards its own failures (a network hiccup must not
        // blank the device markers) — so refresh them all, then merge.
        sources.forEach { it.refresh() }
        _markers.value = merge(sources.map { it.markers.value })
    }

    private fun merge(lists: List<List<PhotoMarker>>): List<PhotoMarker> {
        val winnersByMd5 = LinkedHashMap<String, PhotoMarker>()
        val unhashed = mutableListOf<PhotoMarker>()
        for (marker in lists.flatten()) {
            val md5 = marker.fileMd5
            if (md5 == null) {
                unhashed += marker
                continue
            }
            val current = winnersByMd5[md5]
            winnersByMd5[md5] = when {
                current == null -> marker
                current.source == "device" && marker.source != "device" -> marker
                else -> current
            }
        }
        return unhashed + winnersByMd5.values
    }
}
