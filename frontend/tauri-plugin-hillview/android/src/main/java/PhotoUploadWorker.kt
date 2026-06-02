package cz.hillview.plugin

import android.app.*
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
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

    // Set once this run actually promotes to a foreground service. Progress
    // updates via notify() only show (and only make sense) when that FGS
    // notification exists — i.e. when the app was backgrounded.
    @Volatile private var promoted = false

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        workerMutex.withLock {
            val triggerSource = inputData.getString("trigger_source") ?: "unknown"
            Log.d(TAG, "Starting upload work with trigger: $triggerSource")

            // Promote to a foreground service ONLY when the app is in the
            // BACKGROUND. The promotion runs SystemForegroundService.onStartCommand
            // on the MAIN thread, so doing it during active (foreground) capture
            // is what churned the main thread, flashed the notification on every
            // shot, and previously crashed via ForegroundServiceDidNotStartInTime.
            // A foreground app is already high-priority and doesn't need the FGS;
            // a backgrounded drain does — both for survival and to surface progress.
            //
            // Decided here at run time (not by the enqueuer) because the deferred
            // batch fires ~15s later and the app may have been left by then.
            // Residual: if the app is foreground at start and backgrounded
            // mid-drain, this run has no FGS protection — the batch/periodic
            // backstops cover that. (Long term PhotoUploadForegroundService,
            // currently dormant, is the better fit for long continuous uploads.)
            val backgrounded = try {
                !ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
            } catch (e: Exception) {
                true // ProcessLifecycleOwner not initialized → assume background & promote
            }
            Log.d(TAG, "promote decision: backgrounded=$backgrounded (trigger=$triggerSource)")
            if (backgrounded) {
                try {
                    setForeground(getForegroundInfo())
                    promoted = true
                    Log.d(TAG, "promoted to foreground (notif $NOTIFICATION_ID)")
                } catch (e: Exception) {
                    Log.w(TAG, "Could not set foreground: ${e.message}")
                    // Continue anyway - work can still run without foreground
                }
            }

            // Delegate to upload logic, surfacing per-photo progress on the
            // foreground notification when we have one.
            PhotoUploadLogic(applicationContext).doWorkInternal(triggerSource, null, ::updateUploadNotification)
        }
    }

    override suspend fun getForegroundInfo(): ForegroundInfo {
        return createForegroundInfo("Preparing to upload photos...")
    }

    private fun createForegroundInfo(message: String): ForegroundInfo {
        // Android 14+ also needs FOREGROUND_SERVICE_DATA_SYNC in the
        // manifest — WorkManager 2.8.1 doesn't bundle it, 2.9+ does. Add
        // the permission (or bump WorkManager) before this path is usable
        // on physical devices.
        return ForegroundInfo(
            NOTIFICATION_ID,
            buildNotification(message),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
        )
    }

    private fun buildNotification(message: String): Notification {
        createNotificationChannel()

        val intent = applicationContext.packageManager.getLaunchIntentForPackage(applicationContext.packageName)
        val pendingIntent = PendingIntent.getActivity(
            applicationContext,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setContentTitle("Uploading Photos")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
    }

    /**
     * Refresh the ongoing upload notification's text. No-op unless this run
     * promoted to a foreground service (a foreground run has no notification to
     * update). Updating via notify() with the same id/channel is cheap and
     * off the main thread — no setForeground re-promotion, no FGS churn.
     */
    private fun updateUploadNotification(message: String) {
        if (!promoted) return
        try {
            NotificationManagerCompat.from(applicationContext).notify(NOTIFICATION_ID, buildNotification(message))
        } catch (e: Exception) {
            Log.w(TAG, "Could not update upload notification: ${e.message}")
        }
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
