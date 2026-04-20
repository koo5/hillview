package cz.hillview.plugin

import android.content.Context
import android.util.Log
import androidx.work.*
import java.util.concurrent.TimeUnit

class PhotoUploadManager(private val context: Context) {
    companion object {
        private const val TAG = "PhotoUploadManager"
    }

    fun startManualUpload(photoId: String) {
        // in future, use PhotoUploadForeground here
    }

    fun startAutomaticUpload(triggerSource: String = "automatic") {
        // Trigger the upload worker immediately
        val workManager = WorkManager.getInstance(context)
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)
        val wifiOnly = prefs.getBoolean("wifi_only", false)

        if (autoUploadEnabled) {
            // Manual retry button bypasses wifi-only constraint
            val effectiveWifiOnly = if (triggerSource == "retry_button") false else wifiOnly
            Log.d(TAG, "🢄📤 workManager.enqueue(workRequest) with wifiOnly=$effectiveWifiOnly, trigger=$triggerSource")
            val networkType = if (effectiveWifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(networkType)
                .build()

            // Expedited work is what makes WorkManager call
            // getForegroundInfo() on Android 12+, surfacing the ongoing
            // "Uploading Photos" notification. Without it the worker runs
            // silently as plain background work. The RUN_AS_NON_EXPEDITED
            // fallback keeps uploads going when the per-app expedited
            // quota (~10 min per rolling 10-min window for Active apps)
            // is exhausted — at the cost of the notification for that
            // specific invocation.
            val workRequest = OneTimeWorkRequestBuilder<PhotoUploadWorker>()
                .setConstraints(constraints)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .setInputData(
                    Data.Builder()
                        .putString("trigger_source", triggerSource)
                        .build()
                )
                .build()
            workManager.enqueue(workRequest)
        } else {
            Log.d(TAG, "🢄📤 auto_upload_enabled === false")
        }
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
