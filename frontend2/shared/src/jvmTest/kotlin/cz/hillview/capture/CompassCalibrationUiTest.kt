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
    fun aClaimedPositionShowsItselfAndClaimsNoMeasurements() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = CaptureState(
                    ready = false,
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
        onNodeWithText("Getting location...").assertIsDisplayed()
    }

    @Test
    fun tapCyclesTheBackdrop() = runComposeUiTest {
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
        onNodeWithTag("location-overlay").performClick()
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
}
