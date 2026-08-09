package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class EcoSliderTest {

    @Test
    fun theAxisEndsMeanWhatThePhoneRoundSpecified() {
        // Extreme left/bottom: refresh only on capture.
        assertEquals(0f, ecoSliderToFps(0f))
        assertEquals(0f, ecoSliderToFps(0.03f))
        // Extreme right/top: the untouched default.
        assertEquals(30f, ecoSliderToFps(1f))
    }

    @Test
    fun theTwoBandsSkipTheDeadZone() {
        // Lower half: the duty band, log 0.1..1.
        val bottom = ecoSliderToFps(0.051f)
        assertTrue(bottom in 0.09f..0.15f, "duty band starts ≈ 0.1, got $bottom")
        val dutyTop = ecoSliderToFps(0.499f)
        assertTrue(dutyTop in 0.9f..1.01f, "duty band tops at 1, got $dutyTop")
        // Upper half: the AE band, log 7..30 — 1..7 is unimplementable
        // (AE floors, session-reconfig cost) and never labelled.
        val aeBottom = ecoSliderToFps(0.5f)
        assertTrue(aeBottom in 6.9f..7.5f, "AE band starts at 7, got $aeBottom")
        // Monotonic overall.
        var last = 0f
        for (i in 0..20) {
            val v = ecoSliderToFps(i / 20f)
            assertTrue(v >= last, "monotonic at t=${i / 20f}: $v >= $last")
            last = v
        }
    }

    @Test
    fun theInverseRoundTripsWithinItsBands() {
        for (fps in listOf(0f, 0.1f, 0.5f, 1f, 7f, 15f, 29f, 30f)) {
            val roundTripped = ecoSliderToFps(ecoFpsToSlider(fps))
            assertTrue(
                kotlin.math.abs(roundTripped - fps) < fps * 0.05f + 0.02f,
                "round trip $fps -> $roundTripped",
            )
        }
        // Dead-zone prefs land on the band boundary (the AE floor), not
        // nonsense.
        val deadZone = ecoSliderToFps(ecoFpsToSlider(3f))
        assertTrue(deadZone in 6.9f..7.5f, "dead zone lands at the AE floor, got $deadZone")
    }

    @Test
    fun labelsSpeakTheThreeBands() {
        assertEquals("on 📸 only", ecoFpsLabel(0f))
        assertEquals("default", ecoFpsLabel(30f))
        assertEquals("0.3 fps", ecoFpsLabel(0.31f))
        assertEquals("15 fps", ecoFpsLabel(15.2f))
    }
}
