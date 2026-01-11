package cz.hillview.plugin

import android.util.Log
import org.unifiedpush.android.connector.PushService
import org.unifiedpush.android.connector.FailedReason
import org.unifiedpush.android.connector.data.PushEndpoint
import org.unifiedpush.android.connector.data.PushMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * UnifiedPush Service Implementation
 * This replaces the previous HillviewUnifiedPushService with the newer API
 */
class PushServiceImpl : PushService() {

    companion object {
        private const val TAG = "🢄PushServiceImpl"
    }

    override fun onNewEndpoint(endpoint: PushEndpoint, instance: String) {
        Log.d(TAG, "🔗 onNewEndpoint called!")
        Log.d(TAG, "🔗   Endpoint URL: ${endpoint.url}")
        Log.d(TAG, "🔗   Instance: $instance")

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val manager = PushDistributorManager.getInstance(this@PushServiceImpl)
                manager.onNewEndpoint(endpoint.url)
                Log.d(TAG, "✅ Backend registration completed")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Backend registration failed", e)
            }
        }
    }

    override fun onRegistrationFailed(reason: FailedReason, instance: String) {
        Log.w(TAG, "❌ onRegistrationFailed called!")
        Log.w(TAG, "❌   Reason: $reason")
        Log.w(TAG, "❌   Instance: $instance")
    }

    override fun onUnregistered(instance: String) {
        Log.d(TAG, "🚫 onUnregistered called!")
        Log.d(TAG, "🚫   Instance: $instance")
    }

    override fun onMessage(message: PushMessage, instance: String) {
        Log.d(TAG, "📬 onMessage called - smart poke received")
        Log.d(TAG, "📬   Instance: $instance")

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val notificationManager = NotificationManager(this@PushServiceImpl)
                notificationManager.checkForNewNotifications()
                Log.d(TAG, "✅ Smart poke handled successfully")
            } catch (e: Exception) {
                // UnifiedPush doesn't include fallback content, just log the error
                Log.e(TAG, "❌ Failed to handle smart poke: ${e.message}")
            }
        }
    }




}
