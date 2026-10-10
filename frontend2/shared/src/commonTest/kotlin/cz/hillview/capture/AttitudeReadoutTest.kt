package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
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

    /**
     * THE WIDTH INVARIANT, which is the whole point of the slots: every value a field can
     * hold must render to the SAME number of characters. One sample passing (as the
     * overlay UI test checks) does not establish that — the failure mode is a value
     * elsewhere in the range growing a digit and shoving its neighbours sideways.
     */
    @Test
    fun everyFieldIsTheSameWidthAcrossItsWholeRange() {
        fun widths(values: List<Double>, render: (Double) -> String): Set<Int> =
            values.map { render(it).length }.toSet()

        // The image roll and gravity's copy of it: -180 through +180.
        val rolls = (-180..180).map { it.toDouble() } + listOf(-99.95, -9.99, 0.0, 99.99)
        assertEquals(
            1,
            widths(rolls) { pad(signedOneDp(it), W_ROLL) }.size,
            "roll widths: " + widths(rolls) { pad(signedOneDp(it), W_ROLL) },
        )
        // Pitch: -90 through +90.
        val pitches = (-90..90).map { it.toDouble() }
        assertEquals(1, widths(pitches) { pad(signedOneDp(it), W_PITCH) }.size)
        // The bearing is unsigned, 0 through 360.
        val bearings = (0..360).map { it.toDouble() }
        assertEquals(1, widths(bearings) { pad(fmtDecimals(it, 1), W_BEARING) }.size)
        // Coordinates at their extremes, where the sign and the extra digit both land.
        val lats = listOf(-90.0, -9.123456, 0.0, 50.115044, 89.999999)
        assertEquals(1, widths(lats) { pad(fmtDecimals(it, 6), W_LAT) }.size)
        val lons = listOf(-180.0, -14.5, 0.0, 14.500907, 179.999999)
        assertEquals(1, widths(lons) { pad(fmtDecimals(it, 6), W_LON) }.size)
        // Altitude, from the Dead Sea to above Everest.
        val alts = listOf(-430.5, 0.0, 320.5, 8848.9)
        assertEquals(1, widths(alts) { pad(fmtDecimals(it, 1), W_ALT) }.size)
    }

    /**
     * A value WIDER than its slot must not be truncated — it may only push. Clipping a
     * readout would turn a wrong number into a plausible one, which is the failure this
     * codebase treats as worse than a visible one.
     */
    @Test
    fun anOversizedValueOverflowsRatherThanBeingCut() {
        val huge = pad(fmtDecimals(123456.7, 1), W_ALT)
        assertTrue(huge.contains("123456.7"), huge)
    }

    /** The sign is always present, so "+" marks the direction rather than its absence. */
    @Test
    fun theSignIsAlwaysShownOnTheTwoAxesWhereItIsTheInformation() {
        assertEquals("+12.3", signedOneDp(12.34))
        assertEquals("-12.3", signedOneDp(-12.34))
        assertEquals("+0.0", signedOneDp(0.0))
        // Rounding must not lose the sign of a value that rounds to zero.
        assertEquals("-0.0", signedOneDp(-0.01))
    }
}
