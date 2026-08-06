package cz.hillview.map

import kotlinx.coroutines.flow.StateFlow

/** A photo as the map cares about it. */
data class PhotoMarker(
    val id: String,
    val latitude: Double,
    val longitude: Double,
    /** True-north heading the photo was shot at, if known — drawn as a tick. */
    val bearingDeg: Double?,
    val capturedAtMs: Long,
    val uploadStatus: String,
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

/**
 * Where the map is looking. Bearing is true north, degrees clockwise —
 * the same convention as the EXIF the capture writes.
 */
data class MapCamera(
    val latitude: Double = 50.0874,
    val longitude: Double = 14.4212,
    val zoom: Double = 16.0,
    val bearingDeg: Double = 0.0,
)

/** Walking rotates the view to the sensor heading; car keeps a mount offset. */
enum class BearingMode { Walking, Car }
