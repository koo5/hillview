package cz.hillview.plugin

import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The write gate in front of the tracking tables (shared-kt). Pure rules, so
 * they run on the JVM with a fake clock rather than by sleeping — the two
 * bugs guarded here were both about WHEN the clock moves, which a real clock
 * makes awkward to say anything exact about.
 *
 * See docs/geo-election-test-todo.md item 2.
 */
class SourceRateGateTest {

    private var now = 0L
    private fun gate(intervalMs: Long = 10) = SourceRateGate(intervalMs) { now }

    @Test
    fun theFirstSampleFromASourceAlwaysLands() {
        val gate = gate()
        assertTrue(gate.allow(1))
        now = 1_000
        // A source that has never written is not held back by another's slot.
        assertTrue(gate.allow(2))
    }

    @Test
    fun aSecondSampleInsideTheIntervalIsDropped() {
        val gate = gate()
        assertTrue(gate.allow(1))
        now = 9
        assertFalse(gate.allow(1))
        now = 10
        assertTrue(gate.allow(1), "the interval is a floor, not a ceiling — 10 ms later is due")
    }

    @Test
    fun aRejectionDoesNotMoveTheClock() {
        // The starvation bug: the old gate stamped the clock on rejection as
        // well, so a stream arriving faster than the interval pushed its own
        // deadline away on every sample and NOTHING was ever stored again.
        val gate = gate()
        assertTrue(gate.allow(1))
        // Hammer at 1 ms — every one of these is a rejection that used to
        // reset the countdown.
        for (t in 1L..9L) {
            now = t
            assertFalse(gate.allow(1))
        }
        now = 10
        assertTrue(gate.allow(1), "a hammered source must still get its slot when the interval is up")
    }

    @Test
    fun aHammeredSourceKeepsLandingAtTheIntervalCadence() {
        // The same rule stated as a rate: 100 ms of 1 ms samples is 10 slots
        // (t=0 plus one every 10 ms), not one and then silence.
        val gate = gate()
        var stored = 0
        for (t in 0L..99L) {
            now = t
            if (gate.allow(1)) stored++
        }
        assertEquals(10, stored)
    }

    @Test
    fun oneRunawaySourceCannotStarveAnother() {
        // The slot-stealing bug: a 1 Hz gps-kalman bearing losing its write
        // to the ~10 Hz sensor stream, because both were gated on one clock.
        val gate = gate()
        val fast = 1
        val slow = 2
        var slowStored = 0
        for (t in 0L..999L) {
            now = t
            gate.allow(fast) // the ~1 kHz runaway
            if (t % 100L == 0L && gate.allow(slow)) slowStored++
        }
        assertEquals(10, slowStored, "the slow source's every sample must land — it is well inside its own floor")
    }

    @Test
    fun twoThreadsWritingOneSourceCannotBothPass() {
        // compute() is atomic per key; a read-then-write gate would let both
        // through and the pair would then collide on the composite key.
        val gate = gate()
        val threads = 8
        val start = CountDownLatch(1)
        val done = CountDownLatch(threads)
        val passed = AtomicInteger()
        val pool = Executors.newFixedThreadPool(threads)
        repeat(threads) {
            pool.execute {
                start.await()
                if (gate.allow(1)) passed.incrementAndGet()
                done.countDown()
            }
        }
        start.countDown()
        done.await()
        pool.shutdown()
        assertEquals(1, passed.get())
    }
}
