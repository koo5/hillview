package cz.hillview.capture

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.sqrt

/**
 * The saved image's elevation, positive up, from the pose it actually carries.
 * Matches capture_pose.py: gravity wins, then the measured attitude. The
 * elected bearing's pitch can be old when only tilt changed, or absent after
 * a manual heading; it is not a measurement of this frame.
 *
 * Read from the completed snapshot so an at-exposure lookup takes precedence
 * over the press-time pose, exactly as it does in the upload's provenance.
 */
fun SensorSnapshot.measuredPitchDeg(): Double? {
    val gravity = motion?.gravity
    if (gravity?.size == 3 && gravity.all { it.isFinite() }) {
        val g = gravity.map { it.toDouble() }
        val norm = sqrt(g.sumOf { it * it })
        if (norm > 0 && norm.isFinite()) {
            return -asin((g[2] / norm).coerceIn(-1.0, 1.0)) * 180.0 / PI + 0.0
        }
    }
    return attitude?.pitch?.takeIf { it.isFinite() && abs(it) <= 90.0 }?.plus(0.0)
}
