package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.core.nowMs
import kotlin.test.Test

/**
 * A recording says so. The pane showed nothing at all while one ran
 * (user-caught, 2026-09-08), which made the button that stops it look
 * exactly like the button that takes a photo.
 */
@OptIn(ExperimentalTestApi::class)
class RecordingIndicatorTest {

    @Test
    fun itNamesItselfAndCountsUp() = runComposeUiTest {
        val startedAt = nowMs() - 7_000
        setContent { RecordingIndicator(startedAtMs = startedAt) }
        onNodeWithTag("capture-recording").assertExists()
        onNodeWithText("REC 0:07").assertExists()
    }

    @Test
    fun aRecordingPastTheMinuteStillReads() = runComposeUiTest {
        setContent { RecordingIndicator(startedAtMs = nowMs() - 754_000) }
        onNodeWithText("REC 12:34").assertExists()
    }
}
