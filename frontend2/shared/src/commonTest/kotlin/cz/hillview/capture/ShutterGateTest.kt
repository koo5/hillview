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
        assertFalse(shutterEnabled(ready = true, hasFix = false, mapPositionElected = false))
    }

    @Test
    fun aFixOpensTheGate() {
        assertTrue(shutterEnabled(ready = true, hasFix = true, mapPositionElected = false))
    }

    @Test
    fun liftingTheGateOpensItWithoutAFix() {
        assertTrue(shutterEnabled(ready = true, hasFix = false, mapPositionElected = true))
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
        assertFalse(shutterEnabled(ready = false, hasFix = true, mapPositionElected = true))
    }
}

/**
 * Shutter priority: choosing a time must not change the picture's
 * brightness, so ISO scales to keep the exposure product — until a wall is
 * reached, and then it matters a great deal WHICH wall the rule is willing
 * to give at.
 */
class PlanExposureTest {

    // A plausible phone: 1/20000 .. 1s, ISO 50..6400, fixed aperture.
    private val caps = SensorExposureCaps(
        minExposureNs = 50_000,
        maxExposureNs = 1_000_000_000,
        minIso = 50,
        maxIso = 6400,
    )

    private fun plan(
        mode: ExposureMode,
        targetNs: Long,
        meteredExposureNs: Long,
        meteredIso: Int,
        evBias: Double = 0.0,
    ) = planExposure(
        ExposureRule(mode, targetNs, evBias),
        meteredExposureNs, meteredIso, caps,
    )

    // --- the cases the old shutterPriorityIso carried, now as Pin ---

    @Test
    fun halvingTheExposureDoublesTheIso() {
        val p = plan(ExposureMode.Pin, 2_000_000, meteredExposureNs = 4_000_000, meteredIso = 200)
        assertEquals(400, p.iso)
        assertEquals(2_000_000, p.exposureNs)
        assertEquals(ExposureOutcome.OnTarget, p.outcome)
    }

    @Test
    fun aPinAtTheMeteredTimeKeepsTheMeteredIso() {
        val p = plan(ExposureMode.Pin, 4_000_000, meteredExposureNs = 4_000_000, meteredIso = 200)
        assertEquals(200, p.iso)
        assertEquals(4_000_000, p.exposureNs)
    }

    @Test
    fun aVeryFastPinInDimLightClampsToMaxIsoAndUnderexposes() {
        // 1/30s @ ISO 800 pinned to 1/2000 wants ISO ~53000 — the sensor
        // tops out instead, and the photo comes out dark. That is the
        // truthful outcome of asking for 1/2000 in the dark.
        val p = plan(ExposureMode.Pin, 500_000, meteredExposureNs = 33_000_000, meteredIso = 800)
        assertEquals(6400, p.iso)
        assertEquals(500_000, p.exposureNs)
        assertEquals(ExposureOutcome.Underexposed, p.outcome)
    }

    @Test
    fun aSlowPinInBrightLightClampsToMinIso() {
        val p = plan(ExposureMode.Pin, 33_000_000, meteredExposureNs = 1_000_000, meteredIso = 100)
        assertEquals(50, p.iso)
    }

    // --- the wall Pin cannot climb, and the reason Floor exists ---

    @Test
    fun pinInOpenSunBlowsOutAndSaysSo() {
        // AE settles around 1/10000 @ ISO 50 in open sun; pinned to 1/2000
        // the product wants ISO 10, the sensor floor is 50, and the frame
        // comes out ~2.3 stops over with nothing left to give.
        val p = plan(ExposureMode.Pin, 500_000, meteredExposureNs = 100_000, meteredIso = 50)
        assertEquals(50, p.iso)
        assertEquals(500_000, p.exposureNs)
        assertEquals(ExposureOutcome.Overexposed, p.outcome)
    }

    @Test
    fun floorInOpenSunGoesFasterInsteadOfBlowingOut() {
        val p = plan(ExposureMode.Floor, 500_000, meteredExposureNs = 100_000, meteredIso = 50)
        assertEquals(50, p.iso)
        assertEquals(100_000, p.exposureNs) // the metered time itself: 1/10000
        assertEquals(ExposureOutcome.Faster, p.outcome)
    }

    @Test
    fun floorNeverGoesSLOWERThanItsTarget() {
        // Dusk: 1/30 @ ISO 800. The whole point of a floor is that it
        // refuses to hand the shutter back — it underexposes instead.
        val p = plan(ExposureMode.Floor, 1_000_000, meteredExposureNs = 33_000_000, meteredIso = 800)
        assertEquals(1_000_000, p.exposureNs)
        assertEquals(6400, p.iso)
        assertEquals(ExposureOutcome.Underexposed, p.outcome)
    }

    @Test
    fun evenAFloorRunsOutWhenTheSensorItselfDoes() {
        // Unbiased, a floor can always reach AE's own choice — the sensor
        // demonstrably can do it, AE just did. Only asking for LESS light
        // than the hardware's fastest frame can run it out of road.
        val p = plan(
            ExposureMode.Floor, 500_000,
            meteredExposureNs = 50_000, meteredIso = 50, evBias = -2.0,
        )
        assertEquals(caps.minExposureNs, p.exposureNs)
        assertEquals(ExposureOutcome.Overexposed, p.outcome)
    }

    // --- Sports: a floor that gives the shutter back before the gain ---

    @Test
    fun sportsHoldsItsTargetWhileTheGainStaysUnderTheKnee() {
        // Overcast: 1/500 @ ISO 400 → 1/1000 wants ISO 800, under the knee.
        val p = plan(ExposureMode.Sports, 1_000_000, meteredExposureNs = 2_000_000, meteredIso = 400)
        assertEquals(1_000_000, p.exposureNs)
        assertEquals(800, p.iso)
        assertEquals(ExposureOutcome.OnTarget, p.outcome)
    }

    @Test
    fun sportsSlowsDownRatherThanPassTheKnee() {
        // Indoors: 1/125 @ ISO 800 → 1/1000 would want ISO 6400. Sports
        // gives the shutter back until the gain sits on the knee instead.
        val p = plan(ExposureMode.Sports, 1_000_000, meteredExposureNs = 8_000_000, meteredIso = 800)
        assertEquals(SPORTS_ISO_KNEE, p.iso)
        assertEquals(4_000_000, p.exposureNs) // 1/250 — the knee's price
        assertEquals(ExposureOutcome.Slower, p.outcome)
    }

    @Test
    fun sportsStopsSlowingAtItsFloorAndUnderexposesFromThere() {
        // Night: 1/4 @ ISO 3200. Handing back to 1/125 is as far as it
        // goes; past that a moving car smears and the shot is worthless.
        val p = plan(ExposureMode.Sports, 1_000_000, meteredExposureNs = 250_000_000, meteredIso = 3200)
        assertEquals(SPORTS_SLOWEST_NS, p.exposureNs)
        assertEquals(6400, p.iso)
        assertEquals(ExposureOutcome.Underexposed, p.outcome)
    }

    @Test
    fun sportsInSunBehavesLikeAFloor() {
        val p = plan(ExposureMode.Sports, 500_000, meteredExposureNs = 100_000, meteredIso = 50)
        assertEquals(100_000, p.exposureNs)
        assertEquals(ExposureOutcome.Faster, p.outcome)
    }

    // --- the bias, which is the only answer to a sun in frame ---

    @Test
    fun aStopOfNegativeBiasHalvesTheGain() {
        val straight = plan(ExposureMode.Floor, 2_000_000, 4_000_000, 200)
        val darker = plan(ExposureMode.Floor, 2_000_000, 4_000_000, 200, evBias = -1.0)
        assertEquals(400, straight.iso)
        assertEquals(200, darker.iso)
        assertEquals(2_000_000, darker.exposureNs)
    }

    @Test
    fun negativeBiasBuysBackTheShutterOnceTheGainIsOnTheFloor() {
        // With gain already on the floor the bias has nowhere to go but
        // the shutter — which is exactly what shooting into the sun needs.
        val straight = plan(ExposureMode.Floor, 500_000, 100_000, 50)
        val darker = plan(ExposureMode.Floor, 500_000, 100_000, 50, evBias = -1.0)
        assertEquals(50, darker.iso)
        assertEquals(straight.exposureNs / 2, darker.exposureNs)
    }

    @Test
    fun aPinIgnoresTheLadderWhenTheSensorCannotHoldIt() {
        // Targets outside the sensor's range clamp to it rather than being
        // handed to Camera2 as an impossible request.
        val p = plan(ExposureMode.Pin, 10_000, 100_000, 100)
        assertEquals(caps.minExposureNs, p.exposureNs)
    }
}

/** The ⚡ button has to say which of the three rules is in force. */
class ExposureProvenanceJsonTest {

    @Test
    fun theFullStampSerializesEveryField() {
        // One serialization, two riders: the EXIF UserComment and the
        // photos-table column the upload metadata is built from. The exact
        // string is the contract — the worker parses it as JSON and the
        // synthesized UserComment must match what the writer would produce.
        val json = exposureProvenanceJson(
            ExposureStamp(
                rule = ExposureRule(ExposureMode.Floor, 2_000_000L, -1.0),
                plan = ExposurePlan(1_958_333L, 50, ExposureOutcome.Faster),
                meteredExposureNs = 10_000_000L,
                meteredIso = 100,
            ),
        )
        kotlin.test.assertEquals(
            "{\"mode\":\"floor\",\"target_ns\":2000000,\"ev_bias\":-1.0," +
                "\"applied_ns\":1958333,\"iso\":50,\"outcome\":\"faster\"," +
                "\"metered_ns\":10000000,\"metered_iso\":100}",
            json,
        )
    }

    @Test
    fun aStampWithoutMeteringOmitsTheMeteredKeys() {
        val json = exposureProvenanceJson(
            ExposureStamp(
                rule = ExposureRule(ExposureMode.Pin, 500_000L),
                plan = ExposurePlan(500_000L, 218, ExposureOutcome.OnTarget),
            ),
        )
        kotlin.test.assertTrue("metered" !in json, json)
        kotlin.test.assertTrue("\"mode\":\"pin\"" in json, json)
        kotlin.test.assertTrue("\"outcome\":\"ontarget\"" in json, json)
    }
}

class ExposureLabelTest {

    @Test
    fun eachModeReadsDifferently() {
        assertEquals("Auto", exposureLabel(null))
        assertEquals("=1/500", exposureLabel(ExposureRule(ExposureMode.Pin, 2_000_000)))
        assertEquals("≥1/500", exposureLabel(ExposureRule(ExposureMode.Floor, 2_000_000)))
        assertEquals("🏃1/500", exposureLabel(ExposureRule(ExposureMode.Sports, 2_000_000)))
    }

    @Test
    fun theBiasShowsOnlyWhenItIsDoingSomething() {
        assertEquals("≥1/500 -1EV", exposureLabel(ExposureRule(ExposureMode.Floor, 2_000_000, -1.0)))
        assertEquals("≥1/500 -½EV", exposureLabel(ExposureRule(ExposureMode.Floor, 2_000_000, -0.5)))
        assertEquals("≥1/500", exposureLabel(ExposureRule(ExposureMode.Floor, 2_000_000, 0.0)))
    }

    @Test
    fun theBiasLadderReadsAsPhotographersExpect() {
        assertEquals(
            listOf("-2", "-1", "-½", "0", "+½", "+1"),
            EV_BIAS_CHOICES.map { formatEvBias(it) },
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
    fun everyRowUsesTheSameScale() {
        // The list must be comparable DOWN THE COLUMN (user-raised). It used
        // to name video tiers where a height happened to match one — "4K",
        // "1080p" — and fall back to megapixels otherwise, so a real
        // sensor's menu mixed two unrelated scales.
        assertEquals("8.3 MP · 16:9 (3840×2160)", resolutionLabel(CaptureResolution(3840, 2160)))
        assertEquals("3.7 MP · 16:9 (2560×1440)", resolutionLabel(CaptureResolution(2560, 1440)))
        assertEquals("2.1 MP · 16:9 (1920×1080)", resolutionLabel(CaptureResolution(1920, 1080)))
        assertEquals("12.0 MP · 4:3 (4000×3000)", resolutionLabel(CaptureResolution(4000, 3000)))
        assertEquals("0.3 MP · 4:3 (640×480)", resolutionLabel(CaptureResolution(640, 480)))
    }

    @Test
    fun theRatioIsWhatSaysAChoiceCropsTheSensor() {
        // 16:9 on a 4:3 sensor is a NARROWER picture, not merely a smaller
        // one — the megapixel count alone hides that.
        assertEquals("4:3", aspectRatioLabel(CaptureResolution(4032, 3024)))
        assertEquals("16:9", aspectRatioLabel(CaptureResolution(1920, 1080)))
        assertEquals("11:9", aspectRatioLabel(CaptureResolution(176, 144)))
    }

    @Test
    fun anOddSizeSaysNothingRatherThanSomethingUseless() {
        // A ratio that reduces to big terms is noise; the dimensions are
        // right there in the label anyway.
        assertEquals(null, aspectRatioLabel(CaptureResolution(4001, 3000)))
        assertEquals("4001×3000", resolutionLabel(CaptureResolution(4001, 3000)).substringAfter("("). substringBefore(")"))
        assertEquals(null, aspectRatioLabel(CaptureResolution(0, 0)))
    }
}

/**
 * Which exposure a metering frame is credited to. The precedence IS the
 * behaviour: the harvest is frozen while a rule holds the sensor, so
 * crediting it first anchors the meter to dead light — the 2026-08-21
 * "interval Sports stuck in high exposure" report. SceneMeterLoopTest
 * (androidHostTest) plays that run out end to end.
 */
class MeterCreditedExposureTest {

    private val plan = ExposurePlan(2_000_000L, 200, ExposureOutcome.OnTarget)

    @Test
    fun aRuleInForceCreditsFramesToItsOwnPlan() {
        assertEquals(2_000_000L to 200, meterCreditedExposure(plan, 33_000_000L, 800))
    }

    @Test
    fun underAutoExposureTheHarvestIsTheCredit() {
        assertEquals(33_000_000L to 800, meterCreditedExposure(null, 33_000_000L, 800))
    }

    @Test
    fun halfAHarvestCreditsNothing() {
        // Pairing a time from one source with a gain from another would be
        // a product that never exposed anything; better no evidence at all.
        assertEquals(null, meterCreditedExposure(null, 33_000_000L, null))
        assertEquals(null, meterCreditedExposure(null, null, 800))
    }
}
