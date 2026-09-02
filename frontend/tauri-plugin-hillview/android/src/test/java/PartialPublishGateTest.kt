package cz.hillview.plugin

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The publish policy shared by all three marker pipelines: first arrival now,
 * later arrivals collapsed into one trailing publish per throttle window, the
 * settled publish immediate and final.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PartialPublishGateTest {

    @Test
    fun theFirstArrivalPublishesAtOnce() = runTest {
        val log = mutableListOf<Pair<Long, Boolean>>()
        val gate = PartialPublishGate(this, 300, { currentTime }) { complete -> log += currentTime to complete }

        gate.arrived()
        runCurrent()

        assertEquals(listOf(0L to false), log)
    }

    @Test
    fun arrivalsInsideTheWindowCollapseIntoOneTrailingPublish() = runTest {
        val log = mutableListOf<Pair<Long, Boolean>>()
        val gate = PartialPublishGate(this, 300, { currentTime }) { complete -> log += currentTime to complete }

        gate.arrived(); runCurrent()              // t=0: immediate
        advanceTimeBy(50); gate.arrived()
        advanceTimeBy(50); gate.arrived()
        advanceTimeBy(50); gate.arrived()
        runCurrent()
        assertEquals("nothing more inside the window", 1, log.size)

        advanceUntilIdle()
        assertEquals(listOf(0L to false, 300L to false), log)
    }

    @Test
    fun anArrivalAfterTheWindowIsImmediateAgain() = runTest {
        val log = mutableListOf<Pair<Long, Boolean>>()
        val gate = PartialPublishGate(this, 300, { currentTime }) { complete -> log += currentTime to complete }

        gate.arrived(); runCurrent()
        advanceTimeBy(1000)
        gate.arrived(); runCurrent()

        assertEquals(listOf(0L to false, 1000L to false), log)
    }

    @Test
    fun settleDropsThePendingPartialAndPublishesTheSettledSetNow() = runTest {
        val log = mutableListOf<Pair<Long, Boolean>>()
        val gate = PartialPublishGate(this, 300, { currentTime }) { complete -> log += currentTime to complete }

        gate.arrived(); runCurrent()
        advanceTimeBy(100); gate.arrived()        // pending trailing partial at t=300
        advanceTimeBy(50)
        gate.settle()
        advanceUntilIdle()

        assertEquals(listOf(0L to false, 150L to true), log)
    }

    @Test
    fun nothingGoesOutAfterSettle() = runTest {
        val log = mutableListOf<Boolean>()
        val gate = PartialPublishGate(this, 300, { currentTime }) { complete -> log += complete }

        gate.settle()
        gate.arrived()
        advanceUntilIdle()

        assertEquals(listOf(true), log)
    }

    @Test
    fun cancellingTheScopeDropsAPendingPartial() = runTest {
        val log = mutableListOf<Boolean>()
        val area = CoroutineScope(coroutineContext + Job())
        val gate = PartialPublishGate(area, 300, { currentTime }) { complete -> log += complete }

        gate.arrived(); runCurrent()
        advanceTimeBy(100); gate.arrived()        // pending
        area.cancel()
        advanceUntilIdle()

        assertEquals(listOf(false), log)
    }
}
