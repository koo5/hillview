package cz.hillview.capture

import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CaptureStatsTest {

    @BeforeTest
    fun clean() {
        CaptureStatsLog.reset()
        CaptureStatsLog.platformLines = { emptyList() }
    }

    @Test
    fun metricsAggregate() {
        CaptureStatsLog.record("shutter→jpeg", 500, nowMs = 1_000)
        CaptureStatsLog.record("shutter→jpeg", 700, nowMs = 3_000)
        CaptureStatsLog.record("shutter→jpeg", 300, nowMs = 5_000)
        val text = CaptureStatsLog.snapshotText(nowMs = 11_000)
        assertTrue("window: 10s" in text, text)
        assertTrue("shutter→jpeg: n=3 last=300 avg=500 min=300 max=700 ms" in text, text)
    }

    @Test
    fun countersAndPlatformLinesJoinTheText() {
        CaptureStatsLog.increment("preview binds", nowMs = 1_000)
        CaptureStatsLog.increment("preview binds", nowMs = 2_000)
        CaptureStatsLog.platformLines = { listOf("thermal: LIGHT") }
        val text = CaptureStatsLog.snapshotText(nowMs = 2_000)
        assertTrue("preview binds: 2" in text, text)
        assertTrue("thermal: LIGHT" in text, text)
    }

    @Test
    fun resetClearsEverything() {
        CaptureStatsLog.record("cadence", 2_000, nowMs = 1_000)
        CaptureStatsLog.reset()
        assertEquals("window: 0s", CaptureStatsLog.snapshotText(nowMs = 9_000))
    }
}
