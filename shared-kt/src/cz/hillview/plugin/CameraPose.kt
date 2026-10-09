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
    /**
     * The bearing of the device's TOP EDGE — where the +Y axis points, projected
     * horizontally. The reference a map wants when the phone is lying on a table.
     *
     * It exists because the two references are COMPLEMENTARY, not rival. Held up to
     * shoot, the lens is horizontal and the top edge points at the sky, so
     * [bearingDeg] is the well-conditioned one. Flat on a table, the lens points at the
     * table and the top edge is horizontal, so this one is. The old `getOrientation`
     * path published exactly this (its azimuth IS the top edge's direction), which is
     * why it kept working on a desk and why its orientation classifier had a FLAT case
     * with "no remapping needed" — unremapped, it was already the right answer there.
     * Replacing it with the camera bearing alone fixed photos and broke the map.
     */
    val deviceBearingDeg: Float,
    /** How well-conditioned [deviceBearingDeg] is — see [horizontalLength]. */
    val deviceHorizontalLength: Float,
    /**
     * THE ONE TO PUBLISH: the camera bearing wherever the lens is meaningfully off
     * vertical, the top edge's where it is not, blended across the band between.
     *
     * The camera DOMINATES rather than sharing, and that is the whole design. In
     * landscape held upright BOTH axes are horizontal, so a blend weighted by
     * conditioning alone would split the difference and skew the bearing by up to 45° —
     * which is the mid-roll bug in a new costume. So the weight is driven by the
     * camera's conditioning only, and the top edge is a fallback, never a partner.
     *
     * The thresholds are not arbitrary. The device's +Y and −Z are orthogonal unit
     * vectors, so their vertical components satisfy u_y² + u_z² ≤ 1, hence
     * hc² + hd² ≥ 1 and **max(hc, hd) ≥ 1/√2 ≈ 0.707 always**. Taking that bound as
     * the point where the camera stops being trusted alone guarantees the fallback is
     * itself well-conditioned whenever it is reached: there is no posture in which both
     * references are bad.
     */
    val pointingBearingDeg: Float,
) {
    /**
     * Which reference [pointingBearingDeg] came from — "camera", "device" or "blend".
     *
     * Deliberately NOT a provenance field, because it does not need to be: the weight is
     * a function of the camera's conditioning, which is a function of [pitchDeg], which
     * every photo already carries. A consumer recovers it exactly —
     * `|pitch_deg| < 45` is "camera", `> 75` is "device", between is "blend" — so
     * nothing is hidden and the four-list tax is not paid for a derived value.
     */
    val bearingReference: String
        get() = when (cameraWeight(horizontalLength)) {
            1f -> "camera"
            0f -> "device"
            else -> "blend"
        }
}

/**
 * Full trust in the camera bearing at or above this horizontal length — the lens within
 * 45° of level, which covers every posture a photo is taken from, landscape included.
 * Also the provable crossover: at this value the top edge is guaranteed conditioned too.
 */
const val CAMERA_REFERENCE_FULL_AT = 0.707f

/** No trust below this — the lens within ~15° of vertical, i.e. the phone flat. */
const val CAMERA_REFERENCE_NONE_BELOW = 0.259f

/** The camera bearing's share of [CameraPose.pointingBearingDeg], 0..1. */
internal fun cameraWeight(cameraHorizontal: Float): Float = when {
    cameraHorizontal >= CAMERA_REFERENCE_FULL_AT -> 1f
    cameraHorizontal <= CAMERA_REFERENCE_NONE_BELOW -> 0f
    else -> (cameraHorizontal - CAMERA_REFERENCE_NONE_BELOW) /
        (CAMERA_REFERENCE_FULL_AT - CAMERA_REFERENCE_NONE_BELOW)
}

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
    // The device's +Y axis — the top edge — is the matrix's second COLUMN.
    val devEast = r[1]
    val devNorth = r[4]
    val devHorizontal = sqrt(devEast * devEast + devNorth * devNorth)
    val hc = horizontal / norm
    val w = cameraWeight(hc)
    // Blend as VECTORS, each normalised first so the weight is the only thing deciding;
    // adding the raw projections would weight by conditioning twice. A term whose axis
    // is vertical contributes nothing and is skipped rather than dividing by ~zero.
    var blendEast = 0f
    var blendNorth = 0f
    if (w > 0f && horizontal > 1e-6f) {
        blendEast += w * east / horizontal
        blendNorth += w * north / horizontal
    }
    if (w < 1f && devHorizontal > 1e-6f) {
        blendEast += (1f - w) * devEast / devHorizontal
        blendNorth += (1f - w) * devNorth / devHorizontal
    }
    fun deg(e: Float, n: Float) =
        ((Math.toDegrees(atan2(e, n).toDouble()).toFloat() % 360f) + 360f) % 360f
    return CameraPose(
        bearingDeg = deg(east, north),
        // Positive = looking DOWN, so it is the negated elevation. Identical to
        // asin(gravityZ / |gravity|), which is how it was checked against real captures.
        pitchDeg = -Math.toDegrees(asin(upUnit).toDouble()).toFloat(),
        // World up expressed in DEVICE coordinates is the matrix's third ROW; its x and
        // y are how far the horizon is rotated within the image.
        imageRollDeg = Math.toDegrees(atan2(r[6], r[7]).toDouble()).toFloat(),
        horizontalLength = hc,
        deviceBearingDeg = deg(devEast, devNorth),
        deviceHorizontalLength = devHorizontal,
        // Both axes vertical is impossible for an orthogonal pair, so this only guards
        // a matrix that is not a rotation; the camera bearing then stands.
        pointingBearingDeg = if (blendEast == 0f && blendNorth == 0f) {
            deg(east, north)
        } else {
            deg(blendEast, blendNorth)
        },
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
