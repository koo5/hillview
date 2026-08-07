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

    // The call site passes `armed || claimed` — an accepted pill claim is a
    // manual position too (phone-in-hand find: the claim left the gate shut).

    @Test
    fun aStaleFixWarnsUnlessAManualPositionStandsIn() {
        val fixAt = 1_000_000L
        // Fresh: no warning.
        assertFalse(staleFixWarning(fixAt, fixAt + FIX_FRESH_MS, manualAvailable = false))
        // Stale and it would stamp the photo: warn.
        assertTrue(staleFixWarning(fixAt, fixAt + FIX_FRESH_MS + 1, manualAvailable = false))
        // A manual position would take over instead: nothing to warn about.
        assertFalse(staleFixWarning(fixAt, fixAt + FIX_FRESH_MS + 1, manualAvailable = true))
        // No fix at all is the gate's business, not the warning's.
        assertFalse(staleFixWarning(null, 5_000_000, manualAvailable = false))
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

/**
 * The shutter's voice. Interval capture runs in a pocket; a slide into a
 * degraded location mode must be audible, not just visible.
 */
class CaptureToneTest {

    @Test
    fun aFreshFixSoundsNormal() {
        assertEquals(CaptureTone.Normal, captureTone("gps", 500))
        assertEquals(CaptureTone.Normal, captureTone("gps", null))
    }

    @Test
    fun aManualPositionSoundsTheWarning() {
        assertEquals(CaptureTone.Degraded, captureTone("manual", null))
    }

    @Test
    fun aStaleFixSoundsTheWarning() {
        assertEquals(CaptureTone.Degraded, captureTone("gps", 16_000))
    }

    @Test
    fun noLocationAtAllSoundsTheWarning() {
        assertEquals(CaptureTone.Degraded, captureTone(null, null))
    }
}

/** The overlay backdrop cycle and number formatting, from the contract. */
class CameraOverlayRulesTest {

    @Test
    fun theOpacityWalkMatchesTheOriginal() {
        // From the default 3: 3 → 5 → 0 → 2 → 4 → 0 → … ({0,2,4} loop).
        assertEquals(5, nextOverlayOpacity(3))
        assertEquals(0, nextOverlayOpacity(5))
        assertEquals(2, nextOverlayOpacity(0))
        assertEquals(4, nextOverlayOpacity(2))
        assertEquals(0, nextOverlayOpacity(4))
        assertEquals(3, nextOverlayOpacity(1))
    }

    @Test
    fun coordinatesFormatLikeToFixed6() {
        assertEquals("50.115044", fmtDecimals(50.1150435, 6))
        assertEquals("14.500000", fmtDecimals(14.5, 6))
        assertEquals("-1.234568", fmtDecimals(-1.2345678, 6))
    }

    @Test
    fun bearingFormatsLikeToFixed1() {
        assertEquals("5.4", fmtDecimals(5.39563, 1))
        assertEquals("0.0", fmtDecimals(0.04, 1))
        assertEquals("359.9", fmtDecimals(359.94, 1))
    }
}

/** Resolution labels: the Tauri tier names, extended to real sensor sizes. */
class ResolutionLabelTest {

    @Test
    fun theTauriTiersKeepTheirNames() {
        assertEquals("4K (3840×2160)", resolutionLabel(CaptureResolution(3840, 2160)))
        assertEquals("1440p (2560×1440)", resolutionLabel(CaptureResolution(2560, 1440)))
        assertEquals("1080p (1920×1080)", resolutionLabel(CaptureResolution(1920, 1080)))
        assertEquals("720p (1280×720)", resolutionLabel(CaptureResolution(1280, 720)))
    }

    @Test
    fun realSensorSizesGetMegapixels() {
        assertEquals("12.0 MP (4000×3000)", resolutionLabel(CaptureResolution(4000, 3000)))
        assertEquals("0.3 MP (640×480)", resolutionLabel(CaptureResolution(640, 480)))
    }
}
