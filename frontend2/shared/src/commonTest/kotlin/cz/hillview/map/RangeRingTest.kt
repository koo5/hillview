package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The one circle's rule (user, 2026-10-10): the circle is the exact range
 * threshold, so nothing drawn may cover the line — and the arrowhead's base
 * "sits flush on the threshold", as in the original. At any screen density.
 */
class RangeRingTest {

    private val densities = listOf(1f, 2f, 2.625f, 3.5f)

    /** The range ring as MapScreen sizes it: 70 dp. */
    private fun threshold(density: Float) = 70f * density

    @Test
    fun theArrowheadRestsOnTheLineFromOutside() {
        for (d in densities) {
            val r = threshold(d)
            val lineOuterEdge = r + RANGE_THRESHOLD_LINE_DP / 2f * d
            assertEquals(lineOuterEdge, arrowHeadBaseRadiusPx(r, d), 1e-3f, "density $d: the base is ON the line")
            assertEquals(
                ARROW_HEAD_DP * d, arrowTipRadiusPx(r, d) - arrowHeadBaseRadiusPx(r, d), 1e-3f,
                "density $d: the tip is one head length out, pointing away from the range",
            )
        }
    }

    @Test
    fun theHoldHugsTheLineFromInside() {
        for (d in densities) {
            val r = threshold(d)
            val lineInnerEdge = r - RANGE_THRESHOLD_LINE_DP / 2f * d
            val outerEdge = bearingHoldRadiusPx(r, d) + BEARING_HOLD_DP / 2f * d
            assertEquals(lineInnerEdge, outerEdge, 1e-3f, "density $d")
        }
    }
}
