package cz.hillview.plugin

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * A worker-busy 503 resumes the drain at the WORKER's pace (its Retry-After),
 * not WorkManager's exponential backoff — and within bounds, so a missing or
 * hostile header can neither make a client hammer nor vanish for hours
 * (PhotoUploadManager.resumeAfterWorkerBusy, 2026-11-06).
 */
class WorkerBusyResumeTest {

    @Test
    fun retryAfterIsReadAsSecondsOnly() {
        assertEquals(500L, retryAfterSeconds("500"))
        assertEquals(30L, retryAfterSeconds(" 30 "))
        assertNull(retryAfterSeconds(null))
        assertNull(retryAfterSeconds("Fri, 07 Nov 2026 10:00:00 GMT"), "the HTTP-date form is not parsed")
        assertNull(retryAfterSeconds("-5"))
    }

    @Test
    fun theWorkersPaceIsHonouredAndNeverShortened() {
        assertEquals(500_000L, busyResumeDelayMs(500, 0.0))
        // Jitter only ever adds, at most a quarter.
        assertEquals(625_000L, busyResumeDelayMs(500, 1.0))
    }

    @Test
    fun noHeaderMeansTheWorkersDefault() {
        assertEquals(BUSY_RESUME_DEFAULT_S * 1000, busyResumeDelayMs(null, 0.0))
    }

    @Test
    fun anOddHeaderCannotMakeAClientHammerOrVanish() {
        assertEquals(BUSY_RESUME_MIN_S * 1000, busyResumeDelayMs(0, 0.0))
        assertEquals(BUSY_RESUME_MAX_S * 1000, busyResumeDelayMs(86_400, 0.0))
    }
}
