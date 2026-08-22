package cz.hillview.plugin

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The upload schedule's decision rules.
 *
 * These are the cases that used to be untestable — the logic lived in five
 * call sites that each needed a Context, WorkManager and a device to exercise.
 * Every test below names a failure we actually shipped.
 */
class UploadScheduleDecisionTest {

    private val openGate = UploadGate(
        autoUploadEnabled = true,
        hasLicense = true,
        wifiOnly = true,
    )
    private val nothingScheduled = ScheduledUploadWork(exists = false, running = false, wifiOnly = null)

    private fun decide(
        gate: UploadGate = openGate,
        waiting: Int = 1,
        existing: ScheduledUploadWork = nothingScheduled,
        leadingEdge: Boolean = true,
        bypassWifiOnly: Boolean = false,
    ) = decideUploadSchedule(
        gate, UploadQueueSnapshot(waiting), existing, leadingEdge, bypassWifiOnly,
    )

    @Test
    fun aWaitingQueueWithNoJobIsAlwaysScheduled() {
        // The whole point: photos waiting and nothing enqueued is the state in
        // which "Wi-Fi came back and nothing happened" becomes possible.
        val action = decide(waiting = 3)
        assertTrue(action is ScheduleAction.Ensure, "got $action")
        assertEquals(true, action.wifiOnly)
        assertEquals(false, action.replaceExisting)
    }

    @Test
    fun anEmptyQueueSchedulesNothing() {
        assertTrue(decide(waiting = 0) is ScheduleAction.CancelAll)
    }

    @Test
    fun aMatchingScheduleIsLeftAlone() {
        val existing = ScheduledUploadWork(exists = true, running = false, wifiOnly = true)
        assertTrue(decide(existing = existing) is ScheduleAction.Leave)
    }

    @Test
    fun aStaleNetworkRuleIsReplacedRatherThanKept() {
        // The KEEP trap: the constraint is fixed at enqueue time, so a job
        // parked under UNMETERED survives the user turning Wi-Fi-only off and
        // then swallows every later enqueue under the same unique name.
        val parkedUnderOldRule = ScheduledUploadWork(exists = true, running = false, wifiOnly = true)
        val action = decide(
            gate = openGate.copy(wifiOnly = false),
            existing = parkedUnderOldRule,
        )
        assertTrue(action is ScheduleAction.Ensure, "got $action")
        assertEquals(false, action.wifiOnly)
        assertTrue(action.replaceExisting, "the stale job must be cancelled first")
    }

    @Test
    fun aRunningDrainIsNeverDisturbed() {
        // A row being uploaded right now is neither pending nor failed, so the
        // queue reads empty — cancelling on that would kill the very drain the
        // snapshot was measuring. It reconciles again when it ends.
        val running = ScheduledUploadWork(exists = true, running = true, wifiOnly = true)
        assertTrue(decide(waiting = 0, existing = running) is ScheduleAction.Leave)
        assertTrue(decide(waiting = 5, existing = running) is ScheduleAction.Leave)
    }

    @Test
    fun aClosedGateCancelsInsteadOfParkingAnUnusableJob() {
        // Enqueueing against a shut gate is worse than not enqueueing: the job
        // holds the unique name it cannot use, so the enqueue that arrives when
        // the gate opens is dropped by KEEP.
        assertTrue(decide(gate = openGate.copy(autoUploadEnabled = false)) is ScheduleAction.CancelAll)
        assertTrue(decide(gate = openGate.copy(hasLicense = false)) is ScheduleAction.CancelAll)
    }

    @Test
    fun theRetryButtonKeepsItsWifiOnlyBypass() {
        val action = decide(bypassWifiOnly = true)
        assertTrue(action is ScheduleAction.Ensure, "got $action")
        assertEquals(false, action.wifiOnly, "a manual retry uploads on any network")
    }

    @Test
    fun theCoalescingWindowChoosesUrgencyNotExistence() {
        // Inside a capture burst the drain is deferred rather than expedited —
        // but a job still exists. Folding the window into the "should anything
        // be scheduled" question is what let bursts skip scheduling entirely.
        val action = decide(leadingEdge = false)
        assertTrue(action is ScheduleAction.Ensure, "got $action")
        assertEquals(false, action.expedited)
    }
}
