package cz.hillview.plugin

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.sqrt

/**
 * Where the LENS points, derived from a rotation matrix by transforming the camera axis
 * — not by reading Euler angles out of a remapped frame.
 *
 * WHY THIS EXISTS. `SensorManager.getOrientation` answers a different question: "how is
 * the phone tilted", as Euler angles, whose azimuth is the direction the TOP OF THE
 * PHONE points projected onto the horizontal plane. For a phone held upright that
 * projection is degenerate, which is why the old code had to call
 * `remapCoordinateSystem` first, keyed on a QUANTIZED orientation class
 * (PORTRAIT / LANDSCAPE_LEFT / LANDSCAPE_RIGHT), and then patch the result with two
 * `if (abs(roll) > 90)` branches, one of them commented `// magic`.
 *
 * That scheme was measured against gravity on 2026-10-03 and it fails in two ways,
 * both explained by the quantized key:
 *
 *  - LANDSCAPE: the portrait remap sends the device's Y axis to world Z (up), which is
 *    the "phone is upright" part. Neither landscape remap sends anything to Z — they
 *    are in-plane rotations about the screen normal. So the frame handed to
 *    `getOrientation` has no axis near world up, its pitch pins near ∓90 and its roll
 *    goes ill-conditioned: across one up/level/down sweep the published `pitch_deg` read
 *    −56.7 / −84.4 / −68.0 (not even monotonic) where gravity said −33.7 / −4.4 / +21.8,
 *    and `roll_deg` flipped −176.8 → +2.7 between consecutive frames. Worse, the two
 *    correction branches are keyed on exactly that degenerate `roll`, so whether they
 *    fire is decided by an ill-conditioned number.
 *  - MID-ROLL: the orientation classifier only calls it landscape from 45°, so at a roll
 *    of 38° the PORTRAIT remap is applied to a rolled phone. Three deliberate ~40°
 *    captures came out 43–52° off their own un-rolled neighbours, the error tracking the
 *    roll angle.
 *
 * A vector transform has no quantized key, no orientation class and no step functions.
 * It is continuous through every pose, and the only place it degenerates is where the
 * question itself does: a lens pointed straight up or down has no bearing. See
 * [horizontalLength] for how a caller knows it is there.
 *
 * THE CONVENTIONS, all three chosen to match what the app already publishes so that
 * portrait output does not move (verified: portrait `pitch_deg` agrees with the
 * gravity-derived value to ≤0.8° on real captures, so this is a no-op there):
 *  - [bearingDeg] degrees clockwise from the matrix's north, 0..360;
 *  - [pitchDeg] POSITIVE when the camera looks DOWN — the existing sign, not elevation;
 *  - [imageRollDeg] 0 when the screen's up is world up, ±90 in landscape.
 */
data class CameraPose(
    val bearingDeg: Float,
    val pitchDeg: Float,
    val imageRollDeg: Float,
    /**
     * How well-conditioned [bearingDeg] is: the length of the camera axis's horizontal
     * projection, 1 with the lens level and 0 with it pointed at the sky or the ground.
     *
     * A number rather than a hidden singularity. At 0 the bearing is not merely
     * imprecise, it does not exist — `atan2(0, 0)` returns 0, so an unguarded caller
     * would publish "due north" for a photo of the ceiling. It equals cos(elevation), so
     * a caller can also read it as "how much of the aim is horizontal".
     */
    val horizontalLength: Float,
)

/**
 * Below this, [CameraPose.bearingDeg] should not be believed: the lens is within ~3° of
 * vertical, and the horizontal projection it is derived from is under 5 % of full
 * length. Chosen as a round 0.05 rather than fitted to anything — the point is to have a
 * threshold at all, where the previous code had an unmarked singularity.
 */
const val BEARING_CONDITION_FLOOR = 0.05f

/**
 * [CameraPose] from a row-major 3x3 device→world rotation matrix, as
 * `SensorManager.getRotationMatrixFromVector` produces it: world is (East, North, Up).
 *
 * Null when the matrix is not one — all zeros before the first sample, or a wrong-sized
 * array. Null rather than a plausible pose, because a zero matrix would otherwise read
 * as a level camera facing north.
 */
fun cameraPoseFromRotationMatrix(r: FloatArray): CameraPose? {
    if (r.size < 9) return null
    // The rear camera looks along the device's -Z. In world coordinates that is minus
    // the matrix's third COLUMN, which for a row-major 3x3 is r[2], r[5], r[8].
    val east = -r[2]
    val north = -r[5]
    val up = -r[8]
    val horizontal = sqrt(east * east + north * north)
    val norm = sqrt(horizontal * horizontal + up * up)
    // A real rotation matrix's columns are unit length. Anything far off is not one.
    if (norm < 0.5f || norm > 2f) return null
    val upUnit = (up / norm).coerceIn(-1f, 1f)
    return CameraPose(
        bearingDeg = ((Math.toDegrees(atan2(east, north).toDouble()).toFloat() % 360f) + 360f) % 360f,
        // Positive = looking DOWN, so it is the negated elevation. Identical to
        // asin(gravityZ / |gravity|), which is how it was checked against real captures.
        pitchDeg = -Math.toDegrees(asin(upUnit).toDouble()).toFloat(),
        // World up expressed in DEVICE coordinates is the matrix's third ROW; its x and
        // y are how far the horizon is rotated within the image.
        imageRollDeg = Math.toDegrees(atan2(r[6], r[7]).toDouble()).toFloat(),
        horizontalLength = horizontal / norm,
    )
}

/** Whether [CameraPose.bearingDeg] is worth publishing — see [BEARING_CONDITION_FLOOR]. */
fun CameraPose.bearingIsDefined(): Boolean = horizontalLength >= BEARING_CONDITION_FLOOR

/** Shortest signed difference b − a, degrees, in (−180, 180]. Wraparound-safe. */
internal fun signedDegreeDelta(a: Float, b: Float): Float {
    var d = (b - a) % 360f
    if (d > 180f) d -= 360f
    if (d <= -180f) d += 360f
    return d
}

/** True when [a] and [b] are within [toleranceDeg] of each other on the circle. */
internal fun degreesClose(a: Float, b: Float, toleranceDeg: Float): Boolean =
    abs(signedDegreeDelta(a, b)) <= toleranceDeg
