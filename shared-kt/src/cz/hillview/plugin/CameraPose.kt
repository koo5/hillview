package cz.hillview.plugin

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
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
    /**
     * `det(R)` — +1 for a proper rotation, −1 for a mirrored frame.
     *
     * A DIAGNOSTIC, not a value anything consumes. It is here because a reversal was
     * reported that the maths above cannot produce: every expression in this function is
     * unconditional, so a symptom confined to one region of the sphere has to be in the
     * matrix rather than in what is computed from it. This splits "the HAL handed us
     * something that is not a rotation at all", which a negation would genuinely
     * compensate, from "a rotation, but pointing the wrong way", which it would not.
     */
    val determinant: Float,
    /** The lens direction in world coordinates — (east, north, up), unit length. */
    val lensEast: Float,
    val lensNorth: Float,
    val lensUp: Float,
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
        get() {
            val w = cameraWeight(horizontalLength)
            val fallback = (1f - w) * abs(cos(Math.toRadians(imageRollDeg.toDouble())).toFloat())
            return when {
                w >= 1f || fallback <= 0f -> "camera"
                w <= 0f -> "device"
                else -> "blend"
            }
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
    //
    // THE FALLBACK IS SCALED BY HOW CO-DIRECTIONAL IT ACTUALLY IS, which is the
    // correction to a wrong assumption: that the top edge is usable whenever the lens
    // degenerates. It is — in PORTRAIT, where tilting the phone forward swings both the
    // lens and the top edge toward the same horizontal direction. In LANDSCAPE the top
    // edge points 90° away from the lens and stays there, so any fallback weight at all
    // drags the bearing toward that 90°. Measured on the phone as "landscape still jumps
    // by about 90 degrees" (user, 2026-10-10), and reproducible on paper: at 60° of lens
    // tilt the old weighting gave 40.7° of error, at 75° a full 90°.
    //
    // |cos(imageRoll)| is exactly that co-directionality: 1 upright, 0 in landscape. So
    // the fallback contributes only to the extent that the top edge points where the
    // lens does, and in landscape it contributes nothing — leaving a vertical lens with
    // no bearing, which is the honest answer rather than a confident wrong one.
    val rollRad = atan2(r[6], r[7])
    val fallbackWeight = (1f - w) * abs(cos(rollRad))
    var blendEast = 0f
    var blendNorth = 0f
    if (w > 0f && horizontal > 1e-6f) {
        blendEast += w * east / horizontal
        blendNorth += w * north / horizontal
    }
    if (fallbackWeight > 0f && devHorizontal > 1e-6f) {
        blendEast += fallbackWeight * devEast / devHorizontal
        blendNorth += fallbackWeight * devNorth / devHorizontal
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
        imageRollDeg = Math.toDegrees(rollRad.toDouble()).toFloat(),
        horizontalLength = hc,
        deviceBearingDeg = deg(devEast, devNorth),
        deviceHorizontalLength = devHorizontal,
        // A MAGNITUDE test, not a test against exact zero, and the difference is a bug
        // this had: `cos(90°)` in Float is −4.4e-8 rather than 0, so in landscape with
        // the lens vertical the blend became a vector of length ~1e-8 pointing at the top
        // edge — and `atan2` does not care how long its arguments are. It returned the
        // full 90° error the co-directional weighting was added to remove.
        //
        // The weights sum to at most 1 over unit vectors, so a length this small means no
        // term contributed anything. The camera bearing then stands, ill-conditioned and
        // saying so through [CameraPose.horizontalLength], which beats a confident lie.
        pointingBearingDeg = if (sqrt(blendEast * blendEast + blendNorth * blendNorth) < 1e-3f) {
            deg(east, north)
        } else {
            deg(blendEast, blendNorth)
        },
        determinant = r[0] * (r[4] * r[8] - r[5] * r[7]) -
            r[1] * (r[3] * r[8] - r[5] * r[6]) +
            r[2] * (r[3] * r[7] - r[4] * r[6]),
        lensEast = east / norm,
        lensNorth = north / norm,
        lensUp = upUnit,
    )
}

/**
 * Beyond this much image roll the device counts as being held in landscape, for the
 * purposes of [MIRRORED_AZIMUTH_PHONES] below.
 *
 * 60° is a measured split rather than a chosen one: every pair in the prod data at
 * |roll| > 60 with the lens above the horizon had a mirrored azimuth, and every pair
 * under it did not. WHAT IS NOT MEASURED is the band between — around 40° of roll,
 * which is the same zone the mid-roll bug lived in. A capture held there gets the
 * uncorrected azimuth, which is the conservative choice: the correction is a device
 * quirk and applying it where it has not been observed would be inventing one.
 */
const val LANDSCAPE_ROLL_DEG = 60f

/**
 * Is this pose on the WRONG BRANCH of the attitude's 180° ambiguity?
 *
 * THE ORIGINAL CODE ALREADY FIXED THIS and I deleted it, calling it an artifact of the
 * Euler path. It was not:
 *
 *     if (abs(roll) > 90) { azimuth += 180 }      // unconditional, above the `// magic`
 *
 * Held in level landscape the device's +Y axis is horizontal, so `r7 ~ 0` and the
 * attitude has a 180° ambiguity that this HAL resolves inconsistently — flipping the
 * azimuth AND the image roll together, several times a second, while the phone is still.
 * Measured: `roll +90.4 / bearing 274.4` alternating with `roll -93.3 / bearing 95.0`
 * within two seconds of each other.
 *
 * `getOrientation` reported those two branches as roll ~ -177 versus ~ +2.7, so
 * `abs(roll) > 90` split them cleanly. This file's `atan2(r6, r7)` reports them as
 * +90 versus -93 — the same ambiguity, now carried in the SIGN, which `abs()` discards.
 * Hence the sign test here, and hence why the original's key cannot simply be copied.
 *
 * [expectedRollSign] comes from the gravity-based orientation class, NOT from the fused
 * attitude — which is the whole point: it held a stable 270 through every flip. Over 729
 * landscape captures, `device_rotation_deg` 270 means a positive image roll (639 against
 * 9) and 90 means negative (79 against 2); those 11 exceptions are the flips themselves.
 *
 * Pass 0 where the class does not say (portrait, flat, unknown) and this declines rather
 * than guessing.
 *
 * SUPERSEDED 2026-10-10 by [onWrongAttitudeBranch] below, which asks GRAVITY instead.
 * Kept because the 729-capture measurement above is real and because the two can be
 * compared on stored frames. What is wrong with it is not the sign table — that scored
 * 6 true positives, 0 false positives and 0 misses against gravity on 100 real captures
 * — but its INPUT:
 *
 *  - `OrientationEventListener` returns ORIENTATION_UNKNOWN when the phone is near
 *    flat, `fromDegrees` maps that to FLAT_UP and `toDegrees` turns FLAT_UP into 0,
 *    which is indistinguishable from PORTRAIT. So pitched steeply down — where the
 *    user reported the roll "completely fucked" — the class flickers between a
 *    landscape bucket and 0, this correction flickers with it, and the reported roll
 *    jumps 180° and back while the phone moves smoothly.
 *  - The class is quantized into 45° buckets, so it cannot say anything during a
 *    rotation, which is where the flicker is most visible.
 *  - `abs(imageRollDeg) > LANDSCAPE_ROLL_DEG` puts a step at exactly 60°. Measured by
 *    the user rotating portrait → landscape below the horizon: the readout ran 0, −10,
 *    … then jumped to +110 and came down to +90 — which is −70+180, −80+180, −90+180.
 */
internal fun CameraPose.onWrongAttitudeBranchByOrientationClass(expectedRollSign: Int): Boolean =
    expectedRollSign != 0 && abs(imageRollDeg) > LANDSCAPE_ROLL_DEG &&
        (if (imageRollDeg > 0f) 1 else -1) != expectedRollSign

/**
 * How much of gravity lies in the screen's plane, 0..1 — the conditioning of
 * [gravityRollDeg], exactly as [CameraPose.horizontalLength] is the conditioning of the
 * bearing. 1 with the phone upright, 0 with it flat, where no in-plane direction exists
 * and the roll it implies is arbitrary.
 */
fun gravityRollConditioning(ax: Float, ay: Float, az: Float): Float {
    val magnitude = sqrt(ax * ax + ay * ay + az * az)
    if (magnitude < 1e-3f) return 0f
    return sqrt(ax * ax + ay * ay) / magnitude
}

/**
 * The image roll GRAVITY implies: `atan2(a_x, a_y)` in the device frame.
 *
 * This is the identity `attitude.roll_deg` is documented to satisfy by construction, and
 * measuring it is what exposed the landscape bug the attitude maths was rewritten for.
 * It comes from the accelerometer, a different stream from the fused rotation vector, so
 * it is INDEPENDENT of the attitude being checked — which is the whole reason it can
 * check it.
 *
 * A raw accelerometer sample is gravity plus linear acceleration and cannot separate
 * them, and this file is careful elsewhere not to pretend otherwise. It is sufficient
 * HERE because the only question asked of it is binary with a 90° margin (see
 * [onWrongAttitudeBranch]): to move this answer, hand movement would have to produce a
 * lateral acceleration comparable to g itself.
 */
fun gravityRollDeg(ax: Float, ay: Float): Float =
    Math.toDegrees(atan2(ax, ay).toDouble()).toFloat()

/**
 * The floor under [gravityRollConditioning] at which the branch test declines.
 *
 * 0.26 is ~15° off flat. Below it gravity has no usable in-plane direction, so the test
 * says nothing rather than guessing — the same discipline as [BEARING_CONDITION_FLOOR],
 * and the opposite of the orientation class's habit of reporting 0 for "I do not know".
 */
const val GRAVITY_ROLL_FLOOR = 0.26f

/**
 * Is this pose on the WRONG 180° attitude branch — judged against gravity?
 *
 * The fault is the HAL's, described in full above: held with the device's +Y axis near
 * horizontal the attitude has a 180° ambiguity, and this one resolves it inconsistently,
 * flipping the azimuth and the image roll together while the phone is still. What is new
 * here is the DETECTOR. Gravity is unambiguous — there is only one down — so the matrix
 * disagreeing with it by about 180° is the fault itself rather than a proxy for it.
 *
 * Measured on 100 consecutive captures: 94 rows agree with gravity to within 15° and 6
 * are 173–175° off. There is nothing in between, so the 90° threshold sits in a 160°-wide
 * empty band and its exact value does not matter.
 *
 * Three properties the orientation-class version could not have, and they are the point:
 * it is continuous (no 45° buckets, so no flicker during a rotation), it needs no step in
 * the roll (no jump at 60°), and it works at EVERY roll and pitch the conditioning allows
 * — including mid-roll around 40°, and including pitched steeply down, where the class
 * reports "unknown" as "portrait".
 *
 * Declines — returns false — when gravity is too flat to say, or when no sample has
 * arrived. Declining means the pose is published as the HAL gave it, which is the honest
 * failure: a 180° correction applied on a guess is worse than an uncorrected reading.
 */
fun CameraPose.onWrongAttitudeBranch(
    gravityRollDeg: Float?,
    gravityConditioning: Float,
): Boolean =
    gravityRollDeg != null && gravityConditioning >= GRAVITY_ROLL_FLOOR &&
        abs(signedDegreeDelta(imageRollDeg, gravityRollDeg)) > 90f

/**
 * This pose with the 180° branch error taken out — of the azimuths AND of the image roll.
 *
 * THE ROLL GOES WITH IT, which the first version of this missed. The flip is reported
 * live in the capture overlay (user, 2026-10-10: "roll flips in overlay"), so it is in
 * the published attitude and not an artifact of the at-exposure lookup. Measured on the
 * two branches of one steady hold: `roll +90.4 / bearing 274.4` against
 * `roll -93.3 / bearing 95.0`, and `-93.3 + 180 = 86.7` lands on the good branch's
 * +90.4 inside hand-held noise. So the flip is `(azimuth += 180, imageRoll += 180)`.
 *
 * PITCH IS NOT TOUCHED, measured: it read ~-10° on both branches. Which is consistent
 * with everything else here — the ambiguity lives in the horizontal frame and in the
 * image's rotation, never in how far the lens is tilted, and that is why pitch has
 * agreed with gravity throughout.
 *
 * [horizontalLength] needs no correction either: the fallback weight uses
 * `|cos(imageRoll)|`, and `cos(r + 180) = -cos(r)` has the same magnitude.
 *
 * Consequence for the archive: landscape captures taken on the wrong branch — about 11
 * of 729 in the prod sample — carry a `roll_deg` that is 180° out as well as a mirrored
 * bearing. Both are recoverable, by the same +180.
 */
fun CameraPose.withBranchCorrected(): CameraPose = copy(
    bearingDeg = (bearingDeg + 180f) % 360f,
    deviceBearingDeg = (deviceBearingDeg + 180f) % 360f,
    pointingBearingDeg = (pointingBearingDeg + 180f) % 360f,
    imageRollDeg = signedDegreeDelta(0f, imageRollDeg + 180f),
)

/**
 * Does this pose fall in the region where a known-affected device mirrors its azimuth?
 *
 * MEASURED, 2026-10-10, on an Armor 22. Held in landscape with the lens ABOVE the
 * horizon, this HAL returns `-a` where it should return `a` — a reflection about the
 * north–south axis. Two independent datasets say so:
 *
 *  - WHILE TURNING: the fused heading's change against the gyroscope's yaw about
 *    gravity, over 9 pairs in that posture, gave a ratio of −1.05 (median). A negated
 *    azimuth gives exactly −1; nothing else does. 29 portrait pairs gave +1.
 *  - WHILE TILTING, with the gyro confirming no yaw at all: crossing the horizon in
 *    landscape jumped the bearing +109.4° and −97.1°, while every pair that stayed on
 *    one side moved ≤13°. On the two crossings where the pitch barely moved, the new
 *    bearing was the NEGATION of the old to within 2° (124.6 → 234.0 against −a =
 *    235.4; 167.8 → 189.9 against 192.2). `180 − a` and `a + 180` both miss by over
 *    100°.
 *
 * THE KEY IS THE PITCH SIGN, and that was tested against the alternative. Correcting on
 * `pitch < 0` makes the tilt sweep continuous — worst step 15.7° against 109.4°
 * uncorrected — while correcting on `|roll| > 90`, which is what the original workaround
 * used, makes it WORSE (113.2°, four large steps). The two coincide at a perfect
 * landscape hold, because a level landscape phone has its +Y axis and its lens both
 * horizontal so `r7` and `r8` cross zero together; across a real sweep they part.
 *
 * NO HYSTERESIS, deliberately. The HAL flips state at the horizon and so does this, so
 * the correction cancels the flip exactly. Smoothing it would desynchronise the two and
 * leave a band where a perfectly good azimuth gets mirrored.
 */
fun CameraPose.inMirroredAzimuthRegion(): Boolean =
    abs(imageRollDeg) > LANDSCAPE_ROLL_DEG && pitchDeg < 0f

/**
 * This pose with every azimuth reflected about north–south — the inverse of what the
 * affected HAL did to it. Pitch and image roll are untouched: the mirror is in the
 * horizontal frame only, which is why they agreed with gravity all along.
 */
fun CameraPose.withMirroredAzimuth(): CameraPose = copy(
    bearingDeg = (360f - bearingDeg) % 360f,
    deviceBearingDeg = (360f - deviceBearingDeg) % 360f,
    pointingBearingDeg = (360f - pointingBearingDeg) % 360f,
)

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
