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
    val manualPositionClaimed: Boolean = false,
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
        }
        append(" · ")
        append(if (input.bearingMode == BearingMode.Car) "car" else "walk")
        append(" · want ")
        append(if (input.bearingWanted) "ON" else "OFF")
        append(" · ")
        append(input.bearingPhase.name)
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
