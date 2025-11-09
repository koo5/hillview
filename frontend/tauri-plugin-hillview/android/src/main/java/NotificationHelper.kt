package cz.hillview.plugin

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

/**
 * Helper class for managing push notifications related to authentication and uploads
 */
class NotificationHelper(private val context: Context) {

    companion object {
        private const val TAG = "🢄NotificationHelper"
        private const val CHANNEL_ID_AUTH = "auth_notifications"
        private const val CHANNEL_ID_UPLOAD = "upload_notifications"
        private const val NOTIFICATION_ID_AUTH_EXPIRED = 1001
        private const val NOTIFICATION_ID_UPLOAD_STATUS = 1002

        // Channel names and descriptions
        private const val AUTH_CHANNEL_NAME = "Authentication"
        private const val AUTH_CHANNEL_DESCRIPTION = "Notifications about login status and authentication issues"
        private const val UPLOAD_CHANNEL_NAME = "Photo Uploads"
        private const val UPLOAD_CHANNEL_DESCRIPTION = "Notifications about photo upload status and progress"
    }

    init {
        createNotificationChannels()
    }

    /**
     * Create notification channels for Android O+ (API 26+)
     */
    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            // Authentication channel
            val authChannel = NotificationChannel(
                CHANNEL_ID_AUTH,
                AUTH_CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = AUTH_CHANNEL_DESCRIPTION
                enableVibration(true)
                setShowBadge(true)
            }

            // Upload status channel
            val uploadChannel = NotificationChannel(
                CHANNEL_ID_UPLOAD,
                UPLOAD_CHANNEL_NAME,
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = UPLOAD_CHANNEL_DESCRIPTION
                enableVibration(false)
                setShowBadge(false)
            }

            notificationManager.createNotificationChannel(authChannel)
            notificationManager.createNotificationChannel(uploadChannel)

            Log.d(TAG, "Notification channels created")
        }
    }

    /**
     * Show notification when authentication expires and user needs to re-login
     */
    fun showAuthExpiredNotification() {
        try {
            Log.d(TAG, "Showing auth expired notification")

            // Create intent to open the app (main activity)
            val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
            val pendingIntent = PendingIntent.getActivity(
                context,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(context, CHANNEL_ID_AUTH)
                .setSmallIcon(android.R.drawable.ic_dialog_alert) // Use system icon, app can override
                .setContentTitle("Login Required")
                .setContentText("Your session has expired. Please open Hillview to continue photo uploads.")
                .setStyle(
                    NotificationCompat.BigTextStyle()
                        .bigText("Your authentication session has expired and automatic photo uploads have been paused. Please open the Hillview app and log in again to resume background uploads.")
                )
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setContentIntent(pendingIntent)
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_REMINDER)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .build()

            if (areNotificationsAllowed()) {
                NotificationManagerCompat.from(context)
                    .notify(NOTIFICATION_ID_AUTH_EXPIRED, notification)
                Log.d(TAG, "Auth expired notification sent successfully")
            } else {
                Log.w(TAG, "Notifications are not allowed (system or user preference)")
            }

        } catch (e: SecurityException) {
            Log.e(TAG, "Missing notification permission", e)
        } catch (e: Exception) {
            Log.e(TAG, "Error showing auth expired notification", e)
        }
    }

    /**
     * Show notification about upload status (optional - for future use)
     */
    fun showUploadStatusNotification(uploaded: Int, failed: Int, pending: Int) {
        try {
            if (uploaded == 0 && failed == 0) return // Nothing to report

            val title = when {
                failed > 0 -> "Upload Issues"
                uploaded > 0 -> "Photos Uploaded"
                else -> "Upload Status"
            }

            val message = buildString {
                if (uploaded > 0) append("$uploaded uploaded")
                if (failed > 0) {
                    if (uploaded > 0) append(", ")
                    append("$failed failed")
                }
                if (pending > 0) {
                    if (uploaded > 0 || failed > 0) append(", ")
                    append("$pending pending")
                }
            }

            val notification = NotificationCompat.Builder(context, CHANNEL_ID_UPLOAD)
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setContentTitle(title)
                .setContentText(message)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_STATUS)
                .build()

            if (areNotificationsAllowed()) {
                NotificationManagerCompat.from(context)
                    .notify(NOTIFICATION_ID_UPLOAD_STATUS, notification)
                Log.d(TAG, "Upload status notification sent: $message")
            } else {
                Log.d(TAG, "Upload status notification skipped (user preference)")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error showing upload status notification", e)
        }
    }

    /**
     * Clear the auth expired notification (call this when user successfully logs in)
     */
    fun clearAuthExpiredNotification() {
        try {
            NotificationManagerCompat.from(context)
                .cancel(NOTIFICATION_ID_AUTH_EXPIRED)
            Log.d(TAG, "Auth expired notification cleared")
        } catch (e: Exception) {
            Log.e(TAG, "Error clearing auth expired notification", e)
        }
    }

    /**
     * Check if notifications are enabled for this app
     */
    fun areNotificationsEnabled(): Boolean {
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    /**
     * Check if notifications are enabled both at system level and user preference level
     */
    fun areNotificationsAllowed(): Boolean {
        // Check system-level permission
        if (!areNotificationsEnabled()) {
            Log.d(TAG, "System notifications are disabled")
            return false
        }

        // Check user preference from SharedPreferences
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        val userEnabled = prefs.getBoolean("notifications_enabled", true)

        if (!userEnabled) {
            Log.d(TAG, "User has disabled notifications in app settings")
            return false
        }

        return true
    }

    /**
     * Show a general notification with title and message
     */
    fun showNotification(
        notificationId: Int,
        title: String,
        message: String,
        channelId: String = CHANNEL_ID_AUTH,
        priority: Int = NotificationCompat.PRIORITY_DEFAULT,
        autoCancel: Boolean = true
    ) {
        try {
            if (!areNotificationsAllowed()) {
                Log.d(TAG, "Notifications not allowed, skipping: $title")
                return
            }

            Log.d(TAG, "Showing notification: $title")

            // Create intent to open the app
            val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)
            val pendingIntent = PendingIntent.getActivity(
                context,
                notificationId,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            val notification = NotificationCompat.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(message)
                .setStyle(NotificationCompat.BigTextStyle().bigText(message))
                .setPriority(priority)
                .setContentIntent(pendingIntent)
                .setAutoCancel(autoCancel)
                .setCategory(NotificationCompat.CATEGORY_MESSAGE)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .build()

            NotificationManagerCompat.from(context).notify(notificationId, notification)
            Log.d(TAG, "Notification sent successfully: $title")

        } catch (e: SecurityException) {
            Log.e(TAG, "Missing notification permission", e)
        } catch (e: Exception) {
            Log.e(TAG, "Error showing notification: $title", e)
        }
    }
}
