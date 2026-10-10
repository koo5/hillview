package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The readout's job while an orientation fault is being hunted: show the fused roll,
 * mark it when our own correction is firing, and show GRAVITY's answer whenever the two
 * disagree — because that disagreement is the diagnosis and it cannot be read off a
 * captured frame (a capture happens once the phone is already still).
 */
class AttitudeReadoutTest {

    @Test
    fun theComparisonIsWraparoundSafe() {
        // The case the naive subtraction gets wrong: either side of due-zero.
        assertTrue(degreesWithin(179f, -179f, 10f))
        assertTrue(degreesWithin(-5f, 5f, 10f))
        assertFalse(degreesWithin(90f, -90f, 10f))
        // And the 180° branch disagreement, which must never read as agreement.
        assertFalse(degreesWithin(-93f, 87f, 10f))
        assertTrue(degreesWithin(-93f, -93f, 10f))
    }
}
