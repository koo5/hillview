package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class StillCaptureModeTest {

    @Test
    fun theDefaultIsLatencyNotTheLockingMode() {
        // The 3A lock (Quality) was the shutter lag the user felt; a fresh
        // install, and a pref written by an older build (no key), must not
        // pay it by default.
        assertEquals(StillCaptureMode.Latency, StillCaptureMode.DEFAULT)
        assertEquals(StillCaptureMode.Latency, StillCaptureMode.fromKey(null))
        assertEquals(StillCaptureMode.Latency, StillCaptureMode.fromKey("garbage"))
    }

    @Test
    fun keysRoundTrip() {
        StillCaptureMode.entries.forEach { mode ->
            assertEquals(mode, StillCaptureMode.fromKey(mode.key))
        }
    }

    @Test
    fun theJpegDefaultIsWhatQualityModeGaveImplicitly() {
        // CameraX: MAXIMIZE_QUALITY → 100, everything else → 95. Switching
        // the default mode must not quietly change the bytes, so 100 is
        // pinned and offered.
        assertEquals(100, DEFAULT_JPEG_QUALITY)
        assertTrue(DEFAULT_JPEG_QUALITY in JPEG_QUALITY_CHOICES)
    }
}
