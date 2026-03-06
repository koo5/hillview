package cz.hillview.plugin

import android.content.Context
import android.util.Log
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.gms.tasks.OnCompleteListener
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * FCM Direct Service for Firebase Cloud Messaging integration
 *
 * This provides direct FCM support as an alternative to UnifiedPush distributors.
 * Uses the same "smart poke" pattern - FCM just triggers a fetch from our backend.
 */
class FcmDirectService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "FcmDirectService"

        /**
         * Check if FCM is available and working (will initialize Firebase if needed)
         */
        fun isAvailable(context: Context): Boolean {
            try {
                // Check Google Play Services availability first
                val googleApiAvailability = GoogleApiAvailability.getInstance()
                val resultCode = googleApiAvailability.isGooglePlayServicesAvailable(context)
                val hasGooglePlay = resultCode == ConnectionResult.SUCCESS

                if (!hasGooglePlay) {
                    Log.d(TAG, "📱 FCM not available: Google Play Services missing (code: $resultCode)")
                    return false
                }

                // Test if Firebase is actually working
                try {
                    FirebaseMessaging.getInstance()
                    Log.d(TAG, "📱 FCM available: Firebase initialized successfully")
                    return true
                } catch (e: IllegalStateException) {
                    Log.w(TAG, "📱 FCM not available: Firebase not configured - ${e.message}")
                    return false
                } catch (e: Exception) {
                    Log.w(TAG, "📱 FCM not available: Firebase error - ${e.message}")
                    return false
                }

            } catch (e: Exception) {
                Log.w(TAG, "📱 FCM availability check failed: ${e.message}")
                return false
            }
        }

        /**
         * Get FCM registration token with timeout
         */
        suspend fun getRegistrationToken(): String = suspendCancellableCoroutine { continuation ->
            // Add timeout to prevent hanging forever
            val timeoutHandler = android.os.Handler(android.os.Looper.getMainLooper())
            val timeoutRunnable = Runnable {
                if (continuation.isActive) {
                    Log.w(TAG, "⚠️  FCM token retrieval timed out after 10 seconds")
                    continuation.resumeWithException(Exception("FCM token retrieval timeout"))
                }
            }
            timeoutHandler.postDelayed(timeoutRunnable, 10000) // 10 second timeout

            try {
                FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                    // Cancel timeout since we got a response
                    timeoutHandler.removeCallbacks(timeoutRunnable)

                    if (!continuation.isActive) return@addOnCompleteListener // Already timed out

                    if (!task.isSuccessful) {
                        Log.w(TAG, "⚠️  FCM token retrieval failed", task.exception)
                        continuation.resumeWithException(
                            task.exception ?: Exception("Failed to get FCM token")
                        )
                        return@addOnCompleteListener
                    }

                    val token = task.result
                    Log.d(TAG, "🔑 FCM token retrieved: ${token.take(20)}...")
                    continuation.resume(token)
                }
            } catch (e: IllegalStateException) {
                timeoutHandler.removeCallbacks(timeoutRunnable)
                Log.w(TAG, "⚠️  FCM token retrieval failed: Firebase not initialized - ${e.message}")
                continuation.resumeWithException(e)
            } catch (e: Exception) {
                timeoutHandler.removeCallbacks(timeoutRunnable)
                Log.w(TAG, "⚠️  FCM token retrieval failed: ${e.message}")
                continuation.resumeWithException(e)
            }
        }

        /**
         * Subscribe to a topic (optional - for broadcast notifications)
         */
        fun subscribeToTopic(topic: String) {
            FirebaseMessaging.getInstance().subscribeToTopic(topic)
                .addOnCompleteListener { task ->
                    if (task.isSuccessful) {
                        Log.d(TAG, "📢 Subscribed to topic: $topic")
                    } else {
                        Log.w(TAG, "⚠️  Failed to subscribe to topic: $topic", task.exception)
                    }
                }
        }

        /**
         * Unsubscribe from a topic
         */
        fun unsubscribeFromTopic(topic: String) {
            FirebaseMessaging.getInstance().unsubscribeFromTopic(topic)
                .addOnCompleteListener { task ->
                    if (task.isSuccessful) {
                        Log.d(TAG, "🔕 Unsubscribed from topic: $topic")
                    } else {
                        Log.w(TAG, "⚠️  Failed to unsubscribe from topic: $topic", task.exception)
                    }
                }
        }
    }

    /**
     * Called when FCM registration token is updated
     */
    override fun onNewToken(token: String) {
        Log.d(TAG, "🔄 FCM token refreshed: ${token.take(20)}...")

        // Notify the PushDistributorManager about the new token
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val context = applicationContext
                val manager = PushDistributorManager.getInstance(context)
                manager.onFcmTokenRefresh(token)
            } catch (e: Exception) {
                Log.e(TAG, "❌ Failed to handle FCM token refresh", e)
            }
        }
    }

    /**
     * Called when a message is received
     *
     * This implements the "smart poke" pattern:
     * 1. FCM message contains minimal data (just a notification ID or trigger)
     * 2. App fetches actual notification content from backend API
     * 3. App displays rich notification with fetched content
     */
    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        Log.d(TAG, "📨 FCM message received from: ${remoteMessage.from}")

        // Log the message data for debugging
        remoteMessage.data.let { data ->
            Log.d(TAG, "📋 Message data: $data")
        }

        // Handle notification in background thread
        CoroutineScope(Dispatchers.IO).launch {
            val context = applicationContext
            val notificationManager = NotificationManager(context)

            // Extract FCM content for fallback
            val fcmTitle = remoteMessage.notification?.title
            val fcmBody = remoteMessage.notification?.body
            val fcmRoute = remoteMessage.data["click_action"]

            try {
                // Try to fetch and display notifications from backend API
                Log.d(TAG, "🔔 Fetching notifications from backend...")
                notificationManager.checkForNewNotifications()
                Log.d(TAG, "✅ Backend notifications displayed")
            } catch (e: Exception) {
                // Fallback: display FCM content directly
                Log.w(TAG, "⚠️ Backend fetch failed: ${e.message}, using FCM fallback")
                if (fcmTitle != null && fcmBody != null) {
                    notificationManager.displaySingleNotification(fcmTitle, fcmBody, fcmRoute)
                } else {
                    Log.e(TAG, "❌ No fallback content available")
                }
            }
        }
    }

    /**
     * Called when message delivery status is updated
     */
    override fun onMessageSent(msgId: String) {
        Log.d(TAG, "📤 FCM message sent: $msgId")
    }

    /**
     * Called when sending a message fails
     */
    override fun onSendError(msgId: String, exception: Exception) {
        Log.e(TAG, "❌ FCM message send failed: $msgId", exception)
    }
}
