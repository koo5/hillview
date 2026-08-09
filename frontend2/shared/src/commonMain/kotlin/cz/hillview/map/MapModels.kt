package cz.hillview.map

import kotlinx.coroutines.flow.StateFlow

/** A photo as the map cares about it. */
data class PhotoMarker(
    val id: String,
    val latitude: Double,
    val longitude: Double,
    /** True-north heading the photo was shot at; null when unknown. */
    val bearingDeg: Double?,
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
