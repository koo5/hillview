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
 * UnifiedPush Service - minimal bridge to existing managers
 */
class HillviewUnifiedPushService : PushService() {

    companion object {
        private const val TAG = "🢄UnifiedPushService"
    }

    override fun onNewEndpoint(endpoint: PushEndpoint, instance: String) {
        Log.d(TAG, "New endpoint: ${endpoint.url}")
        CoroutineScope(Dispatchers.IO).launch {
            PushDistributorManager(this@HillviewUnifiedPushService).registerWithBackend(endpoint.url)
        }
    }

    override fun onRegistrationFailed(reason: FailedReason, instance: String) {
        Log.w(TAG, "Registration failed: $reason")
    }

    override fun onUnregistered(instance: String) {
        Log.d(TAG, "Unregistered")
    }

    override fun onMessage(message: PushMessage, instance: String) {
        Log.d(TAG, "Smart poke received")
        NotificationManager(this@HillviewUnifiedPushService).checkForNewNotifications()
    }
}