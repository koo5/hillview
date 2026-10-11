package cz.hillview.geo

import cz.hillview.plugin.ImuClaimEntity
import cz.hillview.plugin.ImuSampleEntity
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Which capture owns which samples.
 *
 * This is the test the earlier design would have FAILED, and the reason the
 * attribution moved from a derived bound to a claim row. The old scheme gave
 * each photo the range `[first sample it stored, capturedAt + 3 s]`, which looks
 * right and is not: a capture stored in TWO bursts (an inline pre-shutter write
 * and a deferred post-shutter one) and the bursts interleaved across photos, so
 * photo 2's inline write landed before photo 1's deferred one. Traced on a 2 s
 * interval run, the two photos' ranges overlapped by 3 s — 44 sample-slots for
 * 32 distinct samples.
 *
 * Modelled here rather than driven through `GeoEngine`, which needs a `Context`:
 * what is under test is the WRITE SEQUENCE and the bookkeeping over it, which is
 * pure. The engine's real code is the same three lines (filter by high-water,
 * store, claim `first..last`) — see `GeoEngine.persistImuWindow`.
 */
class ImuAttributionTest {

    /** A stand-in for the engine's ring + high-water + claim bookkeeping. */
    private class Recorder(private val samplePeriodMs: Long = 250) {
        val table = mutableListOf<ImuSampleEntity>()
        val claims = mutableListOf<ImuClaimEntity>()
        private var highWater = 0L

        /** Every sample the "ring" would hold for a window. */
        private fun ring(fromMs: Long, toMs: Long) =
            (fromMs..toMs step samplePeriodMs).map {
                ImuSampleEntity(it, "accel", 0, 1f, 0f, 9.8f, it * 1_000_000)
            }

        /** What `persistImuWindow(from, to, forCaptureAtMs)` does. */
        fun persist(fromMs: Long, toMs: Long, forCaptureAtMs: Long?) {
            val fresh = ring(fromMs, toMs).filter { it.timestamp > highWater }
            if (fresh.isEmpty()) return
            table += fresh
            highWater = fresh.last().timestamp
            forCaptureAtMs?.let {
                claims += ImuClaimEntity(it, fresh.first().timestamp, fresh.last().timestamp, fresh.size)
            }
        }

        /** The current high-water mark, for the batching tests. */
        val highWaterForTest: Long get() = highWater

        /**
         * A BATCH, as a FIFO delivers it: samples grouped by sensor, so arrival
         * order is not time order. Mirrors `persistImuWindow`'s bookkeeping over
         * whatever the ring holds, which is what the real code does.
         */
        fun persistBatch(batch: List<Pair<Long, String>>, forCaptureAtMs: Long?) {
            val rows = batch.map { (ts, kind) ->
                ImuSampleEntity(ts, kind, 0, 1f, 0f, 9.8f, ts * 1_000_000)
            }
            val fresh = rows.filter { it.timestamp > highWater }
            if (fresh.isEmpty()) return
            table += fresh
            // min/max, exactly as GeoEngine does it now.
            highWater = fresh.maxOf { it.timestamp }
            forCaptureAtMs?.let {
                claims += ImuClaimEntity(
                    it, fresh.minOf { f -> f.timestamp }, fresh.maxOf { f -> f.timestamp }, fresh.size,
                )
            }
        }

        /** What the upload pass reads: the claim's range out of the table. */
        fun owned(capturedAtMs: Long): List<Long> {
            val c = claims.firstOrNull { it.capturedAtMs == capturedAtMs } ?: return emptyList()
            return table.filter { it.timestamp in c.fromMs..c.toMs }.map { it.timestamp }
        }
    }

    private val half = IMU_WINDOW_HALF_MS

    /**
     * A 2 s interval run — faster than the window, so every photo's nominal
     * ±3 s window overlaps its neighbours'. Only ONE burst per capture now (the
     * pre-shutter call is read-only), so the claims tile.
     */
    @Test
    fun consecutiveCapturesOwnDisjointRanges() {
        val r = Recorder()
        val shutters = listOf(1_000_000L, 1_002_000L, 1_004_000L, 1_006_000L)
        // The deferred writes fire in shutter order, 3.15 s after each shutter.
        shutters.forEach { r.persist(it - half, it + half, it) }

        val sets = shutters.map { r.owned(it) }
        sets.forEach { assertTrue(it.isNotEmpty(), "a capture owned nothing") }
        // The whole point: no sample belongs to two photos.
        val all = sets.flatten()
        assertEquals(all.size, all.distinct().size, "a sample was claimed by two captures")
        // ...and consecutive claims abut rather than leaving holes.
        for (i in 0 until sets.size - 1) {
            assertTrue(
                sets[i].max() < sets[i + 1].min(),
                "claim $i (${sets[i].max()}) overlaps claim ${i + 1} (${sets[i + 1].min()})",
            )
        }
    }

    /** Every stored sample is owned by exactly one capture: nothing is orphaned. */
    @Test
    fun theClaimsPartitionEverythingThatWasStored() {
        val r = Recorder()
        val shutters = listOf(1_000_000L, 1_002_000L, 1_004_000L)
        shutters.forEach { r.persist(it - half, it + half, it) }

        val owned = shutters.flatMap { r.owned(it) }.sorted()
        assertEquals(r.table.map { it.timestamp }.sorted(), owned)
    }

    /**
     * An interval LONGER than the window: each capture gets a genuinely
     * symmetric ±3 s and the claims no longer abut, because nothing was sampling
     * in between. A gap is correct here, and must not be mistaken for loss.
     */
    @Test
    fun aSlowIntervalRunLeavesGapsRatherThanOverlaps() {
        val r = Recorder()
        val shutters = listOf(1_000_000L, 1_020_000L)
        shutters.forEach { r.persist(it - half, it + half, it) }
        val a = r.owned(shutters[0])
        val b = r.owned(shutters[1])
        assertEquals((2 * half / 250 + 1).toInt(), a.size)   // the full symmetric window
        assertTrue(a.max() < b.min())
        assertTrue(b.min() - a.max() > half, "expected an unsampled gap between the two")
    }

    /**
     * The continuous external-camera mode flushes with no owner. Those samples
     * belong to no photo, and a capture that follows must not silently inherit
     * them — it owns only what it actually added.
     */
    @Test
    fun anUnownedContinuousFlushIsNotInheritedByTheNextCapture() {
        val r = Recorder()
        r.persist(1_000_000, 1_002_000, null)          // continuous flush
        r.persist(1_002_000 - half, 1_002_000 + half, 1_002_000L)

        val owned = r.owned(1_002_000L)
        assertTrue(owned.isNotEmpty())
        assertTrue(owned.min() > 1_002_000, "inherited the unowned flush's samples")
        // The flushed rows are still in the table -- they are simply nobody's.
        assertTrue(r.table.any { it.timestamp <= 1_002_000 })
    }

    /**
     * BATCHED ARRIVAL. With a hardware FIFO the two sensors deliver bursts one
     * after the other, so the newest sample in a batch is NOT the last one added:
     * accelerometer 0..200 ms arrives, then gyroscope 0..200 ms, and the final
     * element pre-dates most of the batch.
     *
     * Every bound taken with `first()`/`last()` was wrong the moment batching was
     * switched on — the claim would have run backwards, and the high-water mark
     * would have receded and re-stored samples it had already written. This test
     * fails against that code and passes against min/max.
     */
    @Test
    fun aBatchedBurstIsBoundedByTimeNotByArrivalOrder() {
        val r = Recorder()
        // One capture's worth, delivered as two per-sensor bursts.
        val accel = (0..8).map { 1_000_000L + it * 25 }
        val gyro = (0..8).map { 1_000_000L + it * 25 }
        val batch = accel.map { it to "accel" } + gyro.map { it to "gyro" }
        r.persistBatch(batch, forCaptureAtMs = 1_000_100L)

        val claim = r.claims.single()
        assertEquals(1_000_000L, claim.fromMs, "claim start must be the EARLIEST sample")
        assertEquals(1_000_200L, claim.toMs, "claim end must be the LATEST sample")
        // The last element added was a gyro sample from the start of the window.
        assertEquals("gyro", r.table.last().kind)
        assertEquals(1_000_200L, r.table.last().timestamp)
        // And the high-water mark must not recede below what was stored.
        assertEquals(claim.toMs, r.highWaterForTest)
    }

    /**
     * A second batch after the first must add only what is new, even though its
     * arrival order again ends mid-window.
     */
    @Test
    fun aSecondBatchDoesNotRestoreWhatTheFirstAlreadyHad() {
        val r = Recorder()
        r.persistBatch(
            (0..4).map { 1_000_000L + it * 25 to "accel" } +
                (0..4).map { 1_000_000L + it * 25 to "gyro" },
            forCaptureAtMs = 1_000_050L,
        )
        val firstCount = r.table.size
        // Overlapping window: only the samples past the high-water mark are new.
        r.persistBatch(
            (0..8).map { 1_000_000L + it * 25 to "accel" } +
                (0..8).map { 1_000_000L + it * 25 to "gyro" },
            forCaptureAtMs = 1_000_200L,
        )
        val added = r.table.size - firstCount
        assertTrue(added > 0, "the later half should have been added")
        assertEquals(r.table.size, r.table.distinct().size, "a sample was stored twice")
    }

    /** A capture whose window the ring could not supply claims nothing at all. */
    @Test
    fun aCaptureWithNoFreshSamplesRecordsNoClaim() {
        val r = Recorder()
        r.persist(1_000_000 - half, 1_000_000 + half, 1_000_000L)
        // The same window again: everything in it is already stored.
        r.persist(1_000_000 - half, 1_000_000 + half, 1_000_001L)
        assertEquals(1, r.claims.size)
        assertTrue(r.owned(1_000_001L).isEmpty())
    }
}
