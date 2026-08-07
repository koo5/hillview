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
    /** EXIF provenance: "gps" or "manual" (map-positioned, gate lifted). */
    val locationSource: String? = null,
    /** Age of the location fix at capture time, or null without a fix. */
    val locationAgeMs: Long? = null,
)

data class CapturedPhoto(
    /**
     * Locator for the saved photo: an absolute file path, or a content://
     * URI when it went to MediaStore. Never parse a filename out of this —
     * a URI's last segment is a numeric id, and the backend rejects an
     * extensionless name ("File type not allowed").
     */
    val path: String,
    val filename: String,
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

/** A user-supplied position for when the sky is unreachable. */
data class ManualLocation(val latitude: Double, val longitude: Double)

/**
 * The shutter requires a location fix — a photo mapping app's photos must
 * land somewhere, and first-time users have to be walked into using it
 * right. The requirement is liftable, deliberately: someone starting the
 * app underground can position the map by hand and shoot against that.
 */
fun shutterEnabled(ready: Boolean, hasFix: Boolean, manualLocationArmed: Boolean): Boolean =
    ready && (hasFix || manualLocationArmed)

@Stable
interface PhotoCapture {
    val state: CaptureState

    /**
     * The lifted-gate position: when set, captures without a fresh fix are
     * stamped with it, tagged location_source "manual". A fresh GPS fix
     * always wins over this — the map position goes stale as the user
     * walks, the fix does not.
     */
    var manualLocation: ManualLocation?

    fun capture()

    /** Camera preview + platform permission UI. */
    @Composable
    fun CameraPane(modifier: Modifier)
}

@Composable
expect fun rememberPhotoCapture(): PhotoCapture
