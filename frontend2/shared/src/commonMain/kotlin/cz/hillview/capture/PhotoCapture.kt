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
    /**
     * The PURE DEVICE pose at the shutter, degrees in the
     * OrientationEventListener frame (0 natural, 90 turned clockwise, 180
     * inverted, 270 counter-clockwise). Gravity-derived — deliberately not
     * the screen's rotation, which is frozen whenever auto-rotate is off.
     *
     * Provenance and diagnostics only: the JPEG's EXIF Orientation tag is
     * written by CameraX from the target rotation this pose implies, because
     * only CameraX knows the camera's sensorOrientation and lens facing.
     */
    val deviceRotationDeg: Int? = null,
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
    val fixAltitude: Double? = null,
    val fixAccuracyM: Float? = null,
    /** Wall-clock ms of the last fix, so the UI can watch it go stale. */
    val fixAtMs: Long? = null,
    /** Magnetometer status on Android's 0-3 scale; null = not yet known. */
    val compassAccuracy: Int? = null,
    /** Real JPEG output sizes, biggest first — empty until the camera binds. */
    val availableResolutions: List<CaptureResolution> = emptyList(),
    /** The pinned still size; null = CameraX's own choice. */
    val selectedResolution: CaptureResolution? = null,
    /** Device advertises MANUAL_SENSOR — shutter control is offerable. */
    val manualShutterSupported: Boolean = false,
    /** AF-off + a real focus range exist — the ∞ toggle is offerable. */
    val manualFocusSupported: Boolean = false,
    /** Focus pinned at infinity (the vista shot) — mirrored when applied. */
    val focusInfinity: Boolean = false,
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

/**
 * The overlay backdrop cycle from CameraOverlay.svelte: +2 wrapping past 5
 * to 0, so from the default 3 it settles into the {0, 2, 4} walk. The
 * content never disappears — the cycle only trades legibility against how
 * much preview the glass eats.
 */
fun nextOverlayOpacity(current: Int): Int {
    val next = current + 2
    return if (next > 5) 0 else next
}

/** A still-capture output size the sensor genuinely offers. */
data class CaptureResolution(val width: Int, val height: Int)

/**
 * The Tauri labels ("1080p (1920×1080)"), extended to whatever the sensor
 * reports: named tiers where they exist, plain dimensions elsewhere.
 */
fun resolutionLabel(r: CaptureResolution): String {
    val name = when (r.height) {
        2160 -> "4K"
        1440 -> "1440p"
        1080 -> "1080p"
        720 -> "720p"
        else -> {
            val mp = (r.width.toLong() * r.height / 1_000_000.0)
            "${fmtDecimals(mp, 1)} MP"
        }
    }
    return "$name (${r.width}×${r.height})"
}

/** What the shutter should sound like — the pocket has no screen. */
enum class CaptureTone { Normal, Degraded }

/**
 * A different tone when the photo's position is anything but a fresh fix:
 * interval capture runs in a pocket, and an accidental slip into a
 * degraded location mode must be audible, not just visible. (User-raised:
 * repairing mis-positioned photos after a session is a manual slog.)
 */
/**
 * How old a fix may be and still count as fresh — the gate, the tone, the
 * manual-fallback arbitration and the stale warning all share this one
 * number. A frontend2 divergence (the original has no age concept at all);
 * see docs/tauri-capture-ui-contract.md, "Fix freshness".
 */
const val FIX_FRESH_MS = 15_000L

/**
 * True when a capture RIGHT NOW would stamp the photo with a stale fix:
 * there is a fix, it has gone stale, and no manual position (armed fallback
 * or accepted claim) would take over. The original silently geotags from
 * however old a fix; here the user gets told.
 */
fun staleFixWarning(fixAtMs: Long?, nowMs: Long, manualAvailable: Boolean): Boolean =
    !manualAvailable && fixAtMs != null && nowMs - fixAtMs > FIX_FRESH_MS

fun captureTone(locationSource: String?, locationAgeMs: Long?): CaptureTone =
    if (locationSource == "gps" && (locationAgeMs == null || locationAgeMs <= FIX_FRESH_MS)) {
        CaptureTone.Normal
    } else {
        CaptureTone.Degraded
    }

/** A user-supplied position for when the sky is unreachable. */
data class ManualLocation(val latitude: Double, val longitude: Double)

/**
 * The bearing a capture stamps — Tauri's known-good semantics: photos
 * carry the MAP's bearing state (the arrow), whatever currently owns it:
 * walking's compass, car mode's gps-kalman course + mount offset, or a
 * hand-set arrow. NOT the raw compass (that was the car-mode bug).
 */
data class StampBearing(val trueDeg: Float, val source: String)

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
     * When true the manual position beats even a fresh fix — the claimed
     * "I am at the map position" mode. When false it is only the no-fix
     * fallback.
     */
    var manualLocationWins: Boolean

    /**
     * Pinned shutter time in nanoseconds, null = auto. Only honoured when
     * [CaptureState.manualShutterSupported]; ISO follows via
     * [shutterPriorityIso] so brightness tracks what the metering last saw.
     */
    var shutterNs: Long?

    /**
     * The map bearing state, pushed live by the capture screen — what a
     * capture stamps and the pill shows (see [StampBearing]).
     */
    var stampBearing: StampBearing?

    /**
     * Pin focus at infinity — the vista shot this app exists for. A tap
     * on the preview (tap-to-focus) hands back to auto. Native-ish
     * divergence: the original's focus-distance slider was necessity UX;
     * ∞/auto plus tap and long-press-lock covers the real cases.
     */
    var focusInfinity: Boolean

    /**
     * Power saving: cap the preview frame rate. One of the three effects
     * the Tauri toggle documents ("map moves only after captures, reduced
     * preview frame rate, animations off") — the map effect lives in the
     * screen, and there are no ambient animations here to stop.
     *
     * null = default (no throttle). [ECO_DUTY_MAX_FPS]..30 = an AE
     * frame-rate cap. Below that, real hardware AE ranges run out, so the
     * preview USE CASE duty-cycles: bound for a beat every 1/fps seconds,
     * frozen on its last frame between beats. Exactly 0 = capture-only:
     * the preview refreshes only when a capture lands.
     */
    var ecoPreviewFps: Float?

    /**
     * Pin the still-capture size (null = auto). Rebinding the camera is the
     * implementation's business; the choice lands in
     * [CaptureState.selectedResolution] when applied.
     */
    fun selectResolution(resolution: CaptureResolution?)

    fun capture()

    /** Camera preview + platform permission UI. */
    @Composable
    fun CameraPane(modifier: Modifier)
}

/**
 * The two eco mechanisms and their honest limits (emulator-diagnosed,
 * see the contract doc): AE target-fps ranges are reliable down to ~7;
 * duty-cycling the preview use case (600 ms live beat per period) only
 * makes sense when the period clearly exceeds the beat + the ~200 ms
 * session reconfiguration, i.e. at and below 1 fps. The 1..7 dead zone
 * is SKIPPED by the slider axis rather than mislabelled.
 */
const val ECO_DUTY_BAND_MAX_FPS = 1f
const val ECO_AE_MIN_FPS = 7f

/**
 * The eco slider's value axis (t: 0 = bottom, 1 = top): the very bottom
 * band is the capture-only sentinel (0); then the duty band runs
 * logarithmically 0.1..1; the upper half runs 7..30 (the AE band); the
 * top is 30 ≈ the untouched default. Log, because a linear axis would
 * crowd every battery-relevant value into the bottom centimetre.
 */
fun ecoSliderToFps(t: Float): Float = when {
    t >= 1f -> 30f
    t <= 0.05f -> 0f
    t < 0.5f -> {
        val u = (t - 0.05f) / 0.45f
        // 0.1 * 10^u spans 0.1 .. 1.
        (0.1 * kotlin.math.exp(kotlin.math.ln(10.0) * u)).toFloat()
    }
    else -> {
        val u = (t - 0.5f) / 0.5f
        // 7 * (30/7)^u spans 7 .. 30.
        (7.0 * kotlin.math.exp(kotlin.math.ln(30.0 / 7.0) * u)).toFloat()
    }
}

/**
 * [ecoSliderToFps]'s inverse — the slider's initial thumb position.
 * Dead-zone values (1..7, possible only from old prefs) land on the
 * band boundary.
 */
fun ecoFpsToSlider(fps: Float): Float = when {
    fps <= 0f -> 0f
    fps >= 30f -> 1f
    fps <= 1f -> {
        val u = (kotlin.math.ln(fps / 0.1) / kotlin.math.ln(10.0)).toFloat()
        // Shy of 0.5: exactly 0.5 belongs to the AE band's 7.
        (0.05f + 0.45f * u).coerceIn(0.05f, 0.4995f)
    }
    fps < 7f -> 0.5f
    else -> {
        val u = (kotlin.math.ln(fps / 7.0) / kotlin.math.ln(30.0 / 7.0)).toFloat()
        (0.5f + 0.5f * u).coerceIn(0.5f, 1f)
    }
}

fun ecoFpsLabel(fps: Float): String = when {
    fps <= 0f -> "on 📸 only"
    fps >= 30f -> "default"
    fps < 1f -> "${fmtDecimals(fps.toDouble(), 1)} fps"
    else -> "${kotlin.math.round(fps).toInt()} fps"
}

@Composable
expect fun rememberPhotoCapture(): PhotoCapture
