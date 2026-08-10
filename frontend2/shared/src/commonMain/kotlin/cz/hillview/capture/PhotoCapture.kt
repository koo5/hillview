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

/** What the ⚡ button says: the rule in one glance, bias included. */
fun exposureLabel(rule: ExposureRule?): String {
    if (rule == null) return "Auto"
    val time = formatShutter(rule.targetNs)
    val head = when (rule.mode) {
        ExposureMode.Pin -> "=$time"
        ExposureMode.Floor -> "≥$time"
        ExposureMode.Sports -> "🏃$time"
    }
    return if (rule.evBias == 0.0) head else "$head ${formatEvBias(rule.evBias)}EV"
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
fun shutterEnabled(ready: Boolean, hasFix: Boolean, mapPositionElected: Boolean): Boolean =
    ready && (hasFix || mapPositionElected)

@Stable
interface PhotoCapture {
    val state: CaptureState

    /**
     * The map position a capture is stamped with while it is elected — see
     * [manualLocationElected]. Tagged location_source "manual".
     */
    var manualLocation: ManualLocation?

    /**
     * True while the user has said "I am at the map position", by either of
     * the two deliberate acts that mean it: the pill's accepted claim, or the
     * no-fix escape hatch in the capture pane.
     *
     * It replaced a rule that let a merely STALE fix hand over to the map
     * position with nothing said. An election has to be something the user
     * made — a silent hand-over makes the recorded election a lie, and a lie
     * there is worse than a wrong-but-honest answer, because the whole point
     * of recording it is to be able to re-judge the choice afterwards.
     */
    var manualLocationElected: Boolean

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
     */
    suspend fun prepareExposure()

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
