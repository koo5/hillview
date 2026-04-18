package cz.hillview.plugin

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class HeadingFilterTest {

    private val bearingEpsilon = 0.5 // degrees

    // ~22 m east of (0, 0) at the equator; ~11 m north of (0, 0). Both clear
    // the default 10 m distance gate.
    private val origin = FilterPosition(lat = 0.0, lng = 0.0, speed = 5.0, timestamp = 0L)
    private val east = FilterPosition(lat = 0.0, lng = 0.0002, speed = 5.0, timestamp = 1_000L)
    private val north = FilterPosition(lat = 0.0001, lng = 0.0, speed = 5.0, timestamp = 1_000L)

    @Test
    fun firstValidPositionReturnsNullAndAnchors() {
        val filter = HeadingFilter()
        assertNull(filter.update(origin))
        // Second call from same point won't advance (zero distance), but the
        // anchor was set — a later eastbound sample should return ~90°.
        val heading = filter.update(east)
        assertNotNull(heading)
        assertEquals(90.0, heading!!, bearingEpsilon)
    }

    @Test
    fun lowSpeedRejectedAndDoesNotAnchor() {
        val filter = HeadingFilter()
        val stationary = origin.copy(speed = 0.5)
        assertNull(filter.update(stationary))
        // Anchor wasn't set — next sample is treated as the first valid one.
        assertNull(filter.update(east))
    }

    @Test
    fun nullSpeedRejected() {
        val filter = HeadingFilter()
        val unknown = origin.copy(speed = null)
        assertNull(filter.update(unknown))
    }

    @Test
    fun shortDistanceRejectedButAnchorHeld() {
        val filter = HeadingFilter()
        filter.update(origin) // anchor
        // ~1 m east — well under the 10 m gate.
        val tooClose = FilterPosition(lat = 0.0, lng = 0.00001, speed = 5.0, timestamp = 500L)
        assertNull(filter.update(tooClose))
        // Anchor unchanged: a following eastbound sample still returns ~90° from origin.
        val heading = filter.update(east)
        assertEquals(90.0, heading!!, bearingEpsilon)
    }

    @Test
    fun northBearingIsZero() {
        val filter = HeadingFilter()
        filter.update(origin)
        val heading = filter.update(north)
        assertEquals(0.0, heading!!, bearingEpsilon)
    }

    @Test
    fun referenceAdvancesAfterSuccessfulMeasurement() {
        val filter = HeadingFilter()
        filter.update(origin) // anchor at (0, 0)
        filter.update(east)   // advances anchor to (0, 0.0002)
        // Now go north from the new anchor. Distance is ~11 m, bearing ~0°.
        val next = FilterPosition(lat = 0.0001, lng = 0.0002, speed = 5.0, timestamp = 2_000L)
        val heading = filter.update(next)
        assertEquals(0.0, heading!!, bearingEpsilon)
    }

    @Test
    fun resetClearsAnchor() {
        val filter = HeadingFilter()
        filter.update(origin)
        filter.reset()
        // After reset, next sample is treated as the first valid one.
        assertNull(filter.update(east))
    }

    @Test
    fun normalizeBearingDegreesWrapsCorrectly() {
        assertEquals(0.0, normalizeBearingDegrees(0.0), 1e-9)
        assertEquals(0.0, normalizeBearingDegrees(360.0), 1e-9)
        assertEquals(10.0, normalizeBearingDegrees(370.0), 1e-9)
        assertEquals(350.0, normalizeBearingDegrees(-10.0), 1e-9)
        assertEquals(0.0, normalizeBearingDegrees(-360.0), 1e-9)
        assertEquals(0.0, normalizeBearingDegrees(720.0), 1e-9)
        assertEquals(90.0, normalizeBearingDegrees(450.0), 1e-9)
        assertEquals(270.0, normalizeBearingDegrees(-90.0), 1e-9)
    }

    @Test
    fun customThresholds() {
        val filter = HeadingFilter(minSpeed = 10.0, minDistance = 100.0)
        // speed 5 < minSpeed 10 → rejected
        assertNull(filter.update(origin))
        // Bump speed but keep distance under 100 m → still rejected.
        val fastButClose = origin.copy(speed = 20.0)
        assertNull(filter.update(fastButClose)) // first valid sample anchors
        val nearby = FilterPosition(lat = 0.0, lng = 0.0002, speed = 20.0, timestamp = 1_000L)
        assertNull(filter.update(nearby)) // ~22 m < 100 m
    }
}
