package cz.hillview.plugin

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.work.*
import java.util.concurrent.TimeUnit

class PhotoUploadManager(private val context: Context) {
    companion object {
        private const val TAG = "PhotoUploadManager"

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
    }

    fun startManualUpload(photoId: String) {
        // in future, use PhotoUploadForeground here
    }

    fun startAutomaticUpload(triggerSource: String = "automatic") {
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("auto_upload_enabled", false)) {
            Log.d(TAG, "🢄📤 auto_upload_enabled === false")
            return
        }
        // Manual retry button bypasses the wifi-only constraint.
        val wifiOnly = if (triggerSource == "retry_button") false else prefs.getBoolean("wifi_only", false)

        val now = SystemClock.elapsedRealtime()
        if (triggerSource == "retry_button" || now - lastImmediateMs > WINDOW_MS) {
            // Leading edge: first capture of a window (or an explicit manual
            // retry) uploads right away — expedited, no delay.
            lastImmediateMs = now
            enqueueUpload(triggerSource, wifiOnly, WORK_NOW, delayMs = 0L, expedited = true)
        } else {
            // Inside the window: fold into a single durable, deferred batch.
            // Not expedited (incompatible with an initial delay). KEEP means
            // repeated captures don't reset the timer — it fires WINDOW_MS after
            // the window opened, and its drain loop re-scans the DB for
            // everything pending. Whether it promotes to a foreground service is
            // decided in the worker by app-backgrounded state.
            enqueueUpload(triggerSource, wifiOnly, WORK_BATCH, delayMs = WINDOW_MS, expedited = false)
        }
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
        if (expedited) {
            builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        } else {
            builder.setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
        }

        Log.d(TAG, "🢄📤 enqueue $uniqueName wifiOnly=$wifiOnly expedited=$expedited delayMs=$delayMs trigger=$triggerSource")
        WorkManager.getInstance(context).enqueueUniqueWork(uniqueName, ExistingWorkPolicy.KEEP, builder.build())
    }


    // todo: call this on initialization or something?
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
                750, TimeUnit.MINUTES
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
