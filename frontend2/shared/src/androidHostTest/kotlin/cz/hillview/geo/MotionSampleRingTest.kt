package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class MotionSampleRingTest {
    private val ms = 1_000_000L

    private fun add(ring: MotionSampleRing, atMs: Long, value: Float = atMs.toFloat()) {
        ring.add(atMs, atMs * ms, true, value, 2f, 3f, true, 4f, 5f, 6f)
    }

    @Test
    fun nearestFindsEitherSideAndHonoursToleranceAndTies() {
        val ring = MotionSampleRing(1_000 * ms, 8)
        add(ring, 100)
        add(ring, 200)
        assertEquals(100L, ring.nearest(120 * ms, 20 * ms)?.atMs)
        assertEquals(200L, ring.nearest(180 * ms, 20 * ms)?.atMs)
        assertEquals(100L, ring.nearest(150 * ms, 50 * ms)?.atMs)
        assertNull(ring.nearest(221 * ms, 20 * ms))
        assertNull(ring.nearest(0, 1_000 * ms))
    }

    @Test
    fun missingVectorsAndInvalidTimestampsRemainDistinguishableFromZeroes() {
        val ring = MotionSampleRing(1_000 * ms, 8)
        ring.add(100, 0, true, 0f, 0f, 0f, false, 0f, 0f, 0f)
        assertEquals(0, ring.size)
        assertNull(ring.nearest(100 * ms, 100 * ms))
        ring.add(100, 100 * ms, true, 0f, 0f, 0f, false, 9f, 9f, 9f)
        val sample = assertNotNull(ring.nearest(100 * ms, 0))
        assertEquals(listOf(0f, 0f, 0f), sample.gravity)
        assertNull(sample.linearAcceleration)
    }

    @Test
    fun ageEvictionAndWraparoundKeepTheWindowWithoutReportingACap() {
        val ring = MotionSampleRing(200 * ms, 3)
        for (at in 100L..1_000L step 100L) add(ring, at)
        assertEquals(3, ring.size)
        assertEquals(200 * ms, ring.spanNs)
        assertFalse(ring.capped)
        assertNull(ring.nearest(700 * ms, 0))
        assertEquals(800L, ring.nearest(800 * ms, 0)?.atMs)
        assertEquals(1_000L, ring.nearest(1_000 * ms, 0)?.atMs)
    }

    @Test
    fun capacityEvictionIsReportedAndReturnedSnapshotsSurviveSlotReuse() {
        val ring = MotionSampleRing(8_000 * ms, 2)
        add(ring, 100)
        val snapshot = assertNotNull(ring.nearest(100 * ms, 0))
        add(ring, 200)
        add(ring, 300)
        add(ring, 400)
        assertEquals(2, ring.size)
        assertTrue(ring.capped)
        assertNull(ring.nearest(100 * ms, 0))
        assertEquals(100L, snapshot.atMs)
        assertEquals(listOf(100f, 2f, 3f), snapshot.gravity)
        assertEquals(listOf(4f, 5f, 6f), snapshot.linearAcceleration)
    }

    @Test
    fun outOfOrderCallbacksAreSearchedByTheirActualTimestamp() {
        val ring = MotionSampleRing(1_000 * ms, 8)
        add(ring, 100)
        add(ring, 300)
        add(ring, 200)
        assertEquals(200L, ring.nearest(205 * ms, 5 * ms)?.atMs)
        assertEquals(300L, ring.nearest(295 * ms, 5 * ms)?.atMs)
    }

    @Test
    fun aKilohertzStreamRetainsTheFullEightSecondHistory() {
        val ring = MotionSampleRing(AT_EXPOSURE_RING_WINDOW_NS, AT_EXPOSURE_RING_MAX_SAMPLES)
        for (at in 1L..20_000L) add(ring, at)
        assertEquals(8_001, ring.size)
        assertEquals(8_000 * ms, ring.spanNs)
        assertFalse(ring.capped)
        assertEquals(12_000L, ring.nearest(12_000 * ms, 0)?.atMs)
        assertEquals(18_000L, ring.nearest(18_000 * ms, 0)?.atMs)
        assertNull(ring.nearest(11_999 * ms, 0))
    }
}
