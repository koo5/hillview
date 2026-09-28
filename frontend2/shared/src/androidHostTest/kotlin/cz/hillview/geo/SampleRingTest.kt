package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The history a capture asks "what was the device doing when the shutter was open".
 *
 * The rules worth pinning are the ones that fail silently: a sample with no monotonic
 * instant must not be stored (it could never match, and a ring full of them would look
 * like a working ring that always declines), and a lookup with nothing near the instant
 * must DECLINE rather than return the closest thing it has — because the caller's
 * fallback is the press-time value, which is honest, whereas a 3-second-old attitude
 * presented as the frame's is not.
 */
class SampleRingTest {

    private data class Sample(val ns: Long, val tag: String)

    private val ms = 1_000_000L

    /** Time-bounded, like the real thing; the count cap is out of the way by default. */
    private fun ring(windowMs: Long = 1_000, maxSamples: Int = 100_000) =
        SampleRing<Sample>(windowMs * ms, maxSamples) { it.ns }

    @Test
    fun itFindsTheNearestSampleOnEitherSideOfTheInstant() {
        val r = ring()
        listOf(100L, 200L, 300L, 400L).forEach { r.add(Sample(it * ms, "at$it")) }
        // Closest BELOW.
        assertEquals("at300", r.nearest(310 * ms, 250 * ms)?.tag)
        // Closest ABOVE — deliberately allowed: a sample 10 ms after the exposure
        // describes the frame better than one 90 ms before it.
        assertEquals("at400", r.nearest(390 * ms, 250 * ms)?.tag)
        // Exactly between: either is within tolerance, and it must pick one, not null.
        assertTrue(r.nearest(250 * ms, 250 * ms) != null)
    }

    @Test
    fun itDeclinesWhenNothingIsNearEnough() {
        val r = ring()
        r.add(Sample(100 * ms, "old"))
        assertNull(r.nearest(1_000 * ms, 250 * ms), "a 900 ms-old sample must not pass as the frame's")
        // The boundary is inclusive, so a sample exactly at the tolerance still counts.
        assertEquals("old", r.nearest(350 * ms, 250 * ms)?.tag)
    }

    /**
     * A producer that does not set the monotonic instant yields 0, which can never be
     * matched against a real exposure. Storing those would fill the ring with entries
     * that always decline — indistinguishable from a stream that has stopped.
     */
    @Test
    fun samplesWithNoMonotonicInstantAreNotKept() {
        val r = ring()
        r.add(Sample(0L, "unstamped"))
        r.add(Sample(-5L, "nonsense"))
        assertEquals(0, r.size)
        assertNull(r.nearest(100 * ms, 250 * ms))
    }

    @Test
    fun itDropsWhatIsOlderThanTheWindow() {
        val r = ring(windowMs = 150)
        listOf(100L, 200L, 300L, 400L).forEach { r.add(Sample(it * ms, "at$it")) }
        assertNull(r.nearest(100 * ms, 50 * ms), "the oldest should have been evicted")
        assertEquals("at400", r.nearest(400 * ms, 50 * ms)?.tag)
        assertEquals("at300", r.nearest(300 * ms, 50 * ms)?.tag, "the window's edge stays")
    }

    /**
     * THE BUG THIS CLASS WAS REWRITTEN FOR, as a test.
     *
     * A count-bounded ring's span is capacity/rate, so it shrinks when something else
     * raises the rate — and that is not hypothetical: registering the accelerometer at
     * SENSOR_DELAY_FASTEST for the IMU window raised gravity and linear acceleration
     * from the 33 Hz this ring's owner asked for to ~478 Hz each, and 256 samples that
     * were meant to be 7.7 s became 268 ms. Twelve of seventy uploaded photos fell back
     * to the press because the save outran the history.
     *
     * Time-bounded, the same 30x rate change costs memory and nothing else.
     */
    @Test
    fun thirtyTimesTheSampleRateDoesNotShortenTheHistory() {
        val slow = ring(windowMs = 8_000)
        val fast = ring(windowMs = 8_000)
        // 33 Hz and ~1 kHz, both covering the same 8 seconds of wall time.
        (0 until 8_000 / 30).forEach { slow.add(Sample(it * 30L * ms, "s$it")) }
        (0 until 8_000).forEach { fast.add(Sample(it * 1L * ms, "f$it")) }
        // The exposure, 2 s before the save asks — the worst exposure_to_jpeg measured.
        for (r in listOf(slow, fast)) {
            val newest = 8_000 * ms - 1
            assertTrue(
                r.nearest(newest - 2_000 * ms, AT_EXPOSURE_TOLERANCE_NS) != null,
                "a 2 s-old exposure must still be findable at ${r.size} samples",
            )
            assertTrue(r.spanNs >= 7_000 * ms, "span was ${r.spanNs / ms}ms")
        }
    }

    /**
     * The backstop must SAY it bound. The previous version of this failure was silent,
     * which is why it took uploaded photos to find rather than a log line.
     */
    @Test
    fun theMemoryCapAnnouncesItselfWhenItBinds() {
        val r = ring(windowMs = 8_000, maxSamples = 10)
        (0 until 50).forEach { r.add(Sample(it * 1L * ms, "f$it")) }
        assertEquals(10, r.size)
        assertTrue(r.capped, "a cap that evicts inside the window must not do it quietly")
        assertTrue(ring(windowMs = 8_000).also { it.add(Sample(ms, "a")) }.capped.not())
    }

    /** A lookup before anything has been recorded, and with no instant to look up. */
    @Test
    fun anEmptyRingAndAnUnknownInstantBothDecline() {
        assertNull(ring().nearest(100 * ms, 250 * ms))
        val r = ring()
        r.add(Sample(100 * ms, "a"))
        assertNull(r.nearest(0L, 250 * ms), "no exposure instant means no lookup")
    }

    /**
     * The real cadence, as a sanity check on the tolerance: at 33 Hz the nearest sample
     * is never more than half a period away, so the tolerance is not what decides
     * ordinary captures — it only governs a stalled stream.
     */
    @Test
    fun atTheRealSensorRateEveryLookupHitsWithinHalfAPeriod() {
        val r = SampleRing<Sample>(
            AT_EXPOSURE_RING_WINDOW_NS, AT_EXPOSURE_RING_MAX_SAMPLES,
        ) { it.ns }
        val period = 30 * ms
        (0 until 200).forEach { r.add(Sample(it * period, "s$it")) }
        for (probe in listOf(37L, 1_004L, 2_999L, 5_000L)) {
            val at = probe * ms
            val hit = r.nearest(at, AT_EXPOSURE_TOLERANCE_NS)
            assertTrue(hit != null, "no hit at ${probe}ms")
            assertTrue(
                kotlin.math.abs(hit!!.ns - at) <= period / 2,
                "hit was ${(hit.ns - at) / ms}ms away at ${probe}ms",
            )
        }
    }
}
