package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The gate in front of manual bearing. Every case here is a way the old
 * one-touch grab could change where the app believed you were facing
 * without you meaning it.
 */
class ArrowArmingTest {

    private fun arming() = ArrowArming(holdMs = 400L)

    @Test
    fun aTouchAloneChangesNothing() {
        val a = arming()
        a.press(1_000L)
        assertTrue(a.pressing)
        assertFalse(a.armed, "contact must not be control")
        assertFalse(a.advance(1_399L))
        assertFalse(a.armed)
    }

    @Test
    fun theHoldEarnsItExactlyOnce() {
        val a = arming()
        a.press(1_000L)
        assertTrue(a.advance(1_400L), "the arming call must announce itself")
        assertTrue(a.armed)
        assertFalse(a.advance(1_500L), "and must not announce itself again")
        assertTrue(a.armed)
    }

    /**
     * The accident this exists for: a finger crossing the arrow on its way
     * somewhere else. It must not arm at the end of that travel just because
     * enough time passed.
     */
    @Test
    fun aFingerThatSlidesAcrossNeverArms() {
        val a = arming()
        a.press(1_000L)
        a.moved(distancePx = 40f, slopPx = 20f)
        assertFalse(a.advance(2_000L))
        assertFalse(a.armed)
        assertEquals(0f, a.progress(2_000L), "an abandoned attempt shows no charge")
    }

    /**
     * "Charging nothing yet" and "given up on" both read as zero progress,
     * and mean opposite things — a caller that tells them apart by the
     * number cancels a press it should be waiting on.
     */
    @Test
    fun aFreshPressIsNotAnAbandonedOne() {
        val a = arming()
        a.press(1_000L)
        assertEquals(0f, a.progress(1_000L))
        assertFalse(a.abandoned, "a press that has only just landed is still live")
        a.moved(distancePx = 40f, slopPx = 20f)
        assertTrue(a.abandoned)
        assertEquals(0f, a.progress(1_000L))
        a.release()
        assertFalse(a.abandoned, "with no finger down there is nothing to abandon")
    }

    @Test
    fun aSteadyFingerIsAllowedItsWobble() {
        val a = arming()
        a.press(1_000L)
        a.moved(distancePx = 5f, slopPx = 20f)
        a.moved(distancePx = 19f, slopPx = 20f)
        assertTrue(a.advance(1_400L))
    }

    @Test
    fun movementAfterArmingIsTheWholePoint() {
        val a = arming()
        a.press(1_000L)
        a.advance(1_400L)
        a.moved(distancePx = 500f, slopPx = 20f)
        assertTrue(a.armed, "a drag must not disarm the drag")
    }

    @Test
    fun theChargeFillsOverTheHold() {
        val a = arming()
        a.press(1_000L)
        assertEquals(0f, a.progress(1_000L))
        assertEquals(0.5f, a.progress(1_200L))
        assertEquals(1f, a.progress(1_400L))
        assertEquals(1f, a.progress(9_000L), "and does not overflow")
    }

    @Test
    fun nothingIsChargingBeforeATouch() {
        val a = arming()
        assertEquals(0f, a.progress(5_000L))
        assertFalse(a.pressing)
        assertFalse(a.advance(5_000L))
    }

    /** Letting go leaves no mode behind — that is the point of arming per drag. */
    @Test
    fun releasingEndsManualBearing() {
        val a = arming()
        a.press(1_000L)
        a.advance(1_400L)
        assertTrue(a.armed)
        a.release()
        assertFalse(a.armed)
        assertFalse(a.pressing)
        assertEquals(0f, a.progress(2_000L))
    }

    @Test
    fun aFreshPressStartsFromNothing() {
        val a = arming()
        a.press(1_000L)
        a.moved(distancePx = 99f, slopPx = 20f)
        a.release()
        a.press(5_000L)
        assertEquals(0.25f, a.progress(5_100L), "the abandoned attempt must not carry over")
        assertTrue(a.advance(5_400L))
    }
}

/**
 * The grab zone. The one property that matters is that there is no aiming
 * to do: every angle at the ring's radius is a handle.
 */
class BearingRingGrabTest {

    private val tip = 240f
    private val grab = 90f

    private fun at(angleDeg: Double, radius: Float): Boolean {
        val rad = angleDeg * kotlin.math.PI / 180.0
        return bearingRingGrabbed(
            (kotlin.math.sin(rad) * radius).toFloat(),
            (-kotlin.math.cos(rad) * radius).toFloat(),
            tip,
            grab,
        )
    }

    @Test
    fun everyAngleOnTheRingIsAHandle() {
        for (angle in 0 until 360 step 3) {
            assertTrue(at(angle.toDouble(), tip), "the ring must grab at $angle°")
        }
    }

    @Test
    fun theBandReachesBothWaysFromTheRing() {
        assertTrue(at(0.0, tip - grab))
        assertTrue(at(0.0, tip + grab))
        assertFalse(at(0.0, tip - grab - 1f))
        assertFalse(at(0.0, tip + grab + 1f))
    }

    /** The middle of the map stays the map: panning and marker taps live there. */
    @Test
    fun theDiscInsideIsNotAHandle() {
        assertFalse(at(0.0, 0f))
        assertFalse(at(137.0, tip / 4f))
    }

    @Test
    fun anUnlaidOutArrowGrabsNothing() {
        assertFalse(bearingRingGrabbed(0f, 0f, tipRadiusPx = 0f, grabPx = 90f))
    }
}
