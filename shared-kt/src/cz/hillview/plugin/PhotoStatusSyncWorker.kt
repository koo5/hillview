package cz.hillview.plugin

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Reconciles local photos stuck in "processing" with the server
 * (POST /photos/status). Split out of the upload drain so PhotoUploadWorker
 * finishes the moment the last photo is handed off — while this round-trip
 * ran inline at the end of the drain, the job lingered in RUNNING and
 * ExistingWorkPolicy.KEEP silently dropped capture triggers arriving in that
 * window, leaving the session's last photo stuck in "pending".
 * Enqueued by PhotoUploadManager.schedulePostUploadStatusSync().
 */
class PhotoStatusSyncWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "hv-StatusSync"
        const val WORK_NAME = "photo_status_sync"
    }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            PhotoUploadLogic(applicationContext).syncProcessingPhotosStatus()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Best-effort: the next drain enqueues a fresh sync anyway.
            Log.w(TAG, "Status sync failed: ${e.message}")
        }
        Result.success()
    }
}
