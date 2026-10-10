package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The one circle's rule (user, 2026-10-10): the circle is the exact range
 * threshold and "the bearing arrow should end right inside it" — so nothing
 * drawn may cross the line, at any screen density.
 */
class RangeRingTest {

    private val densities = listOf(1f, 2f, 2.625f, 3.5f)

    /** The range ring as MapScreen sizes it: 70 dp. */
    private fun threshold(density: Float) = 70f * density

    @Test
    fun theArrowEndsJustInsideTheLine() {
        for (d in densities) {
            val r = threshold(d)
            val lineInnerEdge = r - RANGE_THRESHOLD_LINE_DP / 2f * d
            val tip = arrowTipRadiusPx(r, d)
            assertTrue(tip < lineInnerEdge, "density $d: tip $tip reaches the line at $lineInnerEdge")
            assertTrue(
                lineInnerEdge - tip <= 2f * d,
                "density $d: tip $tip stops ${(lineInnerEdge - tip) / d} dp short — not RIGHT inside",
            )
        }
    }

    @Test
    fun theHoldHugsTheLineFromOutsideAtEveryWidth() {
        for (d in densities) {
            val r = threshold(d)
            val lineOuterEdge = r + RANGE_THRESHOLD_LINE_DP / 2f * d
            for (strokeDp in listOf(3f, BEARING_HOLD_ARMED_DP)) {
                val innerEdge = bearingHoldRadiusPx(r, strokeDp, d) - strokeDp / 2f * d
                assertEquals(lineOuterEdge, innerEdge, 1e-3f, "density $d, stroke $strokeDp dp")
            }
        }
    }
}
