package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The IMU ring buffer: wraparound, window bounds, and the per-millisecond
 * sequencing that keeps two samples from the same millisecond from replacing
 * each other in the table.
 *
 * Real logic, and briefly untestable — it started life private inside
 * `GeoEngine`, which needs a `Context`. See the class doc for why it now has
 * its own file.
 */
class ImuRingTest {

    private fun ring(capacity: Int = 8) = ImuRing(capacity)

    private fun ImuRing.accel(atMs: Long, v: Float = 1f, nanos: Long = atMs * 1_000_000) =
        add(atMs, nanos, ImuRing.KIND_ACCEL, v, 0f, 0f)

    private fun ImuRing.gyro(atMs: Long, v: Float = 0.1f, nanos: Long = atMs * 1_000_000) =
        add(atMs, nanos, ImuRing.KIND_GYRO, v, 0f, 0f)

    @Test
    fun anEmptyRingHasNoWindow() {
        assertTrue(ring().window(0, 10_000).isEmpty())
    }

    @Test
    fun theWindowIsInclusiveOfBothBoundsAndOrderedOldestFirst() {
        val r = ring()
        listOf(100L, 200L, 300L, 400L).forEach { r.accel(it) }
        val w = r.window(200, 300)
        assertEquals(listOf(200L, 300L), w.map { it.timestamp })
    }

    @Test
    fun samplesOutsideTheWindowAreNotReturned() {
        val r = ring()
        listOf(10L, 500L, 990L).forEach { r.accel(it) }
        assertEquals(listOf(500L), r.window(100, 900).map { it.timestamp })
    }

    /**
     * The buffer is fixed-size: once full, the oldest sample is the one that
     * goes. Nothing may be returned twice, and nothing stale may survive as a
     * leftover of the array it was written into.
     */
    @Test
    fun awraparoundDropsTheOldestAndNeverDuplicates() {
        val r = ring(capacity = 4)
        listOf(1L, 2L, 3L, 4L, 5L, 6L).forEach { r.accel(it) }
        val w = r.window(0, 1_000)
        assertEquals(listOf(3L, 4L, 5L, 6L), w.map { it.timestamp })
        assertEquals(w.size, w.distinct().size)
    }

    @Test
    fun awraparoundManyTimesOverStillReturnsExactlyOneBufferful() {
        val r = ring(capacity = 4)
        (1L..100L).forEach { r.accel(it) }
        assertEquals(listOf(97L, 98L, 99L, 100L), r.window(0, 1_000).map { it.timestamp })
    }

    /**
     * The point of the composite key. At 200 Hz two samples land in the same
     * millisecond; without a per-millisecond sequence the second would REPLACE
     * the first on insert, which is the bug the bearings table's composite key
     * was added to stop.
     */
    @Test
    fun twoSamplesInOneMillisecondGetDistinctSequences() {
        val r = ring()
        r.accel(500, v = 1f)
        r.accel(500, v = 2f)
        r.accel(500, v = 3f)
        val w = r.window(500, 500)
        assertEquals(listOf(0, 1, 2), w.map { it.sequence })
        // The whole row must be distinct, which is what the table requires.
        assertEquals(3, w.map { Triple(it.timestamp, it.kind, it.sequence) }.distinct().size)
        assertEquals(listOf(1f, 2f, 3f), w.map { it.x })
    }

    /**
     * The two sensors are counted SEPARATELY: they arrive on their own
     * callbacks, and an accelerometer sample sharing a millisecond with a
     * gyroscope sample is not a collision — `kind` is part of the key.
     */
    @Test
    fun theTwoSensorsSequenceIndependentlyWithinAMillisecond() {
        val r = ring()
        r.accel(500)
        r.gyro(500)
        r.accel(500)
        val w = r.window(500, 500)
        assertEquals(
            listOf("accel" to 0, "gyro" to 0, "accel" to 1),
            w.map { it.kind to it.sequence },
        )
    }

    /** Both sensors come back from one window — pairing them is not this class's job. */
    @Test
    fun aWindowCarriesBothKinds() {
        val r = ring()
        r.accel(100)
        r.gyro(110)
        r.accel(120)
        assertEquals(listOf("accel", "gyro", "accel"), r.window(0, 200).map { it.kind })
    }

    /** The monotonic clock travels beside the wall clock — it is the join key. */
    @Test
    fun theSensorsOwnNanosecondClockIsKept() {
        val r = ring()
        r.add(500, 123_456_789L, ImuRing.KIND_ACCEL, 1f, 2f, 3f)
        val s = r.window(500, 500).single()
        assertEquals(123_456_789L, s.elapsedNanos)
        assertEquals(1f, s.x)
        assertEquals(2f, s.y)
        assertEquals(3f, s.z)
    }

    /**
     * Stopping the sensors clears the ring. A window served from a stale buffer
     * after a gap would attach old motion to a new exposure — the same class of
     * lie as the invented `0f` pitch this project removed.
     */
    @Test
    fun clearingLeavesNothingBehind() {
        val r = ring()
        listOf(100L, 200L).forEach { r.accel(it) }
        r.clear()
        assertTrue(r.window(0, 1_000).isEmpty())
        // ...and the array's leftovers do not reappear as the ring refills.
        r.accel(300)
        assertEquals(listOf(300L), r.window(0, 1_000).map { it.timestamp })
    }

    /**
     * The dedup mark: the newest sample's timestamp, which is what lets
     * consecutive photo windows tile a session instead of repeating most of it.
     */
    @Test
    fun theNewestTimestampIsReportedForDeduplication() {
        val r = ring()
        assertEquals(null, r.newestMs())
        r.accel(100)
        r.accel(250)
        assertEquals(250L, r.newestMs())
        // Survives a wraparound — it is the write cursor, not index 0.
        val small = ring(capacity = 2)
        listOf(1L, 2L, 3L).forEach { small.accel(it) }
        assertEquals(3L, small.newestMs())
        r.clear()
        assertEquals(null, r.newestMs())
    }

    /** A window narrower than the sample spacing is empty, not nearest-neighbour. */
    @Test
    fun aWindowThatContainsNothingIsEmptyRatherThanApproximate() {
        val r = ring()
        r.accel(100)
        r.accel(900)
        assertTrue(r.window(400, 600).isEmpty())
    }
}
