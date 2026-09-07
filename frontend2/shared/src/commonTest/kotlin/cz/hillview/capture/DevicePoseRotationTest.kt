package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The camera icon's rotation, checked against the ORIGINAL's table.
 *
 * frontend/src/lib/deviceOrientationExif.ts answers this with a 16-row switch
 * (`calculateWebviewRelativeOrientation`) feeding a 4-row one
 * (`getCssRotationFromOrientation`). [devicePoseUiRotation] answers it with
 * arithmetic, so the arithmetic has to reproduce all sixteen rows — that is
 * what this asserts, row by row, in the original's own terms.
 */
class DevicePoseRotationTest {

    /** The original's EXIF orientation codes, as device rotations. */
    private val poseOfExif = mapOf(1 to 0, 6 to 90, 3 to 180, 8 to 270)

    /** getCssRotationFromOrientation, verbatim. */
    private fun cssOfExif(code: Int): Float = when (code) {
        1 -> 0f
        3 -> 180f
        6 -> -90f
        8 -> 90f
        else -> error("not an orientation this app produces: $code")
    }

    /**
     * calculateWebviewRelativeOrientation, verbatim — device EXIF code and
     * screen angle to the relative EXIF code.
     */
    private val relative: Map<Pair<Int, Int>, Int> = mapOf(
        (1 to 0) to 1, (1 to 90) to 6, (1 to 180) to 3, (1 to 270) to 8,
        (3 to 0) to 3, (3 to 90) to 8, (3 to 180) to 1, (3 to 270) to 6,
        (6 to 0) to 6, (6 to 90) to 3, (6 to 180) to 8, (6 to 270) to 1,
        (8 to 0) to 8, (8 to 90) to 1, (8 to 180) to 6, (8 to 270) to 3,
    )

    @Test
    fun everyRowOfTheOriginalsTableAgrees() {
        for ((key, relativeExif) in relative) {
            val (deviceExif, screenAngle) = key
            assertEquals(
                cssOfExif(relativeExif),
                devicePoseUiRotation(poseOfExif.getValue(deviceExif), screenAngle),
                "exif $deviceExif at screen angle $screenAngle",
            )
        }
    }

    /**
     * Auto-rotate on: the display follows the device, so nothing turns. Note
     * the inversion — a device at 90° puts the display at 270°.
     */
    @Test
    fun aFollowingDisplayCancelsThePose() {
        assertEquals(0f, devicePoseUiRotation(0, 0))
        assertEquals(0f, devicePoseUiRotation(90, 270))
        assertEquals(0f, devicePoseUiRotation(180, 180))
        assertEquals(0f, devicePoseUiRotation(270, 90))
    }

    /** Nothing sensing the pose reads as unrotated, like the original's reset. */
    @Test
    fun anUnsensedPoseIsUpright() {
        assertEquals(0f, devicePoseUiRotation(null, 0))
        assertEquals(-90f, devicePoseUiRotation(null, 90))
    }

    @Test
    fun theAnimationTakesTheShortWayRound() {
        // 180 → -90 is a quarter turn clockwise, not three quarters back.
        assertEquals(270f, nextRotationTarget(180f, -90f))
        // -90 → 90 is a half turn; either way is equal, and it stays put.
        assertEquals(-270f, nextRotationTarget(-90f, 90f))
        // Continuing round rather than unwinding: 90 → -90 → ...
        assertEquals(0f, nextRotationTarget(-90f, 0f))
    }

    @Test
    fun anUnchangedTargetDoesNotMove() {
        assertEquals(-90f, nextRotationTarget(-90f, -90f))
        assertEquals(630f, nextRotationTarget(630f, -90f))
    }
}
