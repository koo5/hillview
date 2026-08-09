package cz.hillview.plugin

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The stamp refiner's arithmetic — pure functions, no Room, no clock. The
 * refinement's whole claim is "better than the at-the-time value", and every
 * one of these is a way that claim silently breaks: a circular mean that
 * averages 359° and 1° to 180° would stamp photos backwards.
 */
class StampRefinerMathTest {

    @Test
    fun circularMeanHandlesTheNorthWrap() {
        // The case a naive average gets exactly wrong: (359 + 1) / 2 = 180.
        assertEquals(0.0, circularMeanDeg(listOf(359.0, 1.0)), 0.01)
    }

    @Test
    fun circularMeanOfPlainAnglesIsThePlainMean() {
        assertEquals(15.0, circularMeanDeg(listOf(10.0, 20.0)), 0.01)
        assertEquals(90.0, circularMeanDeg(listOf(90.0)), 0.01)
    }

    @Test
    fun circularLerpTakesTheShortArcAcrossNorth() {
        // 350° -> 10° passes through 0, not through 180.
        assertEquals(0.0, circularLerpDeg(350.0, 10.0, 0.5), 0.01)
        assertEquals(355.0, circularLerpDeg(350.0, 10.0, 0.25), 0.01)
    }

    @Test
    fun circularLerpEndpointsAreExact() {
        assertEquals(350.0, circularLerpDeg(350.0, 10.0, 0.0), 0.01)
        assertEquals(10.0, circularLerpDeg(350.0, 10.0, 1.0), 0.01)
    }

    @Test
    fun angularDiffIsSignedAndSmallest() {
        assertEquals(20.0, angularDiffDeg(350.0, 10.0), 0.01)
        assertEquals(-20.0, angularDiffDeg(10.0, 350.0), 0.01)
        assertEquals(180.0, angularDiffDeg(0.0, 180.0), 0.01)
    }

    @Test
    fun fractionPlacesTheInstantBetweenTheBrackets() {
        assertEquals(0.5, fraction(1000L, 2000L, 1500L), 1e-9)
        assertEquals(0.0, fraction(1000L, 2000L, 1000L), 1e-9)
        // Degenerate bracket must not divide by zero.
        assertEquals(0.0, fraction(1000L, 1000L, 1000L), 1e-9)
    }

    @Test
    fun lerpIsLinear() {
        assertEquals(50.05, lerp(50.0, 50.1, 0.5), 1e-9)
    }

    @Test
    fun distanceIsSaneAtRefinementScales() {
        // ~1.11 m per 1e-5 degrees of latitude.
        val d = distanceMeters(50.0, 14.0, 50.00001, 14.0)
        assertTrue(d in 1.0..1.3, "expected ~1.1 m, got $d")
        // At 50°N a longitude degree is ~cos(50°) of a latitude degree.
        val dLon = distanceMeters(50.0, 14.0, 50.0, 14.00001)
        assertTrue(dLon in 0.6..0.85, "expected ~0.71 m, got $dLon")
    }

    @Test
    fun eligibilityMirrorsTheSourceVocabulary() {
        // The sources the refiner can improve…
        assertTrue(StampRefiner.isEligible("gps", null))
        assertTrue(StampRefiner.isEligible(null, "android-compass-true"))
        assertTrue(StampRefiner.isEligible(null, "gps-kalman"))
        // …and the ones it must never touch: the user placed these.
        assertTrue(!StampRefiner.isEligible("manual", null))
        assertTrue(!StampRefiner.isEligible("manual", "manual"))
        assertTrue(!StampRefiner.isEligible(null, null))
    }
}
