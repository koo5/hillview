package cz.hillview.plugin

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

class PhotoUploadForegroundService : Service() {
    companion object {
        private const val TAG = "PhotoUploadForeground"
        const val CHANNEL_ID = "photo_upload_foreground"
        const val NOTIFICATION_ID = 2001
        const val ACTION_START_UPLOAD = "START_UPLOAD"
        const val ACTION_STOP_UPLOAD = "STOP_UPLOAD"

        private var isUploading = false
    }

    private val binder = LocalBinder()

    inner class LocalBinder : Binder() {
        fun getService(): PhotoUploadForegroundService = this@PhotoUploadForegroundService
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

            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundUploadProcess(triggerSource: String = "unknown") {
        if (isUploading) {
            Log.d(TAG, "Upload already in progress")
            return
        }

        Log.d(TAG, "Starting foreground upload service (triggered by: $triggerSource)")
        isUploading = true

        val notification = createUploadNotification("Starting photo uploads...")
        startForeground(NOTIFICATION_ID, notification)

        // Store trigger source for later use in upload logic
        // TODO: Implement actual upload processing based on triggerSource
        // For "scheduled" triggers, should scan for new photos
        // For "manual" triggers, should process pending uploads only
    }

    private fun stopForegroundUploadProcess() {
        Log.d(TAG, "Stopping foreground upload service")
        isUploading = false
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    fun updateUploadProgress(message: String) {
        if (isUploading) {
            val notification = createUploadNotification(message)
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.notify(NOTIFICATION_ID, notification)
        }
    }

    private fun createUploadNotification(message: String): Notification {
        val intent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, PhotoUploadForegroundService::class.java).apply {
            action = ACTION_STOP_UPLOAD
        }
        val stopPendingIntent = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Uploading Photos")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentIntent(pendingIntent)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Stop",
                stopPendingIntent
            )
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
    }

    // Service lifecycle methods
    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "PhotoUploadForegroundService created")
        createNotificationChannel()
    }

    override fun onBind(intent: Intent?): IBinder {
        return binder
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_UPLOAD -> {
                val triggerSource = intent.getStringExtra("trigger_source") ?: "unknown"
                startForegroundUploadProcess(triggerSource)
            }
            ACTION_STOP_UPLOAD -> {
                stopForegroundUploadProcess()
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "PhotoUploadForegroundService destroyed")
        isUploading = false
    }
}