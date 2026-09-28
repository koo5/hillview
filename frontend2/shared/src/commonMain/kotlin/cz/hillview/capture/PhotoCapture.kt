package cz.hillview.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.roundToLong
import androidx.compose.ui.Modifier

/**
 * What the sensors said at the moment of capture; burned into the photo's
 * EXIF, which is the contract with the backend parser and the pics pipeline.
 */
/**
 * How this capture's instants related to each other — the one object that says what
 * `captured_at` actually IS.
 *
 * It exists because the answer is "the button press", and the press is 332–426 ms
 * before the exposure in Latency mode and ~1213 ms in Quality (measured 2026-09-27,
 * 13 captures). That gap cannot be calibrated away: it varies by ±47 ms WITHIN one
 * interval run at fixed settings, so only a per-capture measurement describes it.
 * Until the exposure instant itself is reachable — see
 * docs/todo/captured-at-is-the-exposure.md — the honest move is to say which instant
 * we mean and how far the other ones were.
 *
 * Secondary, and the reason it ships now: these numbers reach the server inside the
 * `capture_timing` provenance object, so the press→exposure behaviour can be studied
 * from uploaded photos instead of from an attached cable.
 */
@kotlinx.serialization.Serializable
data class CaptureTiming(
    /** What `captured_at` is. "press" today; never silently something else. */
    val capturedAtSource: String,
    /** Press → CameraX's onCaptureStarted. Null when that callback never fired. */
    val pressToExposureMs: Long? = null,
    /** onCaptureStarted → the JPEG landing. */
    val exposureToJpegMs: Long? = null,
    /** "quality" / "latency" / "zsl": the gap depends strongly on it. */
    val stillMode: String? = null,

    /**
     * The exposure itself, on `elapsedRealtimeNanos` — the SAME clock as
     * `imu_samples.t0_ns`, so a consumer can locate the shutter inside the inertial
     * window by subtraction, with no wall-clock quantization in the way.
     *
     * Present only when the capture owned its file write; the frame's own
     * SENSOR_TIMESTAMP is the only source, and it arrives on an uptime base that is
     * bridged onto this one at the moment of capture (they were 2.016 DAYS apart on
     * the device this was measured on).
     */
    val exposureElapsedNs: Long? = null,

    /** The same instant as wall-clock ms, so it can be compared to `captured_at`. */
    val exposureWallMs: Long? = null,

    /**
     * Which build took this photo — `BuildInfo.label()`, e.g.
     * `0.1.0 · d4993b5a · 2026-09-28T00:16:00+00:00`.
     *
     * Here because an autoupload can glitch and a phone can be a build behind, and then
     * every number in this object describes code nobody can identify afterwards. That is
     * not hypothetical: two rounds of analysis on 2026-09-28 argued from age
     * distributions about which APK was running, and the version screen settled it in one
     * line.
     *
     * IT IS IN THE WRONG OBJECT and should move. `capture_timing` is about when the
     * shutter opened, not about the software; the right home is a top-level `app` object.
     * It lives here because a top-level key needs `BrowserMetadata` plus
     * `PROVENANCE_KEYS` and therefore a worker deploy, while a nested one needs nothing —
     * and having the build recorded NOW is worth more than having it in the right place
     * later. Move it when the metadata rehaul lands
     * (docs/todo/metadata-structure-sanitization.md).
     */
    val build: String? = null,

    /**
     * Which instant the POSE objects describe — "exposure" when the attitude and
     * inertial readings were looked up at the exposure, "press" when they are the
     * press-time stamp because no sample was within tolerance.
     *
     * Separate from [exposureSource] because the two can disagree: knowing when the
     * frame was exposed does not guarantee a sample from that moment, and a reader
     * deserves to know which of the two it got.
     *
     * MEANING NARROWED 2026-09-28. It used to name the instant every `age_ms` was
     * measured against as well, which conflated "where the values came from" with
     * "what they are dated against" and made both wrong whenever the lookup half
     * failed — see [SensorSnapshot.poseReferenceMs]. Ages are now measured against
     * `exposure_wall_ms` whenever it is present, and this field says only which
     * stream answered. A reader wanting the age reference reads the presence of
     * `exposure_wall_ms`; it needs no field of its own.
     *
     * It also covers only the POSE pair. The position is not looked up — there is no
     * fix at the exposure to look up — it is interpolated there by `StampRefiner`,
     * which reports that separately (see the note under [exposureSource]).
     */
    val poseReferencedTo: String? = null,

    /**
     * How the exposure instant was obtained — "sensor_timestamp", or absent when it
     * was not obtained at all. Never inferred: a dispatch-derived estimate would be
     * ~104 ms late and jitter by ±16, and calling that the exposure is the pretending
     * this whole object exists to stop.
     */
    val exposureSource: String? = null,

    // THREE MORE KEYS REACH THE SERVER IN THIS OBJECT AND ARE NOT FIELDS HERE:
    // `refined_to`, `refined_position` and `refined_bearing`, added to the serialized
    // JSON by StampRefiner.recordRefinement. They cannot be fields, because they are
    // not known at the shutter — the refiner runs seconds later, after the fix that
    // brackets the exposure from the far side has arrived, and writes them into the
    // photo row it is already updating. Listed here so the object's full shape is
    // documented in one place: anyone reading `capture_timing` from the server will
    // see them, and grepping this data class alone would say they do not exist.
)

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
    /**
     * Camera ELEVATION at the shutter, degrees, positive up — how far the
     * phone was tilted, where [trueBearingDeg] says which way it faced. The
     * viewer needs both to offer "the photo above this one".
     *
     * Nullable and never defaulted to 0: the viewer's up/down rule is
     * strictly-higher and strictly-lower, so "level" and "unknown" must stay
     * distinguishable all the way to the server.
     */
    val pitchDeg: Float? = null,
    val capturedAtMs: Long,
    /** EXIF provenance: "gps" or "map" (the map centre — claimed over a fix, or standing in for none); null with no position. */
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
    /**
     * The exposure rule in force at the shutter and what it resolved to,
     * null when AE owned the shot (auto, or a rule still waiting for its
     * first metering — honest either way: AE exposed that frame). Written
     * into the UserComment provenance; CameraX stamps what the sensor
     * actually DID into the standard ExposureTime/ISO tags, so this is the
     * half the file cannot otherwise tell you — what was asked, and why
     * the answer came out the way it did.
     */
    val exposure: ExposureStamp? = null,
    /** The other position stream, when there was one — see [altLocationFor]. */
    val altLocation: AltLocation? = null,
    /**
     * What the DEVICE was measuring at the shutter, as opposed to what the
     * photo is stamped as FACING.
     *
     * [trueBearingDeg] and [pitchDeg] above are the ELECTED answer, which a
     * manual claim, a car course or a turned-to photo can own — and those
     * sources measure no tilt, so they write null and the record loses how
     * the phone was actually held. This is the other half, and it is the
     * only route roll has ever had off the device: the sensor stack has
     * computed it since the beginning, and nothing downstream had a field
     * for it (user, 2026-09-22: "the phone should store every bit of info
     * it has, both raw and processed").
     *
     * Null when the compass had nothing fresh to say at the shutter. It
     * travels in the upload's `attitude` provenance, never as a column:
     * nothing queries it, the SfM bench reads it.
     */
    val attitude: cz.hillview.map.DeviceAttitude? = null,
    /**
     * Was the Armor-22 landscape heading workaround in force?
     *
     * It NEGATES the azimuth past 90° of roll (EnhancedSensorService), so a
     * heading recorded under it and one recorded without are not the same
     * measurement. Nothing downstream could tell them apart, which makes
     * every landscape bearing in the archive ambiguous after the fact.
     */
    val compassLandscapeWorkaround: Boolean? = null,
    /**
     * The receiver's fix as it stood at the shutter — kept for its QUALITY
     * fields, which nothing else carries.
     *
     * Present whether or not the fix won the election: it describes the
     * receiver at that moment, and a photo that recorded the map centre was
     * still taken somewhere the receiver had an opinion about. Where the fix
     * LOST, `altLocation` carries its position; this carries how good it was.
     *
     * The position itself is already in [latitude]/[longitude]/[altitude]/
     * [accuracyM] above, so the serializer emits only what is not there.
     */
    val fix: cz.hillview.map.FixState? = null,
    /** The camera's own calibration and settings at the shutter — see [LensStamp]. */
    val lens: LensStamp? = null,
    /** How the phone was MOVING at the shutter — see [cz.hillview.map.DeviceMotionSample]. */
    val motion: cz.hillview.map.DeviceMotionSample? = null,
    /**
     * What the IMU window around this exposure contained — the summary of the
     * raw samples, which themselves go to the tracking database and travel by
     * CSV. Null when no window was captured: a device without a gyroscope, an
     * activity that did not ask for the IMU, or a shot before the ring filled.
     *
     * Typed as the fields rather than the platform class so commonMain can
     * serialize it; the Android side fills it from `ImuWindowSummary`.
     */
    val imuWindow: ImuWindow? = null,
    /**
     * What `captured_at` means and how far the exposure was from it — see
     * [CaptureTiming].
     *
     * The ONE field here that is not filled at the press, because two of its three
     * numbers do not exist yet: the snapshot is copied with it at the save, once
     * onCaptureStarted and the JPEG have both happened.
     */
    val captureTiming: CaptureTiming? = null,
)

/** See [SensorSnapshot.imuWindow]. Mirrors the engine's `ImuWindowSummary`. */
data class ImuWindow(
    val sampleCount: Int,
    val startMs: Long,
    val endMs: Long,
    /** Peak raw accelerometer magnitude, m/s² — INCLUDES gravity (~9.81 at rest). */
    val accelPeakMps2: Double? = null,
    /** Peak |magnitude − g|: the gravity-free shake signal. Near zero when still. */
    val accelPeakDeviationMps2: Double? = null,
    /** Peak angular rate, rad/s — the rotation-blur signal. */
    val gyroPeakRadS: Double? = null,
    /**
     * How many of [sampleCount] this capture actually WROTE; the rest a
     * neighbouring photo's window had already stored. Interval capture makes
     * consecutive windows overlap heavily, and trimmed they tile the session
     * instead of repeating it.
     */
    val storedCount: Int = 0,
)

/**
 * What the CAMERA knew about itself at the shutter.
 *
 * The largest single gap for reconstruction, and until 2026-09-26 the app read
 * none of it: a solver was left to recover focal length and distortion from the
 * images, when the manufacturer had written its own calibration into
 * `CameraCharacteristics` and the HAL reports the per-frame values on every
 * capture result the app was already receiving (see the 3A callback in
 * `buildPreviewUseCase` — same stream, nothing new bound).
 *
 * Split by LIFETIME, because the two halves are trustworthy in different ways:
 * the per-camera half is factory calibration that cannot change, the per-shot
 * half tracks focus and zoom and is only true of this frame.
 *
 * And the per-shot half is a PREVIEW frame's, not the still's — stated in the
 * provenance as `frame_values_source: "preview"` with an `age_ms` beside it, because
 * the difference is measurable and was measured: focus moved from 7.0279527 to
 * 6.9795275 diopters DURING one press→exposure window (2026-09-27). Read
 * [previewRollingShutterSkewNs] for why exactly one of these fields is renamed rather
 * than merely dated.
 */
data class LensStamp(
    // --- per shot, from the capture result ---
    /** Actual focal length in mm, as the HAL reports it for this frame. */
    val focalLengthMm: Float? = null,
    val apertureFStop: Float? = null,
    /**
     * Focus distance in DIOPTRES (1/metres), the platform's unit: 0.0 IS
     * infinity, and larger means closer. Not metres, and not convertible
     * without the calibration below saying how to read it.
     */
    val focusDistanceDiopters: Float? = null,
    /** How `LENS_FOCUS_DISTANCE` should be read — CALIBRATED / APPROXIMATE / UNCALIBRATED. */
    val focusDistanceCalibration: String? = null,
    /** The user pinned focus at infinity (the app's ∞ toggle) — intent, not measurement. */
    val focusInfinityRequested: Boolean? = null,
    /**
     * Digital zoom in force, 1.0 = none. The effective focal length and the
     * crop both scale with it, so a frame shot at 2× whose intrinsics are read
     * as the 1× ones is simply wrong — and the app has had pinch-to-zoom, and
     * printed "2.0×" on screen, while recording nothing.
     */
    val zoomRatio: Float? = null,
    /**
     * Readout skew top-to-bottom, ns — of a PREVIEW frame, which is why the name says
     * so. Rolling shutter, which matters in car mode.
     *
     * Renamed 2026-09-28. Every field in this "per shot" half comes from the preview
     * repeating request (`setSessionCaptureCallback` is on the PREVIEW builder; the
     * still's `TotalCaptureResult` is not handed out by CameraX and the 2026-09-27
     * experiment proved an `ImageCapture.Builder` callback sees the preview stream
     * too). For most of them that is STALENESS, and [frameValuesAtMs] reports exactly
     * how much. Skew is the one with a PHYSICAL reason to differ: readout time scales
     * with the lines read, and preview and still run different sensor modes and
     * resolutions — this device previews at a fraction of a 4624×3472 array. So the
     * still's value is not merely a fresher version of this one, and a key called
     * `rolling_shutter_skew_ns` would be read as the photo's own readout time by
     * anyone modelling rolling-shutter distortion. 31.1 ms is ~4 cm of translation at
     * walking pace, so the difference is not cosmetic for reconstruction.
     *
     * When a route to the still's own result appears, THAT gets the unqualified name
     * and this one keeps its own.
     */
    val previewRollingShutterSkewNs: Long? = null,
    /**
     * When the preview frame these per-shot values came from was EXPOSED — its own
     * `SENSOR_TIMESTAMP`, bridged onto `elapsedRealtimeNanos` and expressed as wall ms
     * so it can be subtracted from the reference instant like every other `age_ms`.
     *
     * Null when the HAL reported no timestamp, and then no age is emitted rather than
     * a dispatch-derived guess — the callback's own arrival time would fold in a
     * queueing delay that was measured at ~104 ms ± 16 for the still's equivalent.
     */
    val frameValuesAtMs: Long? = null,
    /**
     * fx, fy, cx, cy, skew for THIS frame, in pixels of the pre-correction
     * active array. The HAL may vary it with focus and zoom, which is why it is
     * read per frame and not only from the characteristics.
     */
    val intrinsics: List<Float>? = null,
    /** Radial and tangential distortion for this frame, the platform's 5-coefficient form. */
    val distortion: List<Float>? = null,
    // --- per camera, from the characteristics at bind ---
    /** Factory intrinsics, when the device publishes any. See [intrinsicsAvailable]. */
    val cameraIntrinsics: List<Float>? = null,
    val cameraDistortion: List<Float>? = null,
    /** Physical sensor size in mm (w, h) — with the pixel array, the true pixel pitch. */
    val sensorPhysicalSizeMm: List<Float>? = null,
    /** Active array in pixels (w, h). */
    val sensorPixelArray: List<Int>? = null,
    /**
     * Whether this device publishes a lens calibration AT ALL.
     *
     * Many phones do not, and the absence has to be a recorded FACT rather
     * than something a reader infers from a missing key — "this device does not
     * calibrate its lenses" and "this app version did not look" are different
     * claims about a photo, and only one of them is the phone's fault.
     */
    val intrinsicsAvailable: Boolean? = null,
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
    /**
     * A fix exists this session — EVER, not fresh. This is a mirror of the
     * one state's `lastFix != null`, and it has no clock in it, which is
     * what makes it safe to store. Freshness is derived at read from
     * [fixAtMs] and a clock (see staleFixWarning) and is never kept as a
     * boolean: a stored "fresh" was true at the instant a fix arrived and
     * was never asked again, so the gate and the no-fix offer read a
     * minute-old fix as fresh while the overlay counted its age up beside
     * them (docs/one-state.md, "Derived, not stored").
     */
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
    /** The still-capture mode the bound ImageCapture was built with. */
    val stillCaptureMode: StillCaptureMode = StillCaptureMode.Latency,
    /** The JPEG quality the bound ImageCapture was built with. */
    val jpegQuality: Int = DEFAULT_JPEG_QUALITY,
    /**
     * The camera can do zero-shutter-lag stills (private reprocessing). When
     * false a ZSL choice silently behaves as Latency — the menu says so.
     */
    val zslSupported: Boolean = false,
    /** Device advertises MANUAL_SENSOR — shutter control is offerable. */
    val manualShutterSupported: Boolean = false,
    /** AF-off + a real focus range exist — the ∞ toggle is offerable. */
    val manualFocusSupported: Boolean = false,
    /** Focus pinned at infinity (the vista shot) — mirrored when applied. */
    val focusInfinity: Boolean = false,
    /** The exposure rule in force, null = auto exposure. */
    val exposureRule: ExposureRule? = null,
    /**
     * The (time, gain) the rule last actually resolved to, and how. Null
     * under auto exposure, or while a rule is waiting for its first
     * metering. Diagnostics and the chip label — the plan is what the
     * camera got, the rule is only what was asked for.
     */
    val plan: ExposurePlan? = null,
    val bearingDeg: Float? = null,
    val lastPhoto: CapturedPhoto? = null,
    val errorMessage: String? = null,
    /** A video recording is in progress — the shutter stops it. */
    val recording: Boolean = false,
    /** Wall clock when recording began, for the elapsed readout. */
    val recordingStartedAtMs: Long? = null,
    /** Where the last recording landed, once it has been finalized. */
    val lastVideoPath: String? = null,
)

/**
 * What sits between the shutter press and the exposure — CameraX's
 * still-capture mode, a knob because the delay it buys is the single
 * most visible thing about the shutter and the trade is scene-dependent.
 *
 * Found 2026-08-19 by reading the CameraX 1.6 (camera-pipe) capture
 * pipeline: in [Quality] mode every still is preceded by a 3A LOCK — wait
 * for AF/AE/AWB to converge (≤1 s), then an AF trigger and a wait for the
 * lens to report locked (≤1 s) — before the capture request is even
 * submitted. With focus pinned at infinity (AF mode OFF) the lens never
 * reports "locked", so that second wait is expected to run to its full
 * timeout on every shot. [Latency] skips the lock entirely; for vista
 * shots out of a moving vehicle the lock buys nothing (the scene IS at
 * infinity) and costs the shutter lag the user feels. [ZeroShutterLag]
 * serves the still from a ring buffer of frames already captured by the
 * repeating request (so an exposure rule still applies) — where the
 * camera supports private reprocessing; elsewhere it is Latency.
 *
 * JPEG quality is a separate knob ([JPEG_QUALITY_CHOICES]) because CameraX
 * couples it to the mode by default (100 for Quality, 95 otherwise) and
 * the two trades have nothing to do with each other.
 */
enum class StillCaptureMode(val key: String, val label: String) {
    /** CameraX MAXIMIZE_QUALITY: the 3A lock described above, then the shot. */
    Quality("quality", "Quality (3A lock first)"),

    /** CameraX MINIMIZE_LATENCY: the shot, as it stands. */
    Latency("latency", "Latency (no lock)"),

    /** CameraX ZERO_SHUTTER_LAG where supported, else Latency. */
    ZeroShutterLag("zsl", "Zero shutter lag"),
    ;

    companion object {
        val DEFAULT = Latency
        fun fromKey(key: String?): StillCaptureMode = entries.firstOrNull { it.key == key } ?: DEFAULT
    }
}

/** What the Quality mode used to give implicitly — kept as the default. */
const val DEFAULT_JPEG_QUALITY = 100
val JPEG_QUALITY_CHOICES: List<Int> = listOf(100, 95, 90, 80)

/**
 * The offered shutter times, in nanoseconds. Chosen for the app's actual
 * use case — killing motion blur when shooting from a moving vehicle —
 * so the ladder starts where handheld auto-exposure typically ends.
 *
 * A time here is the TARGET an [ExposureRule] aims at, not necessarily
 * what the sensor ends up being given.
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
 * A recording's elapsed time, "0:07" / "1:05" / "12:34" / "1:02:03".
 *
 * Minutes and seconds, hours only once there are any — a video shot from a
 * moving car runs to minutes, and a leading "0:" on every one of them is a
 * column of noise for the rare case.
 */
fun formatElapsed(ms: Long): String {
    val total = (ms / 1000).coerceAtLeast(0L)
    val seconds = total % 60
    val minutes = (total / 60) % 60
    val hours = total / 3600
    val ss = seconds.toString().padStart(2, '0')
    if (hours == 0L) return "$minutes:$ss"
    return "$hours:${minutes.toString().padStart(2, '0')}:$ss"
}

/**
 * How hard a chosen shutter time is defended when the light disagrees.
 *
 * [Pin] was the only rule this app had, and it has a wall built into it:
 * the aperture is fixed, so once ISO sits on the sensor's floor the
 * shutter is the ONLY lever left — and Pin has nailed it down. Correct
 * exposure at ISO 50 / f/1.8 in open sun is around 1/20000 s, so a 1/2000
 * pin blows out by three stops or more no matter how good the metering is.
 * [Floor] exists because of that; [Sports] because "never slower" is a
 * miserable rule at dusk.
 *
 * The modes differ only in which direction they are allowed to give. The
 * arithmetic is one function — [planExposure].
 */
enum class ExposureMode {
    /** Exactly this time, whatever it costs the highlights. */
    Pin,

    /** This time OR FASTER — the rule that survives full sun. */
    Floor,

    /** A floor that hands the shutter back before the gain gets silly. */
    Sports,
}

/** Past this gain, [ExposureMode.Sports] would rather slow the shutter. */
const val SPORTS_ISO_KNEE = 1600

/** …and it will slow down this far to avoid that, but no further. */
const val SPORTS_SLOWEST_NS = 8_000_000L // 1/125

/**
 * A shutter WINDOW with a target inside it, plus the gain the rule is
 * willing to reach before it starts widening. Every mode is a tuple over
 * these three, which is the point: a new idea is a row here, not a new
 * code path.
 */
data class ExposureRule(
    val mode: ExposureMode,
    val targetNs: Long,
    /** Stops of deliberate under/overexposure — the backlit knob. */
    val evBias: Double = 0.0,
) {
    /** The fastest this rule may go; 0 = as fast as the sensor allows. */
    val fastestNs: Long get() = if (mode == ExposureMode.Pin) targetNs else 0L

    /** The slowest it may go before it gives up and underexposes instead. */
    val slowestNs: Long get() =
        if (mode == ExposureMode.Sports) maxOf(targetNs, SPORTS_SLOWEST_NS) else targetNs

    /** The gain past which [ExposureMode.Sports] trades the shutter back. */
    val isoKnee: Int get() = if (mode == ExposureMode.Sports) SPORTS_ISO_KNEE else Int.MAX_VALUE
}

/** What the sensor will actually accept — the walls every plan clamps to. */
data class SensorExposureCaps(
    val minExposureNs: Long,
    val maxExposureNs: Long,
    val minIso: Int,
    val maxIso: Int,
)

/** Why a plan came out the way it did — the drive's post-mortem. */
enum class ExposureOutcome {
    /** The target held at a gain the sensor was happy to give. */
    OnTarget,

    /** Gain was on the floor, so the shutter went faster to save the highlights. */
    Faster,

    /** The shutter was handed back to keep gain under the knee. */
    Slower,

    /** Gain hit the ceiling: the frame comes out dark, honestly. */
    Underexposed,

    /** Even the fastest time the rule allows is too slow: it blows out. */
    Overexposed,
}

/** A concrete (time, gain) pair to hand Camera2, and how it got there. */
data class ExposurePlan(
    val exposureNs: Long,
    val iso: Int,
    val outcome: ExposureOutcome,
)

/**
 * The rule and its resolution as they stood at the shutter — the debug
 * numbers the ⚡ menu shows, snapshotted per photo for the UserComment
 * provenance (see [SensorSnapshot.exposure]).
 */
data class ExposureStamp(
    val rule: ExposureRule,
    val plan: ExposurePlan,
    /** The AE reading the plan scaled from — the debugging half. */
    val meteredExposureNs: Long? = null,
    val meteredIso: Int? = null,
)

/**
 * The stamp as a JSON object — ONE serialization for its two riders: the
 * EXIF UserComment provenance (PhotoExifWriter, the opt-in EXIF path) and
 * the photos-table `exposureJson` column that the upload metadata carries
 * (the fast-write default). Hand-built to match the writer's existing
 * string style; readers ignore keys they don't know.
 */
fun exposureProvenanceJson(e: ExposureStamp): String {
    val fields = buildList {
        add("\"mode\":\"${e.rule.mode.name.lowercase()}\"")
        add("\"target_ns\":${e.rule.targetNs}")
        add("\"ev_bias\":${e.rule.evBias}")
        add("\"applied_ns\":${e.plan.exposureNs}")
        add("\"iso\":${e.plan.iso}")
        add("\"outcome\":\"${e.plan.outcome.name.lowercase()}\"")
        e.meteredExposureNs?.let { add("\"metered_ns\":$it") }
        e.meteredIso?.let { add("\"metered_iso\":$it") }
    }
    return fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * Shutter priority, done by hand because Camera2 has no such AE mode:
 * hold the exposure product (time x gain) the metering chose, and spend it
 * according to [rule].
 *
 * Everything here scales from what AE last saw, so it is only ever as
 * fresh as the metering handed in — see PhotoCapture.prepareExposure,
 * which is what keeps that from being the moment the mode was chosen.
 */
fun planExposure(
    rule: ExposureRule,
    meteredExposureNs: Long,
    meteredIso: Int,
    caps: SensorExposureCaps,
): ExposurePlan {
    val product = meteredIso.toDouble() * meteredExposureNs.toDouble() * 2.0.pow(rule.evBias)
    val target = rule.targetNs.coerceIn(caps.minExposureNs, caps.maxExposureNs)
    val fastest = maxOf(rule.fastestNs, caps.minExposureNs).coerceAtMost(target)
    val slowest = rule.slowestNs.coerceIn(target, caps.maxExposureNs)
    val isoAtTarget = product / target

    if (isoAtTarget < caps.minIso) {
        // Gain is already on the floor, so the shutter is the only lever
        // left. This is the branch a fixed-aperture phone lives or dies by
        // in daylight, and the one Pin cannot take.
        val wanted = product / caps.minIso
        val time = wanted.roundToLong().coerceIn(fastest, target)
        return ExposurePlan(
            exposureNs = time,
            iso = caps.minIso,
            outcome = when {
                wanted < fastest.toDouble() -> ExposureOutcome.Overexposed
                time < target -> ExposureOutcome.Faster
                else -> ExposureOutcome.OnTarget
            },
        )
    }

    if (isoAtTarget <= rule.isoKnee.toDouble()) {
        val ideal = isoAtTarget.roundToInt()
        return ExposurePlan(
            exposureNs = target,
            iso = ideal.coerceAtMost(caps.maxIso),
            outcome = if (ideal > caps.maxIso) {
                ExposureOutcome.Underexposed
            } else {
                ExposureOutcome.OnTarget
            },
        )
    }

    // Past the knee: give the shutter back rather than the gain, as far as
    // the rule allows — then underexpose, which beats a smeared frame.
    val time = (product / rule.isoKnee).roundToLong().coerceIn(target, slowest)
    val ideal = (product / time).roundToInt()
    return ExposurePlan(
        exposureNs = time,
        iso = ideal.coerceIn(caps.minIso, caps.maxIso),
        outcome = when {
            ideal > caps.maxIso -> ExposureOutcome.Underexposed
            time > target -> ExposureOutcome.Slower
            else -> ExposureOutcome.OnTarget
        },
    )
}

/**
 * The (time, gain) a metering frame is CREDITED to — which exposure the
 * scene meter is told produced the pixels it just measured: the plan while
 * a rule holds the sensor, AE's harvest otherwise, never a mix of the two.
 *
 * The order is the meter's anchor, not a convenience. While a rule is
 * applied AE is off, so the harvest is frozen at whatever light the rule
 * was ENGAGED in — and crediting frames to it moves the loop's fixed point
 * from luma = target to luma = target × (harvest / estimate): the meter
 * stops measuring the scene and starts reproducing the dead reading.
 * Engage Sports in the shade and drive into sun, and every shot of the
 * run comes back pinned near clipping — the interval-mode "stuck in high
 * exposure" report (2026-08-21). SceneMeterLoopTest walks the whole loop
 * through exactly that day.
 */
fun meterCreditedExposure(
    plan: ExposurePlan?,
    aeExposureNs: Long?,
    aeIso: Int?,
): Pair<Long, Int>? = when {
    plan != null -> plan.exposureNs to plan.iso
    aeExposureNs != null && aeIso != null -> aeExposureNs to aeIso
    else -> null
}

/**
 * The bias ladder: the direct answer to a sun in frame, which no shutter
 * rule can help with — shutter priority only ever reproduces the METERING's
 * decision, and metering targets the average, so a backlit scene is
 * supposed to blow out. Pulling a stop or two down is what a photographer
 * does about it.
 */
val EV_BIAS_CHOICES: List<Double> = listOf(-2.0, -1.0, -0.5, 0.0, 0.5, 1.0)

fun formatEvBias(ev: Double): String = when {
    ev == 0.0 -> "0"
    ev == -0.5 -> "-½"
    ev == 0.5 -> "+½"
    ev > 0 -> "+${ev.roundToInt()}"
    else -> "${ev.roundToInt()}"
}

/** The ⚡ menu's rule row, in the order it reads: strictest first. */
val EXPOSURE_MODES: List<ExposureMode> =
    listOf(ExposureMode.Pin, ExposureMode.Floor, ExposureMode.Sports)

fun exposureModeLabel(mode: ExposureMode): String = when (mode) {
    ExposureMode.Pin -> "Pin"
    ExposureMode.Floor -> "Floor"
    ExposureMode.Sports -> "Sports"
}

/**
 * What the ⚡ button says: the rule in one glance, bias included — and,
 * when the light has pushed the PLAN off the rule's target, where it
 * actually landed ("🏃1/2000→1/125").
 *
 * The arrow is the answer to "does the target row even do anything?",
 * asked from a pitch-black room where the button said 1/2000 while the
 * plan had long slid to the Sports floor. The resolved value only lived
 * inside the open ⚡ menu; the button told the rule and kept the outcome
 * to itself, so a working slide and a dead one looked identical.
 */
fun exposureLabel(rule: ExposureRule?, plan: ExposurePlan? = null): String {
    if (rule == null) return "Auto"
    val time = formatShutter(rule.targetNs)
    val head = when (rule.mode) {
        ExposureMode.Pin -> "=$time"
        ExposureMode.Floor -> "≥$time"
        ExposureMode.Sports -> "🏃$time"
    }
    val landed = plan?.takeIf { it.exposureNs != rule.targetNs }
        ?.let { "→${formatShutter(it.exposureNs)}" } ?: ""
    return if (rule.evBias == 0.0) "$head$landed" else "$head$landed ${formatEvBias(rule.evBias)}EV"
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
 * One scale for every row: megapixels, aspect ratio, dimensions —
 * "12.2 MP · 4:3 (4032×3024)".
 *
 * This used to name the video tiers (4K / 1440p / 1080p / 720p) where a
 * height happened to match one and fall back to megapixels otherwise, so a
 * real sensor's list mixed two unrelated scales and could not be compared
 * down the column (user-raised). The Tauri original only ever offered four
 * hardcoded sizes, where that never showed; enumerating what the sensor
 * actually reports is what exposed it.
 *
 * Megapixels because these are STILL sizes — the video-line names are a
 * different domain's vocabulary — and the ratio because it is the thing
 * that silently crops the sensor: 16:9 on a 4:3 sensor is a narrower
 * picture, not just a smaller one.
 */
fun resolutionLabel(r: CaptureResolution): String {
    val mp = r.width.toLong() * r.height / 1_000_000.0
    val ratio = aspectRatioLabel(r)?.let { " · $it" } ?: ""
    return "${fmtDecimals(mp, 1)} MP$ratio (${r.width}×${r.height})"
}

/**
 * "4:3", "16:9" — the reduced ratio, when it reduces to terms small enough
 * to read. An odd sensor size that reduces to something like 683:512 says
 * nothing useful, so it says nothing at all.
 */
internal fun aspectRatioLabel(r: CaptureResolution): String? {
    if (r.width <= 0 || r.height <= 0) return null
    var a = r.width
    var b = r.height
    while (b != 0) {
        val t = a % b
        a = b
        b = t
    }
    if (a == 0) return null
    val w = r.width / a
    val h = r.height / a
    return if (w <= 32 && h <= 32) "$w:$h" else null
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
 * How old a fix may be and still count as fresh — the gate, the tone and the
 * stale warning share this one number. A frontend2 divergence (the original
 * has no age concept at all); see docs/tauri-capture-ui-contract.md, "Fix
 * freshness".
 *
 * It no longer decides anything on its own. Staleness used to hand over to
 * the map position silently, which made the election recorded on every
 * tracking row a lie; now it only WARNS, and the handover is something the
 * user does.
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
data class ManualLocation(val latitude: Double, val longitude: Double, val atMs: Long? = null)

/** The live fix, recorded beside a map position the user claimed. */
const val ALT_SOURCE_GPS_BACKGROUND = "gps-background"

/** The map position, recorded beside the fix while it is NOT yet claimed. */
const val ALT_SOURCE_MAP_UNCLAIMED = "map-unclaimed"

/**
 * The stream a photo did NOT take its position from, riding along so a
 * reviewer can promote it later — the original's `alt_location`
 * (CameraCapture.svelte:958-966), same field names, same JSON.
 */
data class AltLocation(
    val latitude: Double,
    val longitude: Double,
    val atMs: Long?,
    val accuracyM: Float?,
    val source: String,
)

/** `{"lat":..,"lng":..,"ts":..,"accuracy":..,"source":".."}` — the shape the backend's provenance test asserts. */
fun altLocationJson(a: AltLocation): String {
    val fields = buildList {
        add("\"lat\":${a.latitude}")
        add("\"lng\":${a.longitude}")
        a.atMs?.let { add("\"ts\":$it") }
        a.accuracyM?.let { add("\"accuracy\":$it") }
        add("\"source\":\"${a.source}\"")
    }
    return fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * What the device measured at the shutter, as the upload's `attitude`
 * provenance object.
 *
 * ONE object rather than a column each, for the reason `alt_location` is one:
 * nothing on the device queries it, it only travels, and the set of things
 * worth recording about a pose will grow. Named `attitude`, not
 * `orientation`, because EXIF already has an Orientation tag and it means
 * something else entirely — the 1/3/6/8 display rotation CameraX writes.
 *
 * **Why none of this duplicates a column.** The photo's `bearing` and `pitch`
 * are the ELECTED answer, and they are dead-banded: the bearing state only
 * updates when the heading moves more than 1° (MapSensorController), and a
 * manual claim or a car course can own it outright and reports no tilt at
 * all. Every field below is read from the sample itself, on every sample,
 * past no gate — so even when the compass IS elected these are the
 * instantaneous reading and the columns are the last one that cleared the
 * dead-band. When a hand-set bearing is elected, this is the only record that
 * the device was measuring anything.
 *
 * Field by field, and what else holds it (user asked for exactly this audit,
 * 2026-09-22):
 *  - `heading_true_deg` — the compass's own declination-corrected heading. The
 *    `bearing` column is the elected, dead-banded cousin; `bearing_source`
 *    says whether that one came from here at all.
 *  - `heading_magnetic_deg` — the same reading uncorrected. Stored NOWHERE else: the
 *    snapshot has carried it since the beginning and every writer dropped it
 *    (the EXIF tags take true north, by ecosystem convention). Its difference
 *    from `true_deg` is the declination the device applied.
 *  - `pitch_deg` — tilt. Same relationship to the `pitch` column as above.
 *  - `roll_deg` — stored nowhere else, and never left the device before this.
 *    NOT the camera's rotation about its optical axis: the rotation matrix is
 *    remapped for `device_rotation_deg` FIRST, so this is the residual tilt
 *    within that quadrant and the absolute rotation needs both.
 *  - `magnetometer_calibration` — the magnetometer's calibration status
 *    (0 unreliable,
 *    1 low, 2 medium, 3 high), and it qualifies the HEADING ONLY. Pitch and
 *    roll come from gravity and the gyro, which magnetometer calibration does
 *    not touch, so a 0 here says nothing against them. Three further caveats,
 *    because this field invites over-reading:
 *      * it is NOT the accuracy of the sample the heading came from. The
 *        default fusion is `TYPE_ROTATION_VECTOR`, which reports its own
 *        accuracy; `EnhancedSensorService` reads that and discards it, and
 *        registers the bare magnetometer alongside purely so its
 *        `onAccuracyChanged` fires. This value is a deliberate proxy.
 *      * it is LATCHED, not per-sample: Android reports only on change, so
 *        the last value is carried onto every later sample indefinitely and
 *        has no age of its own.
 *      * absent means Android never reported it — which is also what a bare
 *        `MODE_ROTATION_VECTOR` run would give, since that mode registers no
 *        magnetometer. (Android's own -1 doubles as NO_CONTACT, so the two
 *        are indistinguishable here; both read as absent, which is honest.)
 *    No column anywhere holds it. Not to be confused with
 *    `location_accuracy_m`, the GPS error radius.
 *  - `fused_sensor_accuracy` — what the sensor that produced the sample said
 *    about ITSELF (`SensorEvent.accuracy`), which is the rating that actually
 *    belongs to this reading. Per-sample, unlike the latched magnetometer
 *    status, and the two can disagree: magnetometer low with fusion high is a
 *    gyro carrying a stale field, the reverse is a fusion that has not settled.
 *    Read and thrown away (a commented-out log line) until 2026-09-22. Absent
 *    from the Madgwick and complementary paths, which compose several raw
 *    sensors and have no single rating to give.
 *  - `fusion` — which filter produced the sample (rotation-vector, Madgwick,
 *    complementary). They disagree, and `bearing_source` is too coarse to
 *    say which was running.
 *  - `age_ms` — how stale the reading was at the shutter, measured like
 *    `location_age_ms` beside it.
 *  - `device_rotation_deg` — the quantized pose. The EXIF Orientation tag is
 *    NOT this: CameraX derives that from the pose combined with the camera's
 *    sensorOrientation and lens facing, so it cannot be inverted back.
 *  - `landscape_azimuth_negation` — whether the Armor-22 toggle was ENABLED.
 *    It negates the azimuth, but only past 90° of roll, so this being true
 *    does not mean it fired on this sample — `roll_deg` beside it is what
 *    tells you. Named for what it does rather than for the phone it was added
 *    for, and recorded always, true or false: absence would be ambiguous.
 *
 * The tracking table holds all of this at sensor rate too — but that table
 * only leaves the phone as a manual CSV export, so for an uploaded photo this
 * is the shutter's row of it, pinned to the frame it describes.
 */
fun attitudeProvenanceJson(s: SensorSnapshot): String? {
    val a = s.attitude
    if (a == null && s.deviceRotationDeg == null && s.compassLandscapeWorkaround == null) return null
    val fields = buildList {
        a?.let {
            add("\"heading_true_deg\":${it.trueDeg}")
            add("\"heading_magnetic_deg\":${it.magneticDeg}")
            add("\"pitch_deg\":${it.pitch}")
            add("\"roll_deg\":${it.roll}")
            it.magnetometerCalibration?.let { add("\"magnetometer_calibration\":$it") }
            it.fusedSensorAccuracy?.let { add("\"fused_sensor_accuracy\":$it") }
            it.detail?.let { d -> add("\"fusion\":\"$d\"") }
            add("\"age_ms\":${s.poseReferenceMs() - it.ts}")
        }
        s.deviceRotationDeg?.let { add("\"device_rotation_deg\":$it") }
        s.compassLandscapeWorkaround?.let { add("\"landscape_azimuth_negation\":$it") }
    }
    return if (fields.isEmpty()) null else fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * How the phone was MOVING at the shutter, as the upload's `motion` provenance
 * object.
 *
 *  - `gravity` — (x, y, z) m/s² in the device frame. An unambiguous "down",
 *    where `attitude.roll_deg` is a residual within the quantized device pose.
 *    Two rotation degrees of freedom with no fusion and no magnetometer in the
 *    way, which is why a reconstruction wants it even though pitch and roll
 *    are already recorded.
 *  - `linear_acceleration` — the same stream with gravity removed, (x, y, z).
 *  - `linear_acceleration_magnitude` — its length, precomputed because it is
 *    the number anything sorting frames by motion blur actually uses.
 *  - `age_ms` — how stale the reading was at the shutter, measured like
 *    `attitude.age_ms` and `location_age_ms`.
 *
 * A single RAW accelerometer sample is deliberately not here: it is gravity
 * plus linear acceleration and one sample cannot separate them, so it is
 * strictly worse than either field above. The honest use for raw inertial data
 * is a time SERIES across the exposure, which lives in the tracking database
 * and travels by CSV — see docs/recon-capture-metadata.md.
 */
/**
 * The instant every `age_ms` in the provenance is measured against.
 *
 * The exposure when the pose was actually looked up there, the press otherwise. Without
 * this, replacing the attitude with a sample taken at the exposure would make
 * `age_ms` — defined as "how stale the reading was at the shutter" — come out NEGATIVE,
 * because the sample is later than the press. One definition, so the attitude, the
 * inertial reading and anything added later cannot disagree about what they are stale
 * relative to.
 */
/*
 * CONTRACT NOTE. With `pose_referenced_to: "exposure"` the provenance's `age_ms` fields
 * become SIGNED offsets from the exposure rather than non-negative ages from the press:
 * the lookup takes the nearest sample on either side, so about half of them land after
 * the shutter and report a negative number, bounded by AT_EXPOSURE_TOLERANCE_NS. Nothing
 * downstream needs changing — a staleness filter reading a negative offset as "fresh" is
 * right — but a reader expecting a non-negative age deserves to have been told.
 */
/*
 * UNGATED ON PURPOSE, 2026-09-28 — it used to return the exposure only when
 * `poseReferencedTo == "exposure"`, i.e. only when BOTH rings answered. That gate made
 * two cases lie in opposite directions:
 *
 *  - rings empty: the attitude is the press-time stamp, and measuring it against the
 *    press reported ~25 ms when the reading was really ~340 ms stale with respect to
 *    its own frame. That is item 1 of docs/todo/captured-at-is-the-exposure.md, still
 *    intact for exactly the captures where the lookup failed.
 *  - MIXED (attitude found, motion not, or the reverse): `poseReferencedTo` fell back to
 *    "press" while the attitude object held an at-exposure sample, so its `age_ms` came
 *    out NEGATIVE by the whole press→exposure gap.
 *
 * The instant the exposure was measured is a fact about the capture, not about whether a
 * lookup succeeded. So: when it is known, every age is measured against it, and
 * `pose_referenced_to` goes back to meaning only what it says — where the pose VALUES
 * came from.
 */
fun SensorSnapshot.poseReferenceMs(): Long =
    captureTiming?.exposureWallMs ?: capturedAtMs

/**
 * `capture_timing` — see [CaptureTiming]. Always emits `captured_at_source`, because a
 * timing object that does not say which instant `captured_at` names would be the very
 * ambiguity it exists to remove.
 */
fun captureTimingJson(s: SensorSnapshot): String? {
    val t = s.captureTiming ?: return null
    val fields = buildList {
        add("\"captured_at_source\":\"${t.capturedAtSource}\"")
        t.pressToExposureMs?.let { add("\"press_to_exposure_ms\":$it") }
        t.exposureToJpegMs?.let { add("\"exposure_to_jpeg_ms\":$it") }
        t.stillMode?.let { add("\"still_mode\":\"$it\"") }
        t.exposureElapsedNs?.let { add("\"exposure_elapsed_ns\":$it") }
        t.exposureWallMs?.let { add("\"exposure_wall_ms\":$it") }
        t.exposureSource?.let { add("\"exposure_source\":\"$it\"") }
        t.poseReferencedTo?.let { add("\"pose_referenced_to\":\"$it\"") }
        // The only field in this object built from strings that did not come from an
        // enum or a number, so it is the only one worth guarding: a version or a dirty
        // hash carrying a quote would otherwise produce a payload the worker drops
        // whole. Sanitised rather than escaped — the label is generated, so anything
        // exotic in it is a bug to see, not text to preserve.
        t.build?.takeIf { it.isNotBlank() }
            ?.map { c -> if (c == '"' || c == '\\') ' ' else c }
            ?.joinToString("")
            ?.let { add("\"build\":\"$it\"") }
    }
    return fields.joinToString(",", prefix = "{", postfix = "}")
}

fun inertialProvenanceJson(s: SensorSnapshot): String? {
    fun floats(v: List<Float>?) = v?.joinToString(",", prefix = "[", postfix = "]")
    val fields = buildList {
        s.motion?.let { m ->
            floats(m.gravity)?.let { add("\"gravity\":$it") }
            m.linearAcceleration?.let { a ->
                floats(a)?.let { add("\"linear_acceleration\":$it") }
                val mag = kotlin.math.sqrt(a.fold(0.0) { acc, v -> acc + v.toDouble() * v })
                add("\"linear_acceleration_magnitude\":$mag")
            }
            // Age of the GRAVITY reading, not of the window — the window carries
            // its own bounds.
            add("\"age_ms\":${s.poseReferenceMs() - m.atMs}")
        }
        // The window stands on its own: a device with no gravity sensor can
        // still have an accelerometer and a gyroscope.
        s.imuWindow?.let { add("\"imu_window\":${imuWindowJson(it)}") }
    }
    // An age with nothing to date describes nothing.
    val onlyAge = fields.size == 1 && fields.single().startsWith("\"age_ms\"")
    return if (fields.isEmpty() || onlyAge) null
    else fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * What the IMU window around the exposure contained, as the `imu_window` half
 * of the `motion` provenance — everything a reader needs to judge the frame
 * WITHOUT opening the samples.
 *
 * The samples travel with the photo now (Phase 5: `imu_samples`, a gzipped
 * artifact at `photos.imu_samples_url`), so this is a summary beside them rather
 * than a pointer to them. It earns its place by being cheap: a reader deciding
 * whether a frame was steady enough to use should not have to fetch and decode
 * tens of kilobytes to find out.
 *
 *  - `sample_count`, `window_start_ms`, `window_end_ms` — what span this
 *    summary describes. NOT a lookup key into the tracking CSVs: nothing looks
 *    an app photo up in those (see `GeoTrackingManager`'s dump — the export
 *    exists for EXTERNAL camera frames, which have no other route).
 *  - `accel_peak_mps2` — peak RAW accelerometer magnitude, gravity included, so
 *    it sits near 9.81 on a still phone. Reported unaltered because it is what
 *    the sensor said.
 *  - `accel_peak_deviation_mps2` — peak |magnitude − g|, which IS the shake
 *    signal and needs no linear-acceleration sensor to compute. Near zero for a
 *    still phone at any orientation, which `accel_peak_mps2` is not.
 *  - `gyro_peak_rad_s` — peak angular rate. Gravity-free by nature, and the one
 *    that catches a rotation about the optical axis, which translation-only
 *    measures miss entirely.
 *
 * Null when no window was captured, which is a fact about the capture and not a
 * gap: a device with no gyroscope, or a map-only activity that never asked.
 */
fun imuWindowJson(w: ImuWindow): String {
    val fields = buildList {
        add("\"sample_count\":${w.sampleCount}")
        add("\"window_start_ms\":${w.startMs}")
        add("\"window_end_ms\":${w.endMs}")
        add("\"stored_count\":${w.storedCount}")
        w.accelPeakMps2?.let { add("\"accel_peak_mps2\":$it") }
        w.accelPeakDeviationMps2?.let { add("\"accel_peak_deviation_mps2\":$it") }
        w.gyroPeakRadS?.let { add("\"gyro_peak_rad_s\":$it") }
    }
    return fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * The camera's calibration and settings, as the upload's `lens` provenance
 * object. See [LensStamp] for what each field means.
 *
 * Numbers are emitted as the platform gave them — no rounding. A reconstruction
 * consuming intrinsics wants the value, not a tidy one, and the places this
 * project does round (a display string, an error bar) round for a reader.
 */
fun lensProvenanceJson(s: SensorSnapshot): String? {
    val l = s.lens ?: return null
    fun floats(v: List<Float>?) = v?.joinToString(",", prefix = "[", postfix = "]")
    fun ints(v: List<Int>?) = v?.joinToString(",", prefix = "[", postfix = "]")
    val fields = buildList {
        l.focalLengthMm?.let { add("\"focal_length_mm\":$it") }
        l.apertureFStop?.let { add("\"aperture_f_stop\":$it") }
        l.focusDistanceDiopters?.let { add("\"focus_distance_diopters\":$it") }
        l.focusDistanceCalibration?.let { add("\"focus_distance_calibration\":\"$it\"") }
        l.focusInfinityRequested?.let { add("\"focus_infinity_requested\":$it") }
        l.zoomRatio?.let { add("\"zoom_ratio\":$it") }
        l.previewRollingShutterSkewNs?.let { add("\"preview_rolling_shutter_skew_ns\":$it") }
        floats(l.intrinsics)?.let { add("\"intrinsics\":$it") }
        floats(l.distortion)?.let { add("\"distortion\":$it") }
        // Which stream the per-shot half above came from, and how far it was from the
        // frame this photo IS. Emitted together, and only when there is something for
        // them to qualify: a lens object carrying nothing but factory calibration has
        // no frame behind it to describe. See LensStamp.previewRollingShutterSkewNs.
        if (
            l.focalLengthMm != null || l.apertureFStop != null ||
            l.focusDistanceDiopters != null || l.previewRollingShutterSkewNs != null ||
            l.intrinsics != null || l.distortion != null
        ) {
            add("\"frame_values_source\":\"preview\"")
            l.frameValuesAtMs?.let { add("\"age_ms\":${s.poseReferenceMs() - it}") }
        }
        floats(l.cameraIntrinsics)?.let { add("\"camera_intrinsics\":$it") }
        floats(l.cameraDistortion)?.let { add("\"camera_distortion\":$it") }
        floats(l.sensorPhysicalSizeMm)?.let { add("\"sensor_physical_size_mm\":$it") }
        ints(l.sensorPixelArray)?.let { add("\"sensor_pixel_array\":$it") }
        l.intrinsicsAvailable?.let { add("\"intrinsics_available\":$it") }
    }
    return if (fields.isEmpty()) null else fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * What the RECEIVER said about its own fix, as the upload's `fix` provenance
 * object — the error bars and the motion, which no column carries.
 *
 * Deliberately NOT the position: latitude, longitude, altitude and the
 * horizontal accuracy are already columns and already in every response, so
 * repeating them here would be the duplication this object exists to avoid.
 * What is here is everything `FixState` used to discard:
 *
 *  - `altitude_accuracy_m` — the VERTICAL error bar. A photo could say its
 *    position was good to 4 m and nothing whatever about its height, which
 *    matters because altitude is part of a camera centre.
 *  - `speed_mps` / `speed_accuracy_mps` — motion at the shutter. A frame shot
 *    at 20 m/s is a different reconstruction candidate from a standing one,
 *    and this is the cheap version of that signal (the expensive one is the
 *    IMU window).
 *  - `course_deg` / `course_accuracy_deg` — the receiver's DIRECTION OF
 *    TRAVEL, which is not a heading: a phone pointed out of a car window has a
 *    course down the road and a heading across it. Car mode composes this into
 *    the bearing; raw, it is also the check on that composition.
 *  - `provider` — "gps" / "network" / "fused". With the fused client this
 *    usually reads "fused" and so discriminates less than it looks, but a
 *    "network" fix is useless for reconstruction and nothing else says so.
 *
 * `elected` is the one judgement here: whether this fix is what the photo
 * actually recorded. Without it a reader cannot tell a quality report about
 * the recorded position from one about a position that lost.
 */
fun fixProvenanceJson(s: SensorSnapshot): String? {
    val f = s.fix ?: return null
    val fields = buildList {
        f.altitudeAccuracyM?.let { add("\"altitude_accuracy_m\":$it") }
        f.speedMps?.let { add("\"speed_mps\":$it") }
        f.speedAccuracyMps?.let { add("\"speed_accuracy_mps\":$it") }
        f.courseDeg?.let { add("\"course_deg\":$it") }
        f.courseAccuracyDeg?.let { add("\"course_accuracy_deg\":$it") }
        f.provider?.let { add("\"provider\":\"$it\"") }
        add("\"elected\":${s.locationSource == "gps"}")
    }
    // `elected` alone says nothing worth a row of its own.
    return if (fields.size <= 1) null else fields.joinToString(",", prefix = "{", postfix = "}")
}

/**
 * Which stream rides along as the alternative — the swap rule.
 *
 * Two streams exist: the receiver's fix and the map's centre. One is
 * primary (what the photo records), and the OTHER is worth keeping when
 * they differ. The original swaps them the moment the map is panned; here
 * (user-decided) the swap waits for the claim, so the pre-claim state —
 * exploring, prompt showing, fix still primary — is one the original never
 * has, and the rule extends to it symmetrically: the un-claimed map
 * position rides along, tagged so nobody mistakes it for a measurement.
 *
 * - claimed: primary = map, alt = the live fix, `gps-background` — the
 *   original's exact case;
 * - exploring, unclaimed, a fix present: primary = fix, alt = the map
 *   position, `map-unclaimed`;
 * - following: the streams are one stream; nothing to keep;
 * - no fix: the map centre IS the primary (docs/one-state.md, "The position
 *   side"), so there is no other stream to keep — whatever the tracking
 *   mode. The old no-fix hatch reached this row through `manualElected`;
 *   now it is simply the row a missing fix lands in.
 */
fun altLocationFor(
    manualElected: Boolean,
    exploring: Boolean,
    fix: AltLocation?,
    mapPosition: AltLocation?,
): AltLocation? = when {
    fix == null -> null
    manualElected -> fix
    exploring -> mapPosition
    else -> null
}

/** The primary position a capture records, and the word that says which stream it was. */
data class StampPosition(
    val latitude: Double,
    val longitude: Double,
    /** `gps` or `map` — the original's contract; see docs/one-state.md. */
    val source: String,
    val altitude: Double? = null,
    val accuracyM: Float? = null,
    /** Age of the fix at the shutter; null for a map position, which has no age. */
    val fixAgeMs: Long? = null,
)

/**
 * WHICH record a photo takes its position from — the table in
 * docs/one-state.md, "The position side", and nothing else:
 *
 *   fix | pan | claimed | primary
 *   yes | any | no      | fix, `gps`
 *   yes | yes | yes     | pan, `map`
 *   no  | yes | —       | pan, `map`
 *   no  | no  | —       | none — null, and meant
 *
 * A "pan" is the map centre once someone has put the map somewhere:
 * [ManualLocation.atMs] is null on a blank first run (SpatialState.ts), and
 * that is the one case a photo records no position. A claim with no such
 * pan cannot happen (the pill claims a placed map) and falls through to the
 * fix rather than to nothing.
 *
 * No arbitration on freshness, deliberately: a stale fix is still the fix,
 * its age rides along in [StampPosition.fixAgeMs] and downstream filters.
 * Which stream is primary is decided in the UI, where it can be seen and
 * withdrawn; this function only reports the decision.
 */
fun stampPosition(
    fix: cz.hillview.map.FixState?,
    fixAgeMs: Long?,
    pan: ManualLocation?,
    claimed: Boolean,
): StampPosition? {
    val placed = pan?.takeIf { it.atMs != null }
    return when {
        claimed && placed != null -> StampPosition(placed.latitude, placed.longitude, "map")
        fix != null -> StampPosition(
            fix.latitude, fix.longitude, "gps", fix.altitude, fix.accuracyM, fixAgeMs,
        )
        placed != null -> StampPosition(placed.latitude, placed.longitude, "map")
        else -> null
    }
}

/**
 * The bearing a capture stamps — Tauri's known-good semantics: photos
 * carry the MAP's bearing state (the arrow), whatever currently owns it:
 * walking's compass, car mode's gps-kalman course + mount offset, or a
 * hand-set arrow. NOT the raw compass (that was the car-mode bug).
 */
/**
  * The one state's answer, handed to the capture pane: what a photo taken
  * now records. Everything the stamp needs travels together, because it is
  * one answer — the pane reads no sensor of its own.
  */
data class StampBearing(
    val trueDeg: Float,
    val source: String,
    val magneticDeg: Double? = null,
    val pitch: Double? = null,
    val accuracyLevel: Int? = null,
)

/**
 * The shutter's only gate is camera readiness (2026-09-09).
 *
 * It used to require a fix or a lifted gate: "a photo mapping app's photos
 * must land somewhere". They still do — with no fix the map centre is what
 * a photo records, tagged `map`, and its age and provenance travel with it
 * so downstream can filter. Refusing the press protected nothing the stamp
 * does not now say outright, and it read a stored "fresh" that could never
 * go false (see CaptureState.hasFix), so the protection was not even real.
 * docs/one-state.md, "The position side" and "Derived, not stored".
 */
fun shutterEnabled(ready: Boolean): Boolean = ready

/**
 * Whether a press on the shutter does anything at all — what the button's
 * enabled state and its accessibility click both answer.
 *
 * STOPPING is unconditional. The location gate exists to withhold a capture
 * that would have no position; it has no business withholding the end of
 * one. It used to sit in front of everything, so a fix lost mid-recording
 * left the recording unstoppable — every press answered "no GPS fix" — and
 * the same trap held a repeating run.
 */
fun shutterPressDoesSomething(
    recording: Boolean,
    repeating: Boolean,
    gateOpen: Boolean,
    capturing: Boolean,
): Boolean = recording || repeating || (gateOpen && !capturing)

@Stable
interface PhotoCapture {
    val state: CaptureState

    /**
     * The map centre, live — the position's other record. A capture is
     * stamped with it while it is elected over a fix ([manualLocationElected])
     * and whenever there is no fix at all; tagged location_source "map"
     * either way. Its [ManualLocation.atMs] is null only on a blank first
     * run (nobody has put the map anywhere), which is the one case a photo
     * records no position.
     */
    var manualLocation: ManualLocation?

    /**
     * The receiver's latest fix, pushed live by the capture screen from the
     * one state's `lastFix` — the same shape as [stampBearing]. Null until
     * the first fix of the session. The pane reads no location of its own:
     * this is where its fix comes from, and the only place.
     */
    var stampFix: cz.hillview.map.FixState?

    /**
     * True while the user has said "I am at the map position, not at my fix"
     * through the pill's accepted claim — the ONE deliberate act that elects
     * the map position over a fix. (The capture pane's no-fix hatch used to
     * be a second; it went when a missing fix stopped needing a button.)
     *
     * It replaced a rule that let a merely STALE fix hand over to the map
     * position with nothing said. An election has to be something the user
     * made — a silent hand-over makes the recorded election a lie, and a lie
     * there is worse than a wrong-but-honest answer, because the whole point
     * of recording it is to be able to re-judge the choice afterwards.
     */
    var manualLocationElected: Boolean

    /**
     * Location tracking is BACKGROUND: the map is parked somewhere the fix
     * is not, and the user has not (yet) claimed it. Mirrored from
     * MapSession by the screen, like [manualLocationElected], so a shutter
     * press can apply [altLocationFor] without reaching for session state.
     */
    var exploring: Boolean

    /**
     * How the shutter is chosen, null = auto exposure. Only honoured when
     * [CaptureState.manualShutterSupported]; ISO follows via [planExposure]
     * so brightness tracks what the metering last saw.
     */
    var exposureRule: ExposureRule?

    /**
     * Re-meter before a shot: hand AE the camera back for a few frames,
     * take its reading, and re-apply the rule against it.
     *
     * A rule turns AE OFF, which means the reading it scales from is
     * frozen at whatever the scene was when the rule was chosen — pan from
     * shade into sun and nothing recomputes. Interval capture is where
     * that hurts (nobody is watching the preview to notice) and also where
     * it is cheap to fix: we own the clock between shots, and a few
     * hundred ms of AE inside a multi-second interval costs nothing but a
     * visible pump in the preview.
     *
     * Suspends until the rule is back in force, so the shot that follows
     * is taken under it. No-op under auto exposure.
     *
     * Since metering went continuous (SceneMeter, 2026-08-11) the window
     * above is the FALLBACK for hardware that refused the analysis stream:
     * with a current scene estimate this returns at once, so it costs an
     * interval run nothing and a manual tap never calls it at all.
     */
    suspend fun prepareExposure()

    /**
     * The map bearing state, pushed live by the capture screen — what a
     * capture stamps and the pill shows (see [StampBearing]).
     */
    var stampBearing: StampBearing?

    /**
     * The one state's attitude record, pushed live by the capture screen —
     * what the DEVICE measured, beside [stampBearing]'s what-it-faces.
     * Same shape and same rule as [stampFix]: the pane reads no sensor of
     * its own, this is where the reading comes from. See
     * [SensorSnapshot.attitude].
     */
    var stampAttitude: cz.hillview.map.DeviceAttitude?

    /**
     * The one state's inertial record, pushed live by the capture screen —
     * gravity and linear acceleration. Same rule as [stampAttitude]: the pane
     * reads no sensor of its own.
     */
    var stampMotion: cz.hillview.map.DeviceMotionSample?

    /**
     * Whether the Armor-22 landscape heading workaround is on, mirrored from
     * the compass settings by the screen (the same way
     * [manualLocationElected] is mirrored from the session). It changes what
     * a heading MEANS, so it travels with the heading — see
     * [SensorSnapshot.compassLandscapeWorkaround].
     */
    var compassLandscapeWorkaround: Boolean

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

    /**
     * How a still is taken and how hard the JPEG is squeezed — see
     * [StillCaptureMode]. Both are ImageCapture BUILD options, so a change
     * rebinds the camera exactly like [selectResolution]; the applied pair
     * lands in [CaptureState.stillCaptureMode] / [CaptureState.jpegQuality].
     */
    fun configureStill(mode: StillCaptureMode, jpegQuality: Int)

    fun capture()

    /**
     * Video is a MODALITY of this pane, not a separate screen — "almost
     * just a 0-interval photo capture" (user, 2026-08-09). Chosen from the
     * top of the shutter's interval ladder, so it rides the same one-finger
     * grammar as starting a run.
     *
     * The mp4 streams straight into the photo folder, and a SIDECAR lands
     * beside it carrying what the container cannot: a per-frame log of
     * sensor timestamps, so a later consumer can pair frames to real time
     * (MPEG4Writer rebases presentation timestamps to ~0, and CameraX
     * rewrites the timebase before the encoder — see the per-frame metadata
     * research in frontend2-capture-backlog.md).
     */
    fun startVideo()

    /** Stop and finalize; the sidecar is written as the file closes. */
    fun stopVideo()

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
