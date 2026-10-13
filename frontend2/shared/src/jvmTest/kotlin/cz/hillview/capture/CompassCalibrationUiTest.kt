package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.v2.runComposeUiTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The calibration sheet, exercised on the desktop like the map controls. */
@OptIn(ExperimentalTestApi::class)
class CompassCalibrationUiTest {

    @Test
    fun theSheetNamesTheAccuracyAndOffersEveryExit() = runComposeUiTest {
        var closed = false
        var switched = false
        setContent {
            CompassCalibrationOverlay(
                accuracyLevel = 1,
                walkingMode = true,
                onSwitchToCarMode = { switched = true },
                onClose = { closed = true },
            )
        }

        onNodeWithTag("compass-calibration-overlay").assertIsDisplayed()
        onNodeWithText("LOW").assertIsDisplayed()
        onNodeWithTag("switch-to-car-mode-btn").performClick()
        assertTrue(switched, "the car-mode escape hatch must call back")
        onNodeWithTag("calibration-close-btn").performClick()
        assertTrue(closed, "the close button must call back")
    }

    @Test
    fun goodAccuracyAnnouncesTheComingDismissal() = runComposeUiTest {
        setContent {
            CompassCalibrationOverlay(
                accuracyLevel = 3,
                walkingMode = true,
                onSwitchToCarMode = {},
                onClose = {},
            )
        }
        onNodeWithText("HIGH").assertIsDisplayed()
        onNodeWithText("Accuracy is good! Closing soon…").assertIsDisplayed()
    }
}

/** The camera overlay's states, desktop-run like the rest of the UI. */
@OptIn(ExperimentalTestApi::class)
class CameraOverlayUiTest {

    /**
     * The two axes beside the bearing, added so an orientation test is readable while
     * shooting it: ↕ is the optical axis's tilt (POSITIVE LOOKING DOWN) and ⟳ the
     * image's rotation about that axis, 0 upright and ±90 in landscape.
     *
     * Note what the 🧭 is NOT: it is the ELECTED bearing — what a capture would stamp,
     * so gps-kalman in car mode — while these two come from the raw attitude. In
     * walking mode all three are the same reading.
     */
    @Test
    fun theOverlayShowsTheOtherTwoAxesBesideTheBearing() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    bearingDeg = 273.1f,
                    pitchDeg = -5.6f,
                    imageRollDeg = 0.8f,
                    fixLatitude = 50.115044,
                    fixLongitude = 14.500907,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithText("↕  -5.6°   ⟳   +0.8°").assertIsDisplayed()
    }

    /**
     * THE SLOTS ARE REAL ON SCREEN, not just in the string.
     *
     * Every readout is padded to a fixed character count, which only buys stable layout
     * if the font is actually monospaced AT THE WEIGHT WE ASK FOR. That is an assumption
     * about the platform's font, not about our code, and if it ever stopped holding —
     * `FontFamily.Monospace` resolving to something proportional, or a bolder face with a
     * different advance — every pad() would silently become decoration and the numbers
     * would go back to shuffling sideways. So: two attitude readouts of the same
     * character length, utterly different digits, must DRAW the same width.
     */
    @Test
    fun equalLengthReadoutsDrawTheSameWidth() = runComposeUiTest {
        fun widthOf(pitch: Float, roll: Float): Float {
            var w = 0f
            setContent {
                CameraOverlayUi(
                    state = CaptureState(
                        ready = false,
                        pitchDeg = pitch,
                        imageRollDeg = roll,
                        fixLatitude = 50.115044,
                        fixLongitude = 14.500907,
                    ),
                    bearingMode = cz.hillview.map.BearingMode.Walking,
                    overridePosition = null,
                    opacityLevel = 3,
                    onCycleOpacity = {},
                )
            }
            val b = onNodeWithTag("attitude-readout").getUnclippedBoundsInRoot()
            w = (b.right - b.left).value
            return w
        }
        // "-4.4" / "-92.4" against "+88.8" / "+111.1": every digit differs, several are
        // the widest and narrowest glyphs in the face, and the padded length is equal.
        val a = widthOf(-4.4f, -92.4f)
        val b = widthOf(88.8f, 111.1f)
        assertEquals(a, b, 0.5f, "attitude readout drew $a then $b — the font is not monospaced")
    }

    /**
     * THE COMPARISON MUST NOT HIDE ITSELF.
     *
     * The matrix's roll appeared only on a disagreement of more than 10°, and the result
     * was "no alternative number ever shows in the overlay" — a comparison invisible
     * during the very event it exists to explain. It is unconditional under the
     * diagnostics switch now, and this pins both halves: present when asked for even
     * when the two AGREE, absent when not asked for even when they disagree wildly.
     */
    @Test
    fun theMatrixRollShowsWheneverDiagnosticsAreOnEvenWhenItAgrees() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    pitchDeg = 0f,
                    imageRollDeg = 45f,
                    // Agreeing to a tenth of a degree — the old rule would have hidden it.
                    matrixRollDeg = 45.1f,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                diagnostics = true,
            )
        }
        onNodeWithTag("attitude-readout").assertTextContains("m  +45.1°", substring = true)
    }

    /**
     * A REVERSAL IS NOT A PREFERENCE. The one report that could not be acted on was a
     * 180° jump watched with diagnostics off and no second number beside it, so a gross
     * disagreement surfaces itself whatever the setting. It cannot fire while the fusion
     * is healthy, which is what keeps it out of ordinary use.
     */
    @Test
    fun aGrossDisagreementShowsItselfWithoutBeingAskedFor() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    pitchDeg = 0f,
                    imageRollDeg = -90f,
                    matrixRollDeg = 90f,          // the branch, 180 away
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                diagnostics = false,
            )
        }
        onNodeWithTag("attitude-readout").assertTextContains("m  +90.0°", substring = true)
    }

    @Test
    fun theMatrixRollStaysOutOfTheWayWhenDiagnosticsAreOff() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    pitchDeg = 0f,
                    imageRollDeg = 45f,
                    // Mildly disagreeing — the overshoot's scale — and not shown:
                    // someone taking photographs has no use for a second roll, and every
                    // frame records the pair anyway. A GROSS disagreement does surface
                    // itself; that is the test above.
                    matrixRollDeg = 55f,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                diagnostics = false,
            )
        }
        onNodeWithTag("attitude-readout").assertTextEquals("↕  +0.0°   ⟳  +45.0°")
    }

    /** Landscape: the roll is what moves, and it reads ±90 rather than a residual. */
    @Test
    fun theRollReadsNinetyInLandscape() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    pitchDeg = -4.4f,
                    imageRollDeg = -92.4f,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithText("↕  -4.4°   ⟳  -92.4°").assertIsDisplayed()
    }

    /**
     * Before the compass has answered there is nothing to show, and a 0.0 would read as
     * "perfectly level" rather than "not known yet".
     */
    @Test
    fun noAttitudeMeansNoAttitudeRow() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    bearingDeg = 5.4f,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithTag("attitude-readout").assertDoesNotExist()
    }

    @Test
    fun aFixShowsBearingAndCoordinates() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false, // no hint window
                    bearingDeg = 5.4f,
                    fixLatitude = 50.115044,
                    fixLongitude = 14.500907,
                    fixAltitude = 320.5,
                    fixAccuracyM = 8f,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        // EVERY NUMBER IN ITS OWN FIXED SLOT, right-aligned — the strings carry the
        // padding deliberately. Monospace plus a worst-case width means no readout moves
        // sideways as a value grows a digit, which is what makes them readable while the
        // phone is being rotated. Asserting the exact text is what keeps it that way.
        onNodeWithText("🧭   5.4°").assertIsDisplayed()
        onNodeWithText("📍  50.115044°,   14.500907°").assertIsDisplayed()
        onNodeWithText("⛰️   320.5m").assertIsDisplayed()
        onNodeWithText("🎯 ±  8m").assertIsDisplayed()
    }

    @Test
    fun anAgingFixRaisesTheStaleWarning() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                    fixAtMs = cz.hillview.core.nowMs() - 60_000,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithTag("stale-fix-warning", useUnmergedTree = true).assertExists()
    }

    @Test
    fun aFreshFixRaisesNoWarningAndNeitherDoesAClaim() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    fixLatitude = 50.1,
                    fixLongitude = 14.5,
                    fixAtMs = cz.hillview.core.nowMs() - 60_000,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                // A claimed position takes over — the stale fix would not
                // stamp anything, so no warning.
                overridePosition = ManualLocation(49.9, 14.1),
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithTag("stale-fix-warning", useUnmergedTree = true).assertDoesNotExist()
    }

    @Test
    fun aClaimedPositionShowsItselfAndClaimsNoMeasurements() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
                    hasFix = true, // …a live fix exists (hasFix is "ever", not "fresh"),
                    fixLatitude = 50.0, // live fix exists…
                    fixLongitude = 14.0,
                    fixAccuracyM = 5f,
                ),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                // …but the claim wins, and the overlay must say so.
                overridePosition = ManualLocation(49.897330, 14.500907),
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithText("📍  49.897330°,   14.500907°").assertIsDisplayed()
        onNodeWithText("(map position)").assertIsDisplayed()
    }

    /**
     * Row 3 of the stamp table (docs/one-state.md): no fix this session, a
     * placed map — the map centre is what a capture records, and the
     * overlay says so instead of refusing. The wording differs from the
     * claimed case above because nothing was overridden.
     */
    @Test
    fun withNoFixTheMapPositionShowsItselfAsTheDefault() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(ready = false, hasFix = false),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = ManualLocation(49.897330, 14.500907, atMs = 1L),
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        onNodeWithText("📍  49.897330°,   14.500907°").assertIsDisplayed()
        onNodeWithText("(map position — no GPS fix)").assertIsDisplayed()
        onNodeWithTag("map-position-note", useUnmergedTree = true).assertExists()
    }

    @Test
    fun noPositionShowsTheSpinnerLine() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(ready = false),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        // No fix this session and no placed map: the one no-position case,
        // and the overlay says what a photo would (not) carry.
        onNodeWithText("Waiting for GPS — photos will carry no position").assertIsDisplayed()
    }

    @Test
    fun theLeftEdgeHandleCyclesTheBackdrop() = runComposeUiTest {
        var cycled = false
        setContent {
            CameraOverlayUi(
                state = CaptureState(ready = false),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = { cycled = true },
            )
        }
        // Only the handle cycles — the rest of the glass is deliberately
        // touch-transparent so taps reach the camera's tap-to-focus.
        onNodeWithTag("overlay-opacity-handle").performClick()
        assertTrue(cycled)
    }

    @Test
    fun theHintOwnsTheFirstFourSeconds() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(ready = true, fixLatitude = 50.0, fixLongitude = 14.0),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
            )
        }
        // Unmerged: the clickable panel merges its children's semantics.
        onNodeWithTag("calibration-hint", useUnmergedTree = true).assertIsDisplayed()
        onNodeWithText("• Calibrate compass.").assertIsDisplayed()
    }

    /**
     * "Calibrate compass" is advice about the wrong problem when no compass
     * is driving the app's bearing — so the bearing-tracking hint outranks
     * it, exactly as the original composes the two
     * (showHint = showCalibrationHint && !$shouldShowBearingTrackingHint).
     */
    @Test
    fun theTrackingHintOutranksTheCalibrationHint() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(ready = true, fixLatitude = 50.0, fixLongitude = 14.0),
                bearingMode = cz.hillview.map.BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                suppressHint = true,
            )
        }
        onNodeWithTag("calibration-hint", useUnmergedTree = true).assertDoesNotExist()
    }
}
