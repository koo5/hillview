package cz.hillview.settings

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Which activities RECORD. Read in three places now — what the geo hardware
 * runs, whether entering arms tracking, and whether the bearing ring has to
 * be held — so the three cannot be allowed to drift apart.
 */
class RecordingActivityTest {

    @Test
    fun captureAndExternalRecordAndViewDoesNot() {
        assertTrue(isRecordingActivity("capture"))
        assertTrue(isRecordingActivity("external"), "another app's shutter, this app's record")
        assertFalse(isRecordingActivity("view"))
    }

    @Test
    fun anUnknownActivityRecordsNothing() {
        // A persisted setting from a future build, or a typo: the safe answer
        // is the one that starts no hardware.
        assertFalse(isRecordingActivity(""))
        assertFalse(isRecordingActivity("gallery"))
    }
}
