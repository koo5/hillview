package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.map.BearingMode
import kotlin.test.Test

/**
 * The level indicator on the capture overlay.
 *
 * `CaptureLevelFixtureTest` owns the arithmetic against `capture_pose`; this owns
 * only what reaches the screen — that the words appear, that a mount does not get
 * told to straighten itself, and that an unmeasured pose speaks exactly when
 * silence would cost the photo its publication.
 */
@OptIn(ExperimentalTestApi::class)
class LevelIndicatorUiTest {

    private fun state(pitch: Float?, roll: Float?) = CaptureState(
        ready = true,
        bearingDeg = 273.1f,
        pitchDeg = pitch,
        imageRollDeg = roll,
        fixLatitude = 50.115044,
        fixLongitude = 14.500907,
    )

    @Test
    fun aLevelShotSaysSo() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = 3.0f, roll = 2.0f),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertIsDisplayed().assertTextContains(
            "⊾ Level",
        )
    }

    /** The 2026-11-15 series' own pose: 3.7° up, the phone turned 22.9°. */
    @Test
    fun aRolledShotNamesTheHorizonTilt() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = 3.7f, roll = 22.9f),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertTextContains("⊾ Horizon tilted 23°")
    }

    /** A level LANDSCAPE shot is level: the quarter turn is the image's own. */
    @Test
    fun aLevelLandscapeShotIsNotTilted() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = 1.0f, roll = 88.0f),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertTextContains("⊾ Level")
    }

    @Test
    fun pointingAtTheSkyIsSaidAsSuch() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = 82.0f, roll = 4.0f),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertTextContains("⊾ Pointing at the sky")
    }

    /** A phone on a mount is not being aimed. Telling its owner to level it is noise. */
    @Test
    fun carModeShowsNoIndicator() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = 40.0f, roll = 30.0f),
                bearingMode = BearingMode.Car,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertDoesNotExist()
    }

    /**
     * No attitude and no Panoramax: a missing number that costs this photo nothing
     * does not earn a line of a viewfinder.
     */
    @Test
    fun anUnmeasuredPoseStaysQuietUnlessItCosts() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = null, roll = null),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
            )
        }
        onNodeWithTag("level-indicator").assertDoesNotExist()
    }

    /** ...and with sharing on, it says what the silence would have cost. */
    @Test
    fun anUnmeasuredPoseSpeaksWhenItWouldBlockPublication() = runComposeUiTest {
        setContent {
            CameraOverlayUi(
                state = state(pitch = null, roll = null),
                bearingMode = BearingMode.Walking,
                overridePosition = null,
                opacityLevel = 3,
                onCycleOpacity = {},
                // The hint owns the pill for 4 s after the camera comes ready, and it
                // replaces these rows rather than sitting beside them.
                suppressHint = true,
                panoramaxShare = true,
            )
        }
        onNodeWithTag("level-indicator").assertTextContains(
            "⊾ not measured — won't be published",
        )
    }
}
