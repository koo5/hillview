package cz.hillview.plugin

/**
 * The upload schedule, decided in one place.
 *
 * The rule this file exists to keep — everything here is in service of it:
 *
 *     If any photo is waiting to upload, exactly one drain job is enqueued
 *     (or running) whose constraints match the CURRENT settings. If none is
 *     waiting, no drain job exists.
 *
 * Before this, the schedule was a side effect of whichever event happened to
 * fire: a capture enqueued a job, a settings save enqueued another with a
 * different constraint, and nothing at all watched the gap between "the queue
 * has work" and "a job exists that will run when conditions allow". Every bug
 * we found lived in that gap — a drain that finished leaving photos failed and
 * took the standing job with it, rows handed back by [StartupReconciler] that
 * nobody re-enqueued for, a stale UNMETERED job that ExistingWorkPolicy.KEEP
 * let swallow every later enqueue.
 *
 * So the schedule is a PROJECTION of queue state, not a pile of triggers.
 * Callers do not decide anything; they call the reconciler and it decides.
 *
 * [decideUploadSchedule] is deliberately pure — no Context, no WorkManager, no
 * clock — because this is the logic that was previously untestable, smeared
 * across five call sites. PhotoUploadManager applies whatever it returns.
 */

/** The settings half of the decision: may we upload at all? */
data class UploadGate(
    val autoUploadEnabled: Boolean,
    /** The drain refuses to upload without one, so a missing licence is a stop. */
    val hasLicense: Boolean,
    val wifiOnly: Boolean,
)

/**
 * The queue half.
 *
 * "Waiting" is deliberately coarse — pending plus failed, no backoff or
 * refinement-hold arithmetic. A row in backoff still deserves a parked job:
 * per-photo timing is the drain's business (isEligibleNow), and WorkManager's
 * own retry backoff paces the re-attempts. Modelling the timing twice would
 * mean two clocks that can disagree.
 */
data class UploadQueueSnapshot(val waiting: Int)

/**
 * What WorkManager already holds under our unique names.
 *
 * [wifiOnly] is the constraint baked into the EXISTING job, read back from its
 * tag — WorkInfo does not expose input data, and a job's constraint is fixed at
 * enqueue time, so this is the only way to notice it has gone stale.
 */
data class ScheduledUploadWork(
    val exists: Boolean,
    val running: Boolean,
    val wifiOnly: Boolean?,
)

/** What the reconciler decided. */
sealed class ScheduleAction {
    /** Nothing may or needs to run: drop every queued drain. */
    data class CancelAll(val why: String) : ScheduleAction()

    /**
     * A drain must exist with these constraints. [replaceExisting] means one is
     * already there but under the WRONG constraint, so it has to be cancelled
     * first — KEEP would otherwise drop the new request and leave the stale job
     * waiting on a network rule the user has since changed.
     */
    data class Ensure(
        val wifiOnly: Boolean,
        val expedited: Boolean,
        val replaceExisting: Boolean,
        val why: String,
    ) : ScheduleAction()

    /** Reality already matches. */
    data class Leave(val why: String) : ScheduleAction()
}

/**
 * @param leadingEdge first trigger of a capture burst — see PhotoUploadManager's
 *   coalescing window. Only decides expedited-vs-deferred, never whether a job
 *   exists.
 * @param bypassWifiOnly the manual retry button's documented bypass.
 */
fun decideUploadSchedule(
    gate: UploadGate,
    queue: UploadQueueSnapshot,
    existing: ScheduledUploadWork,
    leadingEdge: Boolean,
    bypassWifiOnly: Boolean,
): ScheduleAction {
    // A running drain is left alone, always. It reconciles again when it ends,
    // and cancelling it would be actively wrong: the row it is uploading right
    // now reads as neither pending nor failed, so an over-eager "nothing is
    // waiting" would cancel the very work it was measuring.
    if (existing.running) return ScheduleAction.Leave("a drain is running")

    if (!gate.autoUploadEnabled) return ScheduleAction.CancelAll("auto-upload is off")
    // Enqueueing against a closed gate is worse than not enqueueing: the job
    // holds the unique name it cannot use, and KEEP then drops the enqueue that
    // arrives once the gate opens.
    if (!gate.hasLicense) return ScheduleAction.CancelAll("no upload licence chosen")

    if (queue.waiting == 0) return ScheduleAction.CancelAll("nothing waiting to upload")

    val wifiOnly = gate.wifiOnly && !bypassWifiOnly
    if (existing.exists && existing.wifiOnly == wifiOnly) {
        return ScheduleAction.Leave("${queue.waiting} waiting, already scheduled")
    }
    return ScheduleAction.Ensure(
        wifiOnly = wifiOnly,
        expedited = leadingEdge,
        // Wrong-constraint job present → cancel it first.
        replaceExisting = existing.exists,
        why = if (existing.exists) {
            "network rule changed (was ${constraintName(existing.wifiOnly)}, " +
                "now ${constraintName(wifiOnly)})"
        } else {
            "${queue.waiting} waiting, nothing scheduled"
        },
    )
}

private fun constraintName(wifiOnly: Boolean?): String = when (wifiOnly) {
    true -> "unmetered"
    false -> "any network"
    null -> "unknown"
}
