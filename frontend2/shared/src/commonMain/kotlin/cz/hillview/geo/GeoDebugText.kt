package cz.hillview.geo

import cz.hillview.map.BearingMode
import cz.hillview.map.BearingState
import cz.hillview.map.LocationTracking
import cz.hillview.map.SpatialState
import cz.hillview.map.TrackingPhase
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * The geo chain, in three lines, for when a readout looks wrong.
 *
 * The bug that motivated this took an emulator, adb and a morning to pin
 * down, and the whole finding was that two numbers on screen were not the
 * same number: the external-camera pane prints the ENGINE's raw heading
 * (always live), while the capture pill and the map arrow print the
 * ELECTED bearing (written only while something is driving it). Nothing
 * on screen said which was which, or when either was last written, so
 * "stuck" was indistinguishable from "off" and from "nothing is
 * listening".
 *
 * So the readout answers exactly those questions, in this order:
 * what the app's value is, who wrote it, HOW LONG AGO, and what the
 * plumbing behind it is doing. An age climbing past a few seconds while
 * the raw line keeps moving is the whole diagnosis at a glance.
 *
 * Pure so it can be tested; rendered as plain mono lines by the panes.
 */
data class GeoDebugInput(
    val bearing: BearingState,
    val spatial: SpatialState,
    val bearingWanted: Boolean,
    val bearingPhase: TrackingPhase,
    val bearingMode: BearingMode,
    val locationTracking: LocationTracking,
    /** The engine's own heading, before election — null if it never read. */
    val rawHeadingDeg: Double? = null,
    val rawAccuracy: Int? = null,
    /**
     * When the engine last DELIVERED a reading, which is not when the
     * elected bearing was last WRITTEN: the map only writes past a 1°
     * dead-band, so a still phone legitimately shows a minutes-old elected
     * age. Without this second age the readout cannot tell that apart from
     * a chain that stopped, which is the one thing it exists to do.
     */
    val rawAtMs: Long? = null,
    /** Which fusion mode produced the raw reading (OrientationSensorData.detail). */
    val rawDetail: String? = null,
    /**
     * How long the sensor has been REPEATING one attitude sample. Events
     * still arriving (a fresh rawAtMs) while this climbs is a registration
     * that died without going silent — the heading then answers only to the
     * device-orientation remap, which is what "it alternates between two
     * values depending on how I hold it" looks like from the outside.
     */
    val rawStillMs: Long? = null,
    /**
     * The device-orientation class the sensor stack's remap is keyed on.
     * Shown because a heading that moves only when THIS moves is a frozen
     * attitude sample being remapped four ways — the fault reads as "the
     * compass alternates between a couple of values depending on how I hold
     * the phone", and this is the line that says so.
     */
    val devicePose: String? = null,
    val manualPositionClaimed: Boolean = false,
    /**
     * When the map overlay was last HANDED a bearing, and which one.
     *
     * The arrow is drawn by osmdroid from a value the AndroidView update
     * block writes, so it can go stale in a way no other readout can: the
     * elected bearing keeps moving, every Compose readout follows it, and
     * the arrow sits still because the block that copies one into the other
     * has stopped running. Coroutine-driven work (the GPS follow) keeps
     * going meanwhile, which is why the map still pans while the arrow is
     * frozen — the symptom that sends you looking at the sensors, wrongly.
     */
    val arrowSetAtMs: Long? = null,
    val arrowValueDeg: Double? = null,
    val nowMs: Long,
)

fun geoDebugLines(input: GeoDebugInput): List<String> = listOf(
    buildString {
        append("🧭 ")
        append(deg(input.bearing.bearing))
        append(' ')
        append(input.bearing.source)
        append(' ')
        append(age(input.bearing.ts, input.nowMs))
        input.bearing.photoUid?.let { append(" uid:${it.take(8)}") }
    },
    buildString {
        append("   raw ")
        append(input.rawHeadingDeg?.let { deg(it) } ?: "—")
        append(" acc")
        append(input.rawAccuracy?.toString() ?: "—")
        input.rawDetail?.let { append("/${compactDetail(it)}") }
        // The delta is the tell: raw moving while elected does not is a
        // stalled chain, not a stuck sensor.
        if (input.rawHeadingDeg != null) {
            append(" Δ")
            append(deg(shortestDelta(input.rawHeadingDeg, input.bearing.bearing)))
            append(' ')
            append(age(input.rawAtMs, input.nowMs))
            // Two ages again, and for the same reason as the elected line:
            // arriving is not moving.
            input.rawStillMs?.let { append(" still ${age(input.nowMs - it, input.nowMs)}") }
        }
        append(" · ")
        append(if (input.bearingMode == BearingMode.Car) "car" else "walk")
        append(" · want ")
        append(if (input.bearingWanted) "ON" else "OFF")
        append(" · ")
        append(input.bearingPhase.name)
        input.devicePose?.let { append(" · ${it.take(9)}") }
    },
    buildString {
        append("📍 ")
        append(coord(input.spatial.latitude))
        append(',')
        append(coord(input.spatial.longitude))
        append(' ')
        append(input.spatial.source)
        append(' ')
        append(age(input.spatial.ts, input.nowMs))
        append(" · ")
        append(input.locationTracking.name.uppercase())
        if (input.manualPositionClaimed) append(" · claimed")
    },
    buildString {
        append("🗺 arrow ")
        if (input.arrowSetAtMs == null) {
            append("never set")
        } else {
            append(age(input.arrowSetAtMs, input.nowMs))
            input.arrowValueDeg?.let { append(" @${deg(it)}") }
            // The gap that names the fault: the overlay is holding a bearing
            // the state has moved on from.
            input.arrowValueDeg?.let {
                append(" Δ${deg(shortestDelta(it, input.bearing.bearing))}")
            }
        }
    },
)

/**
 * Ages are the point of the readout, so they stay readable all the way out:
 * sub-minute in tenths, then whole seconds, then minutes. "never" is its own
 * answer — a source that has not written once is a different fault from one
 * that wrote and stopped.
 */
private fun age(ts: Long?, nowMs: Long): String {
    if (ts == null) return "never"
    val ms = nowMs - ts
    // The clock this is compared against ticks twice a second, so a reading
    // that lands between ticks is legitimately "newer than now". Only a
    // real disagreement between clocks earns a question mark.
    if (ms < 0) return if (ms > -5_000) "0.0s" else "?"
    return when {
        ms < 10_000 -> "${(ms / 100) / 10.0}s"
        ms < 90_000 -> "${ms / 1000}s"
        else -> "${ms / 60_000}m"
    }
}

private fun deg(value: Double): String = "${(value * 10).roundToInt() / 10.0}°"

private fun coord(value: Double): String = ((value * 1_000_000).roundToInt() / 1_000_000.0).toString()

private fun shortestDelta(from: Double, to: Double): Double {
    val diff = ((to - from + 540) % 360) - 180
    return abs(diff)
}

/**
 * The sensor stack's detail is a sentence ("TYPE_ROTATION_VECTOR (UPRIGHT
 * MODE) (EMA smoothed)"), which is right for a log row and wrong for a line
 * that has to fit next to four other facts. Keep the two parts that change
 * between devices and modes — the sensor and the fusion mode — and drop the
 * prose: "ROTATION_VECTOR·UPRIGHT".
 */
internal fun compactDetail(detail: String): String {
    val sensor = detail.substringBefore(' ').removePrefix("TYPE_")
    val mode = detail.substringAfter('(', "").substringBefore(')', "")
        .substringBefore(' ')
        .takeIf { it.isNotBlank() }
    return if (mode == null) sensor else "$sensor·$mode"
}
