package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RefetchGateTest {

    @Test
    fun identicalRequestsInsideTheWindowAreSkipped() {
        val gate = RefetchGate(30_000)
        assertTrue(gate.shouldFetch("a", 1_000))
        gate.recordFetch("a", 1_000)
        assertFalse(gate.shouldFetch("a", 5_000))
        assertFalse(gate.shouldFetch("a", 30_999))
        assertTrue(gate.shouldFetch("a", 31_000))
    }

    @Test
    fun aChangedKeyIsAlwaysNews() {
        val gate = RefetchGate(30_000)
        gate.recordFetch("a", 1_000)
        assertTrue(gate.shouldFetch("b", 1_001))
    }

    @Test
    fun anUnrecordedFetchRetriesNextPoll() {
        // The failure path: shouldFetch said yes, the fetch failed, nothing
        // recorded — the next poll must try again immediately.
        val gate = RefetchGate(30_000)
        assertTrue(gate.shouldFetch("a", 1_000))
        assertTrue(gate.shouldFetch("a", 1_001))
    }
}
