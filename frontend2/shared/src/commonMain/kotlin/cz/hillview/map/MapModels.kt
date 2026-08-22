package cz.hillview.map

import kotlinx.coroutines.flow.StateFlow

/** One rendition of a photo: the same image at one particular size. */
data class PhotoRendition(
    val url: String,
    val width: Int,
    val height: Int,
)

/**
 * A photo as the map cares about it — and, since the viewer pane shows the
 * same objects, as the viewer needs it too.
 *
 * It carries the whole [sizes] map rather than one chosen URL because the
 * choice is not the model's to make: each slot picks the smallest rendition
 * at least as wide as ITS container, and the same photo is a neighbour in one
 * slot and the front photo in another (see [pickRendition] and
 * docs/tauri-viewer-ui-contract.md).
 */
data class PhotoMarker(
    val id: String,
    val latitude: Double,
    val longitude: Double,
    /** True-north heading the photo was shot at; null when unknown. */
    val bearingDeg: Double?,
    /**
     * Elevation the photo was shot at, degrees, null when unknown. The map
     * ignores it; the viewer pane navigates up and down by it (see
     * docs/tauri-viewer-ui-contract.md), and treats null as level.
     */
    val pitchDeg: Double? = null,
    val capturedAtMs: Long,
    /** Which photo source it came from — decides the marker's border colour. */
    val source: String = "device",
    /** Gold, and never recoloured by bearing. */
    val featured: Boolean = false,
    /** Washed out: filtered without override, or non-featured inside range. */
    val greyed: Boolean = false,
    /**
     * Content hash, when known — what lets a photo captured HERE and its
     * uploaded twin from the backend collapse into one marker.
     */
    val fileMd5: String? = null,
    /**
     * Renditions by key: numeric widths ("500", "1024", …) plus "full".
     * Empty when the source offers none, in which case [url] is all there is.
     */
    val sizes: Map<String, PhotoRendition> = emptyMap(),
    /** The single URL a source without renditions offers, if any. */
    val url: String? = null,
    /** Device photos resolve through the platform's own file access. */
    val isDevicePhoto: Boolean = false,
    /**
     * The backend's verdict under the active analysis filters: present but
     * non-matching. Drawn washed out unless the user flips the override —
     * the server returns ALL photos in bounds and flags rather than hides,
     * so the map never silently loses photos to a filter.
     */
    val filteredOut: Boolean = false,
)

/** The visible map area, in the corner convention the backend query uses. */
data class MapViewport(
    val topLeftLat: Double,
    val topLeftLon: Double,
    val bottomRightLat: Double,
    val bottomRightLon: Double,
)

/**
 * A toggleable photo source, as the original's sources store describes one
 * (data.svelte.ts: id/name/enabled defaults — hillview and device on,
 * mapillary/panoramax off until their loaders are wired here).
 */
data class MapSourceDescriptor(
    val id: String,
    val name: String,
    val defaultEnabled: Boolean = true,
)

interface PhotoMarkerSource {
    /** What this source is on the map's toggle panel; null = not listed. */
    val descriptor: MapSourceDescriptor? get() = null

    /** The composite's toggle plumbing; leaf sources need not implement. */
    fun sourceDescriptors(): List<MapSourceDescriptor> =
        listOfNotNull(descriptor)

    fun setSourceEnabled(id: String, enabled: Boolean) {}

    val markers: StateFlow<List<PhotoMarker>>

    /**
     * The selected photo is pinned: limits must never drop what the user is
     * looking at. The Tauri app calls these "picks" and sends them to the
     * backend for the same reason.
     */
    var pinnedId: String?

    /** Where the map is looking; sources that don't query by area ignore it. */
    fun setViewport(viewport: MapViewport) {}

    /** Re-read with the current limit (see MapSettings.maxPhotos). */
    suspend fun refresh()
}

/** Walking rotates the view to the sensor heading; car keeps a mount offset. */
enum class BearingMode { Walking, Car }

/**
 * Which rendition to show in a container [containerWidthPx] wide, ported from
 * Photo.svelte's updateSelectedUrl.
 *
 * The rule: of the NUMERIC sizes in ascending order, the first at least as
 * wide as the container — the smallest one that will not be upscaled. If none
 * qualifies, "full"; if there is no "full" either, the widest numeric one;
 * and failing everything, the photo's bare [PhotoMarker.url].
 *
 * The choice belongs to the slot, not the photo: the viewer lays its five
 * slots out at FULL viewport size (a 3x3 grid offset so the front cell covers
 * the screen), so a neighbour asks for the same width the front photo does —
 * which is why the model carries every rendition instead of a chosen one.
 */
fun PhotoMarker.pickRendition(containerWidthPx: Int): PhotoRendition? {
    val numeric = sizes.entries
        .mapNotNull { (key, value) -> key.toIntOrNull()?.let { it to value } }
        .sortedBy { it.first }
    numeric.firstOrNull { (width, _) -> width >= containerWidthPx }?.let { return it.second }
    sizes["full"]?.let { return it }
    numeric.lastOrNull()?.let { return it.second }
    return url?.let { PhotoRendition(it, 0, 0) }
}
