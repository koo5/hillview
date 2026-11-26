package cz.hillview.capture

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.roundToInt

/**
 * Will this shot pass the Panoramax level gates, and if not, why.
 *
 * The third port of one piece of arithmetic: `common/capture_pose.py` derives
 * `photos.pitch`/`photos.roll` from the stamp, `frontend/src/lib/capturePoseMath.ts`
 * says the same thing in the web capture UI, and this says it here. The three agree
 * case by case against `backend/common/capture_pose_cases.json`, which
 * `CaptureLevelFixtureTest` reads rather than copies.
 *
 * It takes ANGLES, not a gravity vector, because that is what the one state carries:
 * `PhotoCaptureState.pitchDeg` (positive up, since 2026-11-17) and `imageRollDeg`
 * (`atan2(g_x, g_y)`, the same quantity as the stamp's `roll_deg`). Nothing here
 * subscribes to a sensor — see docs/one-state.md.
 */

/**
 * The gates, from `MAX_PITCH_DEG` and `MAX_ROLL_DEG` in
 * `backend/panoramax/app/eligibility.py`. `CaptureLevelFixtureTest` pins them to the
 * shared fixture, so the three ports cannot drift apart silently.
 */
const val LEVEL_MAX_PITCH_DEG = 20.0
const val LEVEL_MAX_ROLL_DEG = 10.0

/**
 * Below this share of gravity in the screen's plane, roll means nothing: the phone is
 * pointing at the ground or the sky and the horizon is not in the frame to be level
 * with. Mirrors `GRAVITY_ROLL_FLOOR` in shared-kt's `CameraPose.kt` and `ROLL_FLOOR`
 * in the other two ports.
 *
 * It is written out rather than imported because `CameraPose.kt` is shared-kt, which
 * only androidMain compiles, and this has to live where the overlay does.
 * `CaptureLevelFixtureTest` asserts the two are equal, so the duplication is checked
 * rather than trusted.
 *
 * A Double, where the sensor stack's is a Float: this one is compared against a
 * Double conditioning, and 0.26f widened is 0.2599999904, which is equal to neither
 * the fixture's 0.26 nor itself written out. The test crosses the two in FLOAT space,
 * where they are exactly equal, rather than pretending a tolerance is agreement.
 */
const val LEVEL_ROLL_FLOOR = 0.26

/** What the indicator says. `Unmeasured` is "no attitude at all", not "flat". */
enum class CaptureLevel { Level, Tilted, Flat, Unmeasured }

/**
 * GPano roll from a stamp-style roll: its residual from the nearest quarter turn,
 * negated, in (−45, 45]. A level landscape shot reads 0, not 90.
 *
 * `floor(r / 90 + 0.5)`, not `round`: Kotlin's `round` goes half away from zero and
 * the other two ports go half up, which disagree at every negative half.
 */
fun levelRollDeg(imageRollDeg: Double): Double {
    val residual = imageRollDeg - 90.0 * floor(imageRollDeg / 90.0 + 0.5)
    // + 0.0 turns -0.0 into 0.0, as capture_pose.py and capturePoseMath.ts both do.
    return -residual + 0.0
}

/**
 * How much of gravity lies in the screen's plane, from the pitch alone.
 *
 * `hypot(g_x, g_y) / |g|` is `|cos(pitch)|` by construction, which is what
 * `_from_attitude` uses when a stamp carries angles and no vector.
 */
fun rollConditioning(pitchDeg: Double): Double = abs(cos(pitchDeg * PI / 180.0))

/** The verdict. Null pitch is [CaptureLevel.Unmeasured] — nothing measured the pose. */
fun captureLevel(pitchDeg: Double?, imageRollDeg: Double?): CaptureLevel {
    if (pitchDeg == null) return CaptureLevel.Unmeasured
    // Flat BEFORE the pitch gate: such a shot fails the gate anyway, and "pointing at
    // the sky" tells the user what to do about it where "tilted up 76°" does not.
    if (rollConditioning(pitchDeg) < LEVEL_ROLL_FLOOR) return CaptureLevel.Flat
    if (imageRollDeg == null) return CaptureLevel.Unmeasured
    if (abs(pitchDeg) > LEVEL_MAX_PITCH_DEG) return CaptureLevel.Tilted
    if (abs(levelRollDeg(imageRollDeg)) > LEVEL_MAX_ROLL_DEG) return CaptureLevel.Tilted
    return CaptureLevel.Level
}

/**
 * The state in words, so the indicator is never colour alone. Null when unmeasured.
 *
 * Deliberately the same sentences as the web app's `levelWords`: a person who has used
 * one app should not have to learn a second vocabulary for the same measurement.
 */
fun captureLevelWords(pitchDeg: Double?, imageRollDeg: Double?): String? {
    val state = captureLevel(pitchDeg, imageRollDeg)
    if (state == CaptureLevel.Unmeasured || pitchDeg == null) return null
    if (state == CaptureLevel.Flat) {
        return if (pitchDeg < 0) "Pointing at the ground" else "Pointing at the sky"
    }
    if (state == CaptureLevel.Level) return "Level"
    val parts = buildList {
        if (abs(pitchDeg) > LEVEL_MAX_PITCH_DEG) {
            add("Tilted ${if (pitchDeg < 0) "down" else "up"} ${abs(pitchDeg).roundToInt()}°")
        }
        val roll = imageRollDeg?.let(::levelRollDeg)
        if (roll != null && abs(roll) > LEVEL_MAX_ROLL_DEG) {
            add("Horizon tilted ${abs(roll).roundToInt()}°")
        }
    }
    return parts.joinToString(" · ")
}
