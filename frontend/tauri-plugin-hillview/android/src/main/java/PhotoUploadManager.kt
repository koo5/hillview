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

    fun startAutomaticUpload() {
        // Trigger the upload worker immediately
        val workManager = WorkManager.getInstance(context)
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)

        if (autoUploadEnabled) {
            Log.d(TAG, "🢄📤 workManager.enqueue(workRequest)")
            val workRequest = OneTimeWorkRequestBuilder<PhotoUploadWorker>()
                .setInputData(
                    Data.Builder()
                        .putString("trigger_source", "automatic")
                        .build()
                )
                .build()
            workManager.enqueue(workRequest)
        } else {
            Log.d(TAG, "🢄📤 auto_upload_enabled === false")
        }
    }


    // todo: call this on initialization or something?
    fun scheduleUploadWorker(workManager: WorkManager, enabled: Boolean) {
        Log.i(TAG, "📤 [scheduleUploadWorker] CALLED with enabled: $enabled")

        try {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .setRequiresBatteryNotLow(true)
                .build()

            Log.d(TAG, "📤 [scheduleUploadWorker] Constraints built - NetworkType.CONNECTED, RequiresBatteryNotLow=true")

            val uploadWorkRequest = PeriodicWorkRequestBuilder<PhotoUploadWorker>(
                150, TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setInputData(
                    Data.Builder()
                        .putBoolean(PhotoUploadWorker.KEY_AUTO_UPLOAD_ENABLED, enabled)
                        .putString("trigger_source", "scheduled")
                        .build()
                )
                .build()

            Log.d(TAG, "📤 [scheduleUploadWorker] Work request created - interval: 150 minutes, workId: ${uploadWorkRequest.id}")

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
