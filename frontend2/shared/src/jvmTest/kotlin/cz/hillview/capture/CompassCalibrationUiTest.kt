package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.v2.runComposeUiTest
import kotlin.test.Test
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
        onNodeWithText("🧭 5.4°").assertIsDisplayed()
        onNodeWithText("📍 50.115044°, 14.500907°").assertIsDisplayed()
        onNodeWithText("⛰️ 320.5m").assertIsDisplayed()
        onNodeWithText("🎯 ±8m").assertIsDisplayed()
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
        onNodeWithText("📍 49.897330°, 14.500907°").assertIsDisplayed()
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
        onNodeWithText("📍 49.897330°, 14.500907°").assertIsDisplayed()
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
