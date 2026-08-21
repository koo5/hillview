package cz.hillview.plugin

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.work.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

class PhotoUploadManager(private val context: Context) {
    companion object {
        private const val TAG = "hv-PhotoUploadManager"

        // Coalescing window for capture bursts. The first capture in a window
        // uploads immediately (expedited + foreground notification); captures
        // within WINDOW_MS fold into ONE durable, deferred batch run that
        // fires WINDOW_MS after the window opened. This turns a burst of N
        // captures into at most one foreground promotion + one cheap
        // background drain, instead of one foreground worker per photo — which
        // churns SystemForegroundService on the main thread and freezes the UI
        // (and previously crashed via ForegroundServiceDidNotStartInTime).
        // The in-memory timestamp only decides immediate-vs-batch; durability
        // is WorkManager's — both are persisted jobs that survive app close.
        // Experiment knob: bump WINDOW_MS for a longer batch delay. Foreground
        // promotion is decided in the worker by app-backgrounded state, so the
        // notification appears only for a backgrounded drain, never while shooting.
        private const val WINDOW_MS = 15_000L
        private const val WORK_NOW = "photo_upload_now"
        private const val WORK_BATCH = "photo_upload_batch"
        private var lastImmediateMs = 0L

        // The enqueued job's network rule, as a tag: WorkInfo exposes tags but
        // neither input data nor constraints, and noticing that a parked job's
        // rule has gone stale is the whole point.
        const val TAG_UNMETERED = "upload-constraint:unmetered"
        const val TAG_ANY_NETWORK = "upload-constraint:any"

        /**
         * How often the backstop sweep runs. It exists only to repair drift (a
         * job lost to a WorkManager reset, a bug, app data cleared) — the
         * standing constrained job is what makes uploads resume when the network
         * returns, so this does not need to be frequent. It does need to be
         * often enough that a repair isn't half a day away, which 750 minutes
         * was.
         */
        private const val BACKSTOP_PERIOD_MINUTES = 6L * 60
    }

    // Reconciliation touches prefs, Room and WorkManager, and its callers
    // include UI toggles — so it never runs on the caller's thread.
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    fun startManualUpload(photoId: String) {
        // in future, use PhotoUploadForeground here
    }

    /**
     * Every event that could change the queue or the settings calls this, and
     * nothing else: a capture, a drain ending, a settings change, app start,
     * login, a delete, the retry button. It reads the world, asks
     * [decideUploadSchedule] what the schedule should be, and makes WorkManager
     * match. See UploadScheduler.kt for why this is one funnel.
     *
     * Runs its own I/O off the caller's thread — callers include UI toggles,
     * and this touches SharedPreferences, Room and WorkManager.
     */
    fun reconcile(reason: String) {
        scope.launch {
            try {
                applyDecision(reason)
            } catch (e: Exception) {
                Log.e(TAG, "🢄📤 reconcile [$reason] failed", e)
                EventLog.record("upload", "schedule reconcile failed: ${e.message}")
            }
        }
    }

    /**
     * Kept as the trigger sites' name for [reconcile] — it reads as what the
     * caller wants ("something happened, please upload"), while the decision of
     * whether anything is enqueued lives in one place.
     */
    fun startAutomaticUpload(triggerSource: String = "automatic") = reconcile(triggerSource)

    private suspend fun applyDecision(reason: String) = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        val gate = UploadGate(
            autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false),
            hasLicense = prefs.getString("auto_upload_license", null) != null,
            wifiOnly = prefs.getBoolean("wifi_only", false),
        )
        val dao = PhotoDatabase.getDatabase(context).photoDao()
        val queue = UploadQueueSnapshot(
            waiting = dao.getPendingUploadCount() + dao.getFailedUploadCount(),
        )
        val workManager = WorkManager.getInstance(context)
        val existing = readScheduledWork(workManager)

        // The coalescing window only chooses expedited-vs-deferred; it never
        // decides whether a job exists (that is the queue's business), which is
        // what used to make a burst of captures silently skip scheduling.
        val now = SystemClock.elapsedRealtime()
        val bypass = reason == "retry_button"
        val leadingEdge = bypass || now - lastImmediateMs > WINDOW_MS

        val action = decideUploadSchedule(gate, queue, existing, leadingEdge, bypass)
        Log.d(TAG, "🢄📤 reconcile [$reason] -> $action (queue=${queue.waiting}, existing=$existing)")

        when (action) {
            is ScheduleAction.Leave -> Unit
            is ScheduleAction.CancelAll -> {
                if (existing.exists) {
                    EventLog.record("upload", "schedule cleared [$reason]: ${action.why}")
                    cancelQueuedUploads(workManager)
                }
                // The backstop goes with it: with the gate shut there is nothing
                // for a periodic sweep to do either.
                if (!gate.autoUploadEnabled || !gate.hasLicense) {
                    workManager.cancelUniqueWork(PhotoUploadWorker.WORK_NAME)
                }
            }
            is ScheduleAction.Ensure -> {
                if (action.replaceExisting) {
                    // A constraint is fixed at enqueue time, so a job whose rule
                    // no longer matches the settings can only be replaced, never
                    // updated — and under KEEP it would otherwise sit there
                    // swallowing every later enqueue under the same name.
                    Log.d(TAG, "🢄📤 replacing stale schedule: ${action.why}")
                    EventLog.record("upload", "rescheduling: ${action.why}")
                    cancelQueuedUploads(workManager)
                }
                if (action.expedited) lastImmediateMs = now
                if (action.expedited) {
                    enqueueUpload(reason, action.wifiOnly, WORK_NOW, delayMs = 0L, expedited = true)
                } else {
                    // Inside the window: fold into a single durable, deferred
                    // batch (expedited and an initial delay are mutually
                    // exclusive). KEEP means repeated captures don't reset the
                    // timer — it fires WINDOW_MS after the window opened, and
                    // its drain re-scans the DB for everything waiting.
                    enqueueUpload(reason, action.wifiOnly, WORK_BATCH, delayMs = WINDOW_MS, expedited = false)
                }
                // The standing job above answers "resume when conditions allow".
                // This is the backstop for the case where it is somehow lost —
                // scheduled here rather than only on a settings save, so that a
                // launch is enough to restore it.
                scheduleUploadWorker(workManager, true, action.wifiOnly)
            }
        }
    }

    /**
     * What WorkManager holds under our two unique names, as one answer.
     *
     * The constraint comes back from a TAG because WorkInfo does not expose a
     * job's input data or its constraints — and without knowing the constraint
     * a parked job was enqueued under, a settings change cannot tell a healthy
     * schedule from a stale one.
     */
    /**
     * The same reading the reconciler makes, for anyone who wants to compare
     * the schedule against what it SHOULD be (the Uploads screen does). One
     * reader, so a diagnosis can't disagree with the decision it is diagnosing.
     */
    fun scheduledWork(): ScheduledUploadWork = readScheduledWork(WorkManager.getInstance(context))

    private fun readScheduledWork(workManager: WorkManager): ScheduledUploadWork {
        var exists = false
        var running = false
        var wifiOnly: Boolean? = null
        for (name in listOf(WORK_NOW, WORK_BATCH)) {
            val infos = runCatching { workManager.getWorkInfosForUniqueWork(name).get() }
                .getOrNull() ?: continue
            for (info in infos) {
                if (info.state.isFinished) continue
                exists = true
                if (info.state == WorkInfo.State.RUNNING) running = true
                if (info.tags.contains(TAG_UNMETERED)) wifiOnly = true
                else if (info.tags.contains(TAG_ANY_NETWORK)) wifiOnly = false
            }
        }
        return ScheduledUploadWork(exists = exists, running = running, wifiOnly = wifiOnly)
    }

    /**
     * Enqueue one PhotoUploadWorker run as unique work (KEEP). `expedited` and
     * a non-zero `delayMs` are mutually exclusive in WorkManager, so the
     * immediate path is expedited with no delay and the batch path is deferred.
     * Foreground promotion is NOT decided here — the worker calls setForeground()
     * based on app-backgrounded state at run time.
     */
    private fun enqueueUpload(
        triggerSource: String,
        wifiOnly: Boolean,
        uniqueName: String,
        delayMs: Long,
        expedited: Boolean,
    ) {
        val networkType = if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(networkType)
            .build()

        val data = Data.Builder()
            .putString("trigger_source", triggerSource)
            .build()

        val builder = OneTimeWorkRequestBuilder<PhotoUploadWorker>()
            .setConstraints(constraints)
            .setInputData(data)
            // The constraint, written where WorkInfo can read it back — see
            // readScheduledWork.
            .addTag(if (wifiOnly) TAG_UNMETERED else TAG_ANY_NETWORK)
        if (expedited) {
            builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        } else {
            builder.setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
        }

        Log.d(TAG, "🢄📤 enqueue $uniqueName wifiOnly=$wifiOnly expedited=$expedited delayMs=$delayMs trigger=$triggerSource")
        EventLog.record(
            "upload",
            "enqueued $uniqueName (trigger $triggerSource, " +
                (if (wifiOnly) "needs unmetered" else "any network") +
                (if (expedited) ", expedited" else ", in ${delayMs / 1000}s") + ")",
        )
        WorkManager.getInstance(context).enqueueUniqueWork(uniqueName, ExistingWorkPolicy.KEEP, builder.build())
    }


    /**
     * Cancel every queued/running one-time upload drain. Called when
     * auto-upload is disabled: WORK_NOW / WORK_BATCH jobs — including the
     * WorkManager retry chains a busy or stuck worker leaves behind — are
     * persistent (they survive process death and reboots) and would
     * otherwise fire hours after the toggle went off, the moment their
     * backoff elapses or their network constraint is finally met.
     * A RUNNING drain is stopped via cancellation; the drain loop restores
     * the in-flight photo's status on that path.
     */
    fun cancelQueuedUploads(workManager: WorkManager) {
        Log.d(TAG, "🢄📤 cancelling $WORK_NOW + $WORK_BATCH")
        workManager.cancelUniqueWork(WORK_NOW)
        workManager.cancelUniqueWork(WORK_BATCH)
    }

    /**
     * One-shot follow-up that reconciles "processing" photos with the server
     * (PhotoStatusSyncWorker). Runs as its own job so the upload drain can
     * finish — and stop KEEP-blocking fresh capture triggers — without
     * waiting on the status round-trip. Short delay + REPLACE: back-to-back
     * drains coalesce into one sync, which re-queries the DB when it runs,
     * and the delay gives the server a moment to actually finish processing.
     */
    fun schedulePostUploadStatusSync() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = OneTimeWorkRequestBuilder<PhotoStatusSyncWorker>()
            .setConstraints(constraints)
            .setInitialDelay(5, TimeUnit.SECONDS)
            .build()
        Log.d(TAG, "🢄📤 enqueue ${PhotoStatusSyncWorker.WORK_NAME}")
        WorkManager.getInstance(context).enqueueUniqueWork(
            PhotoStatusSyncWorker.WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    /**
     * The backstop sweep. Owned by [reconcile] now, which is what answers the
     * old "todo: call this on initialization or something?" — it was previously
     * scheduled only when settings were saved, so an app whose periodic job was
     * ever lost had no way back to it short of the user re-saving settings.
     *
     * Do NOT lean on this for responsiveness: a periodic job runs at most once
     * per period, so on its own it is a sweep that happens to wait for the
     * network, not "uploads resume when Wi-Fi appears". That is the standing
     * constrained one-shot's job.
     */
    fun scheduleUploadWorker(workManager: WorkManager, enabled: Boolean, wifiOnly: Boolean = true) {
        Log.i(TAG, "📤 [scheduleUploadWorker] CALLED with enabled: $enabled, wifiOnly: $wifiOnly")

        try {
            val networkType = if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(networkType)
                .setRequiresBatteryNotLow(true)
                .build()

            Log.d(TAG, "📤 [scheduleUploadWorker] Constraints built - NetworkType=${if (wifiOnly) "UNMETERED" else "CONNECTED"}, RequiresBatteryNotLow=true")

            val uploadWorkRequest = PeriodicWorkRequestBuilder<PhotoUploadWorker>(
                BACKSTOP_PERIOD_MINUTES, TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setInputData(
                    Data.Builder()
                        .putBoolean(PhotoUploadWorker.KEY_AUTO_UPLOAD_ENABLED, enabled)
                        .putString("trigger_source", "scheduled")
                        .build()
                )
                .build()

            Log.d(TAG, "📤 [scheduleUploadWorker] Work request created, workId: ${uploadWorkRequest.id}")

            Log.i(TAG, "📤 [scheduleUploadWorker] Enqueueing unique periodic work with name: ${PhotoUploadWorker.WORK_NAME}")
            workManager.enqueueUniquePeriodicWork(
                PhotoUploadWorker.WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                uploadWorkRequest
            )

            Log.i(TAG, "📤 [scheduleUploadWorker] SUCCESS - periodic work enqueued with UPDATE policy")

        } catch (e: Exception) {
            Log.e(TAG, "📤 [scheduleUploadWorker] ERROR occurred while scheduling worker", e)
        }
    }

}
