package cz.hillview.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.ui.Modifier

/**
 * What the sensors said at the moment of capture; burned into the photo's
 * EXIF, which is the contract with the backend parser and the pics pipeline.
 */
data class SensorSnapshot(
    val latitude: Double? = null,
    val longitude: Double? = null,
    val altitude: Double? = null,
    val accuracyM: Float? = null,
    /** Compass azimuth, degrees clockwise from magnetic north. */
    val bearingDeg: Float? = null,
    /**
     * Declination-corrected azimuth (true north) — what the whole pipeline
     * stores and interprets (the EXIF parser reads the magnitude only, and
     * every writer in the ecosystem puts TRUE heading there).
     */
    val trueBearingDeg: Float? = null,
    /** Which sensor produced the heading — EXIF provenance (bearing_source). */
    val bearingSource: String? = null,
    val capturedAtMs: Long,
    /** Age of the location fix at capture time, or null without a fix. */
    val locationAgeMs: Long? = null,
)

data class CapturedPhoto(
    val path: String,
    val snapshot: SensorSnapshot,
)

data class CaptureState(
    val supported: Boolean = true,
    /** Camera bound and ready to shoot. */
    val ready: Boolean = false,
    val capturing: Boolean = false,
    val hasFix: Boolean = false,
    val bearingDeg: Float? = null,
    val lastPhoto: CapturedPhoto? = null,
    val errorMessage: String? = null,
)

@Stable
interface PhotoCapture {
    val state: CaptureState

    fun capture()

    /** Camera preview + platform permission UI. */
    @Composable
    fun CameraPane(modifier: Modifier)
}

@Composable
expect fun rememberPhotoCapture(): PhotoCapture
