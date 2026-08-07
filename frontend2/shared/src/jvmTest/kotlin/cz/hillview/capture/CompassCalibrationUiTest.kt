package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.runComposeUiTest
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
