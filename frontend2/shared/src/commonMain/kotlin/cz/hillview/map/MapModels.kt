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
    val uploadStatus: String,
    /** Which photo source it came from — decides the marker's border colour. */
    val source: String = "device",
    /** Gold, and never recoloured by bearing. */
    val featured: Boolean = false,
    /** Washed out: filtered without override, or non-featured inside range. */
    val greyed: Boolean = false,
)

/**
 * SCAFFOLDING (P3): the marker source is "the last N photos this device
 * captured", read from the shared upload database. The real thing queries the
 * backend for photos in the viewport — this exists so the orientation map has
 * something true to draw while the map itself is built.
 */
interface PhotoMarkerSource {
    val markers: StateFlow<List<PhotoMarker>>

    /** Re-read with the current limit (see FilterSettings.maxPhotos). */
    suspend fun refresh()
}

/** Walking rotates the view to the sensor heading; car keeps a mount offset. */
enum class BearingMode { Walking, Car }
