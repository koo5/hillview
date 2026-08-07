package cz.hillview.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import kotlin.math.roundToInt
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
    /** Latest fix, so the screen can keep the map in step while tracking. */
    val fixLatitude: Double? = null,
    val fixLongitude: Double? = null,
    /** Magnetometer status on Android's 0-3 scale; null = not yet known. */
    val compassAccuracy: Int? = null,
    /** Device advertises MANUAL_SENSOR — shutter control is offerable. */
    val manualShutterSupported: Boolean = false,
    /** The pinned shutter time, null = auto exposure. */
    val shutterNs: Long? = null,
    val bearingDeg: Float? = null,
    val lastPhoto: CapturedPhoto? = null,
    val errorMessage: String? = null,
)

/**
 * The offered shutter times, in nanoseconds. Chosen for the app's actual
 * use case — killing motion blur when shooting from a moving vehicle —
 * so the ladder starts where handheld auto-exposure typically ends.
 */
val SHUTTER_CHOICES_NS: List<Long> = listOf(
    8_000_000L, // 1/125
    4_000_000L, // 1/250
    2_000_000L, // 1/500
    1_000_000L, // 1/1000
    500_000L, // 1/2000
)

fun formatShutter(ns: Long): String = "1/${(1_000_000_000.0 / ns).roundToInt()}"

/**
 * Shutter priority, done by hand because Camera2 has no such AE mode: keep
 * the exposure product (time x gain) the metering chose, at the pinned
 * time. Pinning a faster shutter raises ISO to compensate; the range clamp
 * means very fast pins in dim light underexpose rather than fail — which
 * is the honest outcome.
 */
fun shutterPriorityIso(
    meteredExposureNs: Long,
    meteredIso: Int,
    pinnedExposureNs: Long,
    minIso: Int,
    maxIso: Int,
): Int {
    val ideal = meteredIso.toDouble() * meteredExposureNs.toDouble() / pinnedExposureNs.toDouble()
    return ideal.roundToInt().coerceIn(minIso, maxIso)
}

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

    /**
     * Pinned shutter time in nanoseconds, null = auto. Only honoured when
     * [CaptureState.manualShutterSupported]; ISO follows via
     * [shutterPriorityIso] so brightness tracks what the metering last saw.
     */
    var shutterNs: Long?

    /**
     * Power saving: cap the preview frame rate. One of the three effects
     * the Tauri toggle documents ("map moves only after captures, reduced
     * preview frame rate, animations off") — the map effect lives in the
     * screen, and there are no ambient animations here to stop.
     */
    var ecoPreviewFps: Boolean

    fun capture()

    /** Camera preview + platform permission UI. */
    @Composable
    fun CameraPane(modifier: Modifier)
}

@Composable
expect fun rememberPhotoCapture(): PhotoCapture
