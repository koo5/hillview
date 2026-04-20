package cz.hillview.plugin

import android.app.*
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File
import java.io.IOException
import java.security.MessageDigest

class PhotoUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "🢄PhotoUploadWorker"
        const val WORK_NAME = "photo_upload_work"
        const val KEY_AUTO_UPLOAD_ENABLED = "auto_upload_enabled"

        // Notification constants
        private const val NOTIFICATION_ID = 2001
        private const val CHANNEL_ID = "photo_upload_foreground"

        // Shared mutex to prevent multiple workers from running simultaneously
        private val workerMutex = Mutex()
    }

    private val notificationHelper by lazy { NotificationHelper(applicationContext) }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        workerMutex.withLock {
            val triggerSource = inputData.getString("trigger_source") ?: "unknown"
            Log.d(TAG, "Starting upload work with trigger: $triggerSource")

            // Promote to foreground so the user sees the "Uploading Photos"
            // notification while the queue drains. The earlier Android-12
            // branch here relied on "expedited work provides foreground
            // automatically", but that's only true when the WorkRequest is
            // built with .setExpedited() — and it wasn't. PhotoUploadManager
            // now sets expedited explicitly; we still call setForeground()
            // unconditionally so pre-12 devices get the same treatment.
            //
            // Long term PhotoUploadForegroundService (currently dormant) is
            // the better fit for long / continuous uploads: no quota cap,
            // survives more memory pressure. The WorkManager path here is
            // bounded by the expedited quota — over-quota runs fall back to
            // RUN_AS_NON_EXPEDITED_WORK_REQUEST and lose the notification
            // for that invocation.
            try {
                setForeground(getForegroundInfo())
            } catch (e: Exception) {
                Log.w(TAG, "Could not set foreground: ${e.message}")
                // Continue anyway - work can still run without foreground
            }

            // Delegate to upload logic
            PhotoUploadLogic(applicationContext).doWorkInternal(triggerSource, null)
        }
    }

    override suspend fun getForegroundInfo(): ForegroundInfo {
        return createForegroundInfo("Preparing to upload photos...")
    }

    private fun createForegroundInfo(message: String): ForegroundInfo {
        createNotificationChannel()

        val intent = applicationContext.packageManager.getLaunchIntentForPackage(applicationContext.packageName)
        val pendingIntent = PendingIntent.getActivity(
            applicationContext,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setContentTitle("Uploading Photos")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()

        // Android 14+ also needs FOREGROUND_SERVICE_DATA_SYNC in the
        // manifest — WorkManager 2.8.1 doesn't bundle it, 2.9+ does. Add
        // the permission (or bump WorkManager) before this path is usable
        // on physical devices.
        return ForegroundInfo(
            NOTIFICATION_ID,
            notification,
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
        )
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Photo Upload Service",
                android.app.NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Shows upload progress for photos"
                setShowBadge(false)
                enableVibration(false)
                setSound(null, null)
            }

            val notificationManager = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

}
