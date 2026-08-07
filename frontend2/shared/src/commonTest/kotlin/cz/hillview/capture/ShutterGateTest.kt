package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The location gate on the shutter. The web app asserts "implies
 * cameraReady && locationData"; the lift exists because the requirement is
 * hand-holding for first-time users, not physics — someone underground can
 * position the map manually and shoot against that.
 */
class ShutterGateTest {

    @Test
    fun noFixMeansNoShutter() {
        assertFalse(shutterEnabled(ready = true, hasFix = false, manualLocationArmed = false))
    }

    @Test
    fun aFixOpensTheGate() {
        assertTrue(shutterEnabled(ready = true, hasFix = true, manualLocationArmed = false))
    }

    @Test
    fun liftingTheGateOpensItWithoutAFix() {
        assertTrue(shutterEnabled(ready = true, hasFix = false, manualLocationArmed = true))
    }

    @Test
    fun nothingOpensAGateOnAnUnreadyCamera() {
        assertFalse(shutterEnabled(ready = false, hasFix = true, manualLocationArmed = true))
    }
}

/**
 * Shutter priority: pinning a time must not change the picture's
 * brightness, so ISO scales to keep the exposure product — until the
 * sensor's gain range runs out, where honesty beats failure.
 */
class ShutterPriorityIsoTest {

    @Test
    fun halvingTheExposureDoublesTheIso() {
        assertEquals(
            400,
            shutterPriorityIso(
                meteredExposureNs = 4_000_000, meteredIso = 200,
                pinnedExposureNs = 2_000_000, minIso = 50, maxIso = 6400,
            ),
        )
    }

    @Test
    fun aPinAtTheMeteredTimeKeepsTheMeteredIso() {
        assertEquals(
            200,
            shutterPriorityIso(
                meteredExposureNs = 4_000_000, meteredIso = 200,
                pinnedExposureNs = 4_000_000, minIso = 50, maxIso = 6400,
            ),
        )
    }

    @Test
    fun aVeryFastPinInDimLightClampsToMaxIsoAndUnderexposes() {
        // 1/30s @ ISO 800 pinned to 1/2000 wants ISO ~53000 — the sensor
        // tops out instead, and the photo comes out dark. That is the
        // truthful outcome of asking for 1/2000 in the dark.
        assertEquals(
            6400,
            shutterPriorityIso(
                meteredExposureNs = 33_000_000, meteredIso = 800,
                pinnedExposureNs = 500_000, minIso = 50, maxIso = 6400,
            ),
        )
    }

    @Test
    fun aSlowPinInBrightLightClampsToMinIso() {
        assertEquals(
            50,
            shutterPriorityIso(
                meteredExposureNs = 1_000_000, meteredIso = 100,
                pinnedExposureNs = 33_000_000, minIso = 50, maxIso = 6400,
            ),
        )
    }
}

class ShutterFormatTest {

    @Test
    fun theLadderReadsAsPhotographersExpect() {
        assertEquals(
            listOf("1/125", "1/250", "1/500", "1/1000", "1/2000"),
            SHUTTER_CHOICES_NS.map { formatShutter(it) },
        )
    }
}
