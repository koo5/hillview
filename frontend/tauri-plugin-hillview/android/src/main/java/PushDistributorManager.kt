package cz.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.unifiedpush.android.connector.UnifiedPush

/**
 * Android Push Message Distributor Manager
 *
 * ARCHITECTURE:
 * =============
 *
 * This manager implements the "smart poke" push notification pattern:
 * 1. Client registers with chosen distributor (FCM, ntfy.sh, etc.)
 * 2. Distributor provides unique endpoint URL
 * 3. Client sends endpoint + client_key_id to backend
 * 4. Backend sends "smart poke" to endpoint when notifications exist
 * 5. Client fetches actual notification content via API
 *
 * BENEFITS:
 * =========
 *
 * ✅ Privacy: No sensitive content sent to push distributors
 * ✅ Flexibility: Rich content fetched dynamically from backend
 * ✅ Multi-device: Each device has unique endpoint
 * ✅ Reliability: Falls back gracefully when distributors unavailable
 *
 * INTEGRATION WITH EXISTING SYSTEM:
 * =================================
 *
 * - Uses ClientCryptoManager for stable client_key_id across installs
 * - Integrates with AuthenticationManager for backend API calls
 * - Stores settings in SharedPreferences for persistence
 * - Provides status detection for missing/invalid distributors
 */
class PushDistributorManager(private val context: Context) {

    companion object {
        private const val TAG = "🢄PushDistributorManager"
        private const val PREFS_NAME = "hillview_push_prefs"
        private const val KEY_SELECTED_DISTRIBUTOR = "selected_distributor"
        private const val KEY_PUSH_ENDPOINT = "push_endpoint"
        private const val KEY_REGISTRATION_STATUS = "registration_status"
        private const val KEY_LAST_ERROR = "last_error"
        private const val KEY_ENABLED = "push_enabled"

        @Volatile
        private var INSTANCE: PushDistributorManager? = null

        /**
         * Get singleton instance of PushDistributorManager
         */
        fun getInstance(context: Context): PushDistributorManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: PushDistributorManager(context.applicationContext).also { INSTANCE = it }
            }
        }
    }

    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val clientCrypto = ClientCryptoManager(context)
    private val authManager = AuthenticationManager(context)
    private val registrationMutex = Mutex()
    private val registrationMutex2 = Mutex()

    /**
     * Registration status enum for UI display
     */
    enum class RegistrationStatus {
        NOT_CONFIGURED,     // No distributor selected
        REGISTERED,         // Successfully registered with backend
        DISTRIBUTOR_MISSING, // Selected distributor app no longer available
        REGISTRATION_FAILED, // Backend registration failed
        DISABLED           // Push notifications disabled by user
    }

    /**
     * Distributor info for UI display
     */
    data class DistributorInfo(
        val packageName: String,
        val displayName: String,
        val isAvailable: Boolean
    )

    /**
     * Debug UnifiedPush registration - provides comprehensive diagnostics
     */
    fun debugUnifiedPush(): String {
        val sb = StringBuilder()
        sb.appendLine("🔍 UnifiedPush Debug Information:")

        try {
            val distributors = UnifiedPush.getDistributors(context)
            sb.appendLine("📨 Available distributors: $distributors (${distributors.size} items)")

            distributors.forEach { packageName ->
                val isAvailable = isDistributorAvailable(packageName)
                val displayName = getDistributorDisplayName(packageName)
                sb.appendLine("   - $displayName ($packageName): available=$isAvailable")
            }

            val selectedDistributor = getSelectedDistributor()
            sb.appendLine("📨 Selected distributor: $selectedDistributor")

            val endpoint = getPushEndpoint()
            sb.appendLine("🔗 Current endpoint: ${endpoint?.take(50) ?: "none"}")

            val status = getRegistrationStatus()
            sb.appendLine("📊 Registration status: $status")

            val lastError = getLastError()
            sb.appendLine("❌ Last error: ${lastError ?: "none"}")

        } catch (e: Exception) {
            sb.appendLine("❌ Exception during debug: ${e.message}")
        }

        return sb.toString()
    }

    /**
     * Get all available UnifiedPush distributors with status information
     */
    fun getAvailableDistributors(): List<DistributorInfo> {
        Log.d(TAG, "📨 getAvailableDistributors() called")
        val distributors = UnifiedPush.getDistributors(context)
        Log.d(TAG, "📨 UnifiedPush.getDistributors() returned: $distributors (${distributors.size} items)")
        val selectedDistributor = getSelectedDistributor()
        Log.d(TAG, "📨 Currently selected distributor: $selectedDistributor")

        val distributorInfoList = distributors.map { packageName ->
            DistributorInfo(
                packageName = packageName,
                displayName = getDistributorDisplayName(packageName),
                isAvailable = isDistributorAvailable(packageName)
            )
        }.toMutableList()

        // Add direct FCM as a distributor option if available
        val fcmPackageName = "com.google.firebase.messaging.direct"
        val isFcmAvailable = FcmDirectService.isAvailable(context)

        Log.d(TAG, "📨 FCM direct availability: $isFcmAvailable")

        distributorInfoList.add(0, DistributorInfo(  // Add at the beginning for priority
            packageName = fcmPackageName,
            displayName = "Google Firebase",
            isAvailable = isFcmAvailable
        ))

        // If we have a selected distributor that's not in the current list,
        // add it as unavailable (like DAVx5 does)
        selectedDistributor?.let { selected ->
            if (distributorInfoList.none { it.packageName == selected }) {
                distributorInfoList.add(
                    DistributorInfo(
                        packageName = selected,
                        displayName = getDistributorDisplayName(selected),
                        isAvailable = false
                    )
                )
            }
        }

        Log.d(TAG, "📨 Final distributor list size: ${distributorInfoList.size}")
        distributorInfoList.forEach { dist ->
            Log.d(TAG, "📨   - ${dist.displayName} (${dist.packageName}): available=${dist.isAvailable}")
        }

        return distributorInfoList
    }

    /**
     * Get current registration status for UI display
     */
    fun getRegistrationStatus(): RegistrationStatus {
        if (!isPushEnabled()) {
            return RegistrationStatus.DISABLED
        }

        val selectedDistributor = getSelectedDistributor()
        if (selectedDistributor == null) {
            return RegistrationStatus.NOT_CONFIGURED
        }

        if (!isDistributorAvailable(selectedDistributor)) {
            return RegistrationStatus.DISTRIBUTOR_MISSING
        }

        val status = prefs.getString(KEY_REGISTRATION_STATUS, null)
        return when (status) {
            "registered" -> RegistrationStatus.REGISTERED
            "failed" -> RegistrationStatus.REGISTRATION_FAILED
            else -> RegistrationStatus.NOT_CONFIGURED
        }
    }

    /**
     * Get user-friendly status message for UI
     */
    fun getStatusMessage(): String {
        return when (getRegistrationStatus()) {
            RegistrationStatus.NOT_CONFIGURED -> "Push notifications not configured"
            RegistrationStatus.REGISTERED -> "Push notifications active"
            RegistrationStatus.DISTRIBUTOR_MISSING -> {
                val distributorName = getSelectedDistributor()?.let { getDistributorDisplayName(it) } ?: "Unknown"
                "Distributor '$distributorName' no longer available"
            }
            RegistrationStatus.REGISTRATION_FAILED -> {
                val error = getLastError()
                "Registration failed${if (error != null) ": $error" else ""}"
            }
            RegistrationStatus.DISABLED -> "Push notifications disabled"
        }
    }

    /**
     * Auto-register with distributor if needed (no selection or failed registration)
     * Synchronized wrapper to prevent race conditions.
     */
    suspend fun autoRegisterIfNeeded() {
        // Check if server URL is configured first
        val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
        val serverUrl = uploadPrefs.getString("server_url", null)
        if (serverUrl == null) {
            Log.d(TAG, "Server URL not configured - skipping push notification auto-registration")
            return
        }

        registrationMutex.withLock {
            autoRegisterIfNeededInternal()
        }
    }

    /**
     * Internal auto-register logic (assumes caller holds registrationMutex)
     */
    private suspend fun autoRegisterIfNeededInternal() {
        val selectedDistributor = getSelectedDistributor()
        val registrationStatus = getRegistrationStatus()

        // Already registered successfully - nothing to do
        if (selectedDistributor != null && registrationStatus == RegistrationStatus.REGISTERED) {
            Log.d(TAG, "Push notifications already registered with $selectedDistributor")
            return
        }

        // Has distributor but registration failed - retry with same distributor
        if (selectedDistributor != null && registrationStatus == RegistrationStatus.REGISTRATION_FAILED) {
            Log.d(TAG, "Retrying failed registration with existing distributor: $selectedDistributor")
            selectDistributor(selectedDistributor)
            return
        }

        // Distributor missing - clear selection and auto-select new one
        if (selectedDistributor != null && registrationStatus == RegistrationStatus.DISTRIBUTOR_MISSING) {
            Log.d(TAG, "Selected distributor '$selectedDistributor' no longer available, clearing selection")
            unregister()
            // Fall through to auto-select new distributor
        }

        // No distributor selected - auto-select first available
        if (getSelectedDistributor() == null) {
            val availableDistributors = getAvailableDistributors().filter { it.isAvailable }
            if (availableDistributors.isEmpty()) {
                Log.d(TAG, "No available distributors for auto-registration")
                return
            }

            val firstDistributor = availableDistributors[0]
            Log.d(TAG, "Auto-registering with first available distributor: ${firstDistributor.packageName}")
            selectDistributor(firstDistributor.packageName)
        }
    }

    /**
     * Select a distributor and register with backend
     */
    suspend fun selectDistributor(packageName: String): Boolean {
		Log.d(TAG, "registrationMutex2.withLock..");
		val holder = registrationMutex2
        return registrationMutex2.withLock {
			Log.d(TAG, "registrationMutex2.withLock.");
            Log.d(TAG, "Selecting distributor: $packageName")

            // Check if this is direct FCM or UnifiedPush distributor
            val isFcmDirect = packageName == "com.google.firebase.messaging.direct"

            if (!isFcmDirect && !isDistributorAvailable(packageName)) {
                val error = "Selected distributor is not available"
                Log.e(TAG, error)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withLock false
            }

            if (isFcmDirect && !FcmDirectService.isAvailable(context)) {
                val error = "Direct FCM is not available on this device"
                Log.e(TAG, error)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withLock false
            }

            try {
                // Save selection immediately
                prefs.edit()
                    .putString(KEY_SELECTED_DISTRIBUTOR, packageName)
                    .apply()

                if (isFcmDirect) {
                    // Handle direct FCM registration
                    Log.d(TAG, "Registering with direct FCM")
                    val fcmToken = FcmDirectService.getRegistrationToken()

                    // For FCM, the "endpoint" is a special format that includes the token
                    val fcmEndpoint = "fcm:$fcmToken"
                    Log.d(TAG, "🔗 FCM endpoint generated: ${fcmEndpoint.take(50)}...")

                    // Register endpoint directly (we already hold the mutex)
                    registerEndpointDirectly(fcmEndpoint)

                    Log.d(TAG, "Direct FCM registration completed with token: ${fcmToken.take(20)}...")
                } else {
                    // Register with UnifiedPush distributor
                    Log.d(TAG, "🔄 Registering UnifiedPush with distributor: $packageName")

                    try {
                    	UnifiedPush.tryUseCurrentOrDefaultDistributor(context) { success ->

							if (!success) {
								Log.w(TAG, "⚠️ Failed to select distributor automatically")
							}

							UnifiedPush.register(context, packageName, "hillview_notifications")
							Log.d(TAG, "✅ UnifiedPush registration initiated")

							// Schedule debug check 5 seconds after registration
							CoroutineScope(Dispatchers.IO).launch {
								delay(5000)
								Log.d(TAG, "🕐 Post-registration status:")
								Log.d(TAG, debugUnifiedPush())
							}

                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "❌ UnifiedPush.register() threw exception", e)
                        throw e
                    }

                    // Note: The actual endpoint will be received via UnifiedPushService.onNewEndpoint
                    Log.d(TAG, "⏳ Waiting for UnifiedPush distributor '$packageName' to call onNewEndpoint...")
                }

                return@withLock true

            } catch (e: Exception) {
                val error = "Failed to register with distributor: ${e.message}"
                Log.e(TAG, error, e)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withLock false
            }
        }
    }

    /**
     * Register push endpoint with backend server
     * Called from UnifiedPushService when endpoint is received
     */
    suspend fun registerWithBackend(endpoint: String): Boolean = withContext(Dispatchers.IO) {
        Log.d(TAG, "🔑 Starting backend registration for endpoint: ${endpoint.take(50)}...")
        // Note: Caller should hold registrationMutex to avoid race conditions
        try {
            // Get client key ID for stable device identification
            Log.d(TAG, "🔑 Getting client key info...")
            val keyInfo = clientCrypto.getPublicKeyInfo()
            Log.d(TAG, "🔑 Client key info result: ${if (keyInfo != null) "success" else "null"}")
            if (keyInfo == null) {
                val error = "Client key not available"
                Log.e(TAG, error)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withContext false
            }

            // Get auth token if available (but don't require it)
            Log.d(TAG, "🎫 Getting auth token...")
            val token = authManager.getValidToken()
            Log.d(TAG, "🎫 Auth token available: ${token != null}")

            // Get server URL
            //Log.d(TAG, "🌐 Getting server URL from preferences...")
            val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val serverUrl = uploadPrefs.getString("server_url", null)
            Log.d(TAG, "🌐 Server URL: $serverUrl")
            if (serverUrl == null) {
                val error = "Server URL not configured"
                Log.e(TAG, error)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withContext false
            }

            // Generate signature for push registration
            //Log.d(TAG, "✍️ Generating signature for push registration...")
            val timestamp = System.currentTimeMillis()
            val selectedDistributor = getSelectedDistributor()
            Log.d(TAG, "✍️ Selected distributor: $selectedDistributor")
            val signatureData = clientCrypto.signPushRegistration(endpoint, selectedDistributor, timestamp)
            Log.d(TAG, "✍️ Signature generation result: ${if (signatureData != null) "success" else "null"}")
            if (signatureData == null) {
                val error = "Failed to generate push registration signature"
                Log.e(TAG, error)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withContext false
            }

            // Prepare registration request
            val url = "$serverUrl/push/register"
            val json = JSONObject().apply {
                put("push_endpoint", endpoint)
                put("distributor_package", selectedDistributor)
                put("timestamp", timestamp)
                put("client_signature", signatureData.signature)
                put("public_key_pem", keyInfo.publicKeyPem)
                put("key_created_at", keyInfo.createdAt)
            }

            // Make HTTP request with timeout configuration
            Log.d(TAG, "🌐 Sending push registration request to: $url")
            val client = okhttp3.OkHttpClient.Builder()
                .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .writeTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
                .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                .callTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
                .build()

            val mediaType = "application/json".toMediaType()
            val requestBody = json.toString().toRequestBody(mediaType)

            val requestBuilder = okhttp3.Request.Builder()
                .url(url)
                .post(requestBody)
                .addHeader("Content-Type", "application/json")

            // Only add Authorization header if we have a valid token
            if (token != null) {
                requestBuilder.addHeader("Authorization", "Bearer $token")
                Log.d(TAG, "📤 Adding Authorization header with token")
            } else {
                Log.d(TAG, "📤 No auth token available, sending request without Authorization header")
            }

            val request = requestBuilder.build()

            Log.d(TAG, "📤 Making HTTP POST request...")
            client.newCall(request).execute().use { response ->
                Log.d(TAG, "📥 Received response: HTTP ${response.code}")

                if (response.isSuccessful) {
                    // Store endpoint and mark as registered
                    prefs.edit()
                        .putString(KEY_PUSH_ENDPOINT, endpoint)
                        .putString(KEY_REGISTRATION_STATUS, "registered")
                        .remove(KEY_LAST_ERROR)
                        .apply()

                    Log.d(TAG, "Push endpoint registered successfully with backend")
                    return@withContext true
                } else {
                    val error = "Backend registration failed: HTTP ${response.code}"
                    Log.e(TAG, error)
                    setLastError(error)
                    setRegistrationStatus("failed")
                    return@withContext false
                }
            }

        } catch (e: java.net.SocketTimeoutException) {
            val error = "Backend registration timeout - server may be unreachable"
            Log.e(TAG, "⏰ $error", e)
            setLastError(error)
            setRegistrationStatus("failed")
            return@withContext false
        } catch (e: java.net.ConnectException) {
            val error = "Backend registration failed - connection refused"
            Log.e(TAG, "🔌 $error", e)
            setLastError(error)
            setRegistrationStatus("failed")
            return@withContext false
        } catch (e: java.io.IOException) {
            val error = "Backend registration failed - network error: ${e.message}"
            Log.e(TAG, "🌐 $error", e)
            setLastError(error)
            setRegistrationStatus("failed")
            return@withContext false
        } catch (e: Exception) {
            val error = "Exception during backend registration: ${e.javaClass.simpleName}: ${e.message}"
            Log.e(TAG, "❌ $error", e)
            setLastError(error)
            setRegistrationStatus("failed")
            return@withContext false
        }
    }

    /**
     * Unregister from current distributor and backend
     */
    suspend fun unregister(): Boolean {
        return registrationMutex.withLock {
            Log.d(TAG, "Unregistering push notifications")

            try {
                // Unregister from backend first
                val endpoint = getPushEndpoint()
                if (endpoint != null) {
                    unregisterFromBackend()
                }

                // Unregister from UnifiedPush
                UnifiedPush.unregister(context)

                // Clear all stored data
                prefs.edit()
                    .remove(KEY_SELECTED_DISTRIBUTOR)
                    .remove(KEY_PUSH_ENDPOINT)
                    .remove(KEY_REGISTRATION_STATUS)
                    .remove(KEY_LAST_ERROR)
                    .apply()

                Log.d(TAG, "Push notifications unregistered successfully")
                return@withLock true

            } catch (e: Exception) {
                Log.e(TAG, "Error during unregistration: ${e.message}", e)
                return@withLock false
            }
        }
    }

    /**
     * Enable or disable push notifications
     */
    fun setPushEnabled(enabled: Boolean) {
        prefs.edit()
            .putBoolean(KEY_ENABLED, enabled)
            .apply()

        Log.d(TAG, "Push notifications ${if (enabled) "enabled" else "disabled"}")
    }

    /**
     * Check if push notifications are enabled
     */
    fun isPushEnabled(): Boolean {
        return prefs.getBoolean(KEY_ENABLED, true) // Default to enabled
    }

    /**
     * Get currently selected distributor package name
     */
    fun getSelectedDistributor(): String? {
        return prefs.getString(KEY_SELECTED_DISTRIBUTOR, null)
    }

    /**
     * Get current push endpoint URL
     */
    fun getPushEndpoint(): String? {
        return prefs.getString(KEY_PUSH_ENDPOINT, null)
    }

    /**
     * Get last error message
     */
    fun getLastError(): String? {
        return prefs.getString(KEY_LAST_ERROR, null)
    }

    /**
     * Check if a distributor package is currently available
     */
    private fun isDistributorAvailable(packageName: String): Boolean {
        return if (packageName == "com.google.firebase.messaging.direct") {
            // Special case: FCM direct is a virtual distributor, check if FCM is actually available
            FcmDirectService.isAvailable(context)
        } else {
            // Regular UnifiedPush distributor: check if app package exists
            try {
                context.packageManager.getPackageInfo(packageName, 0)
                true
            } catch (e: PackageManager.NameNotFoundException) {
                false
            }
        }
    }

    /**
     * Get display name for a distributor package
     */
    private fun getDistributorDisplayName(packageName: String): String {
        return try {
            val pm = context.packageManager
            val appInfo = pm.getApplicationInfo(packageName, 0)
            pm.getApplicationLabel(appInfo).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            // Return package name if app not found (like DAVx5 does)
            packageName
        }
    }

    /**
     * Unregister from backend server
     */
    private suspend fun unregisterFromBackend() {
        try {
            // Get client key ID
            val keyInfo = clientCrypto.getPublicKeyInfo()
            if (keyInfo == null) {
                Log.e(TAG, "Client key not available for backend unregistration")
                return
            }

            // Get valid auth token
            val token = authManager.getValidToken()
            if (token == null) {
                Log.e(TAG, "Authentication not available for backend unregistration")
                return
            }

            // Get server URL
            val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val serverUrl = uploadPrefs.getString("server_url", null)
            if (serverUrl == null) {
                Log.e(TAG, "Server URL not configured for backend unregistration")
                return
            }

            // Make unregistration request
            val url = "$serverUrl/push/unregister/${keyInfo.keyId}"
            val client = okhttp3.OkHttpClient()

            val request = okhttp3.Request.Builder()
                .url(url)
                .delete()
                .addHeader("Authorization", "Bearer $token")
                .build()

            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Log.d(TAG, "Successfully unregistered from backend")
                } else {
                    Log.w(TAG, "Backend unregistration failed: HTTP ${response.code}")
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "Exception during backend unregistration: ${e.message}", e)
        }
    }

    /**
     * Handle FCM token refresh (called from FcmDirectService)
     */
    suspend fun onFcmTokenRefresh(newToken: String) {
        val selectedDistributor = getSelectedDistributor()
        if (selectedDistributor == "com.google.firebase.messaging.direct") {
            Log.d(TAG, "🔄 FCM token refreshed, updating backend registration")
            val fcmEndpoint = "fcm:$newToken"
            onNewEndpoint(fcmEndpoint)
        }
    }

    /**
     * Register endpoint directly (assumes caller already holds registrationMutex)
     */
    private suspend fun registerEndpointDirectly(endpoint: String) {
        Log.d(TAG, "💾 Storing endpoint directly: ${endpoint.take(50)}...")
        // Store the endpoint
        prefs.edit()
            .putString(KEY_PUSH_ENDPOINT, endpoint)
            .apply()

        try {
            // Register endpoint with backend using existing method
            Log.d(TAG, "🔑 Calling registerWithBackend...")
            val success = registerWithBackend(endpoint)
            Log.d(TAG, "🔙 Returned from registerWithBackend with success: $success")

            if (success) {
                Log.d(TAG, "✅ Successfully registered push endpoint with backend")
            } else {
                Log.e(TAG, "❌ Failed to register push endpoint with backend")
            }
        } catch (e: Exception) {
            setRegistrationStatus(RegistrationStatus.REGISTRATION_FAILED.name)
            setLastError("Backend registration error: ${e.message}")
            Log.e(TAG, "❌ Exception during backend registration", e)
        }
    }

    /**
     * Handle new endpoint received from UnifiedPush or FCM
     */
    suspend fun onNewEndpoint(endpoint: String) {
        Log.d(TAG, "🔗 Received new push endpoint: ${endpoint.take(50)}...")

        Log.d(TAG, "🔒 Attempting to acquire mutex for endpoint registration...")
        registrationMutex.withLock {
            Log.d(TAG, "🔓 Mutex acquired for onNewEndpoint")
            registerEndpointDirectly(endpoint)
        }
    }

    /**
     * Handle smart poke from FCM (called from FcmDirectService)
     */
    suspend fun handleSmartPoke(notificationId: String?) {
        Log.d(TAG, "🔔 Handling smart poke notification: $notificationId")
        try {
            // Use NotificationManager to fetch and display notifications
            val notificationManager = NotificationManager(context)
            notificationManager.checkForNewNotifications()
            Log.d(TAG, "✅ Smart poke handled successfully")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to handle smart poke", e)
        }
    }

    /**
     * Handle direct notification from FCM (called from FcmDirectService)
     */
    suspend fun handleDirectNotification(
        title: String?,
        body: String?,
        data: Map<String, String>
    ) {
        Log.d(TAG, "📬 Handling direct notification: $title")
        // Display notification directly without fetching from backend
        // TODO: Implement direct notification display logic
    }

    /**
     * Set last error message
     */
    private fun setLastError(error: String) {
        prefs.edit()
            .putString(KEY_LAST_ERROR, error)
            .apply()
    }

    /**
     * Set registration status
     */
    private fun setRegistrationStatus(status: String) {
        prefs.edit()
            .putString(KEY_REGISTRATION_STATUS, status)
            .apply()
    }
}
