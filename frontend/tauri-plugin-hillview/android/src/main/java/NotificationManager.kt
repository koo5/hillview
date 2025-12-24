package cz.hillview.plugin

import android.app.NotificationChannel
import android.app.NotificationManager as AndroidNotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

/**
 * Notification Manager for Hillview
 *
 * Handles fetching notifications from backend and displaying
 * them as Android system notifications.
 */
class NotificationManager(private val context: Context) {

    companion object {
        private const val TAG = "🢄NotificationManager"
        private const val CHANNEL_ID = "hillview_notifications"
        private const val CHANNEL_NAME = "Hillview Notifications"
    }

    private val authManager = AuthenticationManager(context)

    init {
        createNotificationChannel()
    }

    /**
     * Check for new notifications and display them
     * Handles its own threading - safe to call from any thread
     */
    fun checkForNewNotifications() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val serverUrl = getServerUrl() ?: run {
                    Log.e(TAG, "No server URL configured")
                    return@launch
                }

                val notifications = fetchNotifications(serverUrl)
                if (notifications.isNotEmpty()) {
                    displayNotifications(notifications)
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error checking notifications", e)
            }
        }
    }

    private suspend fun fetchNotifications(serverUrl: String): List<HillviewNotification> {
        return withContext(Dispatchers.IO) {
            try {
                val url = "$serverUrl/notifications/recent?limit=5"
                val client = OkHttpClient()

                // Try to get a valid auth token first
                val token = authManager.getValidToken()
                val requestBuilder = Request.Builder().url(url)

                if (token != null) {
                    // Use token-based authentication if available
                    requestBuilder.header("Authorization", "Bearer $token")
                    Log.d(TAG, "Using token-based authentication for notifications")
                } else {
                    // Fall back to client key signature authentication
                    Log.d(TAG, "No token available, using client key authentication for notifications")
                    // For anonymous notification fetching, we can make the request without auth
                    // The backend should handle both authenticated and anonymous requests
                }

                val request = requestBuilder.build()

                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    val body = response.body?.string()
                    if (body != null) {
                        parseNotifications(body)
                    } else {
                        emptyList()
                    }
                } else {
                    Log.e(TAG, "Failed to fetch notifications: ${response.code}")
                    emptyList()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Exception fetching notifications", e)
                emptyList()
            }
        }
    }

    private fun parseNotifications(json: String): List<HillviewNotification> {
        return try {
            val jsonObj = JSONObject(json)
            val notificationsArray = jsonObj.getJSONArray("notifications")
            val result = mutableListOf<HillviewNotification>()

            for (i in 0 until notificationsArray.length()) {
                val notifObj = notificationsArray.getJSONObject(i)

                // Only show unread notifications (API uses snake_case)
                if (notifObj.isNull("read_at")) {
                    // action_data contains the route (e.g. "/activity")
                    val route = if (notifObj.isNull("action_data")) null else notifObj.getString("action_data")

                    result.add(HillviewNotification(
                        id = notifObj.getInt("id"),
                        title = notifObj.getString("title"),
                        body = notifObj.getString("body"),
                        type = notifObj.getString("type"),
                        route = route
                    ))
                }
            }

            result
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing notifications", e)
            emptyList()
        }
    }

    private fun displayNotifications(notifications: List<HillviewNotification>) {
        val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as AndroidNotificationManager

        notifications.forEach { notification ->
            val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                // Add route as click_action extra for frontend navigation
                if (notification.route != null) {
                    putExtra("click_action", notification.route)
                }
            }

            val pendingIntent = PendingIntent.getActivity(
                context,
                notification.id,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE  // MUTABLE needed to update extras
            )

            val builder = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info) // TODO: Use app icon
                .setContentTitle(notification.title)
                .setContentText(notification.body)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setContentIntent(pendingIntent)
                .setAutoCancel(true)

            notificationManager.notify(notification.id, builder.build())
            Log.d(TAG, "Displayed notification: ${notification.title} with route: ${notification.route}")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                AndroidNotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Notifications from Hillview app"
            }

            val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as AndroidNotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun getServerUrl(): String? {
        val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        return prefs.getString("server_url", null)
    }

    data class HillviewNotification(
        val id: Int,
        val title: String,
        val body: String,
        val type: String,
        val route: String?  // action_data from backend, e.g. "/activity"
    )
}
