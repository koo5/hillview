package cz.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.util.Log
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.unifiedpush.android.connector.UnifiedPush

/**
 * Android Push Notification Distributor Manager
 *
 * Manages UnifiedPush distributor selection and registration, providing smart
 * status detection and error handling similar to DAVx5's implementation.
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
    }

    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val clientCrypto = ClientCryptoManager(context)
    private val authManager = AuthenticationManager(context)
    private val registrationMutex = Mutex()

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
        val isAvailable: Boolean,
        val isSelected: Boolean
    )

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
                isAvailable = isDistributorAvailable(packageName),
                isSelected = packageName == selectedDistributor
            )
        }.toMutableList()

        // If we have a selected distributor that's not in the current list,
        // add it as unavailable (like DAVx5 does)
        selectedDistributor?.let { selected ->
            if (distributorInfoList.none { it.packageName == selected }) {
                distributorInfoList.add(
                    DistributorInfo(
                        packageName = selected,
                        displayName = getDistributorDisplayName(selected),
                        isAvailable = false,
                        isSelected = true
                    )
                )
            }
        }

        Log.d(TAG, "📨 Final distributor list size: ${distributorInfoList.size}")
        distributorInfoList.forEach { dist ->
            Log.d(TAG, "📨   - ${dist.displayName} (${dist.packageName}): available=${dist.isAvailable}, selected=${dist.isSelected}")
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
     * Auto-register with first available distributor if none selected
     */
    suspend fun autoRegisterIfNeeded() {
        val selectedDistributor = getSelectedDistributor()
        if (selectedDistributor != null) {
            return // Already have a distributor selected
        }

        val availableDistributors = getAvailableDistributors().filter { it.isAvailable }
        if (availableDistributors.isEmpty()) {
            Log.d(TAG, "No available distributors for auto-registration")
            return
        }

        val firstDistributor = availableDistributors[0]
        Log.d(TAG, "Auto-registering with first available distributor: ${firstDistributor.packageName}")
        selectDistributor(firstDistributor.packageName)
    }

    /**
     * Select a UnifiedPush distributor and register with backend
     */
    suspend fun selectDistributor(packageName: String): Boolean {
        return registrationMutex.withLock {
            Log.d(TAG, "Selecting distributor: $packageName")

            if (!isDistributorAvailable(packageName)) {
                val error = "Selected distributor is not available"
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

                // Register with UnifiedPush distributor
                UnifiedPush.registerApp(context, packageName, "hillview_notifications")

                // Note: The actual endpoint will be received via UnifiedPushService.onNewEndpoint
                // and then we'll register with the backend

                Log.d(TAG, "UnifiedPush registration initiated for $packageName")
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
    suspend fun registerWithBackend(endpoint: String): Boolean {
        return registrationMutex.withLock {
            Log.d(TAG, "Registering push endpoint with backend: $endpoint")

            try {
                // Get client key ID for stable device identification
                val keyInfo = clientCrypto.getPublicKeyInfo()
                if (keyInfo == null) {
                    val error = "Client key not available"
                    Log.e(TAG, error)
                    setLastError(error)
                    setRegistrationStatus("failed")
                    return@withLock false
                }

                // Get auth token if available (but don't require it)
                val token = authManager.getValidToken()
                Log.d(TAG, "Auth token available: ${token != null}")

                // Get server URL
                val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
                val serverUrl = uploadPrefs.getString("server_url", null)
                if (serverUrl == null) {
                    val error = "Server URL not configured"
                    Log.e(TAG, error)
                    setLastError(error)
                    setRegistrationStatus("failed")
                    return@withLock false
                }

                // Prepare registration request
                val url = "$serverUrl/push/register"
                val selectedDistributor = getSelectedDistributor()
                val json = JSONObject().apply {
                    put("client_key_id", keyInfo.keyId)
                    put("push_endpoint", endpoint)
                    put("distributor_package", selectedDistributor)
                }

                // Make HTTP request
                val client = okhttp3.OkHttpClient()
                val mediaType = "application/json".toMediaType()
                val requestBody = json.toString().toRequestBody(mediaType)

                val request = okhttp3.Request.Builder()
                    .url(url)
                    .post(requestBody)
                    .addHeader("Content-Type", "application/json")
                    .addHeader("Authorization", "Bearer $token")
                    .build()

                val response = client.newCall(request).execute()

                if (response.isSuccessful) {
                    // Store endpoint and mark as registered
                    prefs.edit()
                        .putString(KEY_PUSH_ENDPOINT, endpoint)
                        .putString(KEY_REGISTRATION_STATUS, "registered")
                        .remove(KEY_LAST_ERROR)
                        .apply()

                    Log.d(TAG, "Push endpoint registered successfully with backend")
                    return@withLock true
                } else {
                    val error = "Backend registration failed: HTTP ${response.code}"
                    Log.e(TAG, error)
                    setLastError(error)
                    setRegistrationStatus("failed")
                    return@withLock false
                }

            } catch (e: Exception) {
                val error = "Exception during backend registration: ${e.message}"
                Log.e(TAG, error, e)
                setLastError(error)
                setRegistrationStatus("failed")
                return@withLock false
            }
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
                UnifiedPush.unregisterApp(context)

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
        return try {
            context.packageManager.getPackageInfo(packageName, 0)
            true
        } catch (e: PackageManager.NameNotFoundException) {
            false
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

            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                Log.d(TAG, "Successfully unregistered from backend")
            } else {
                Log.w(TAG, "Backend unregistration failed: HTTP ${response.code}")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Exception during backend unregistration: ${e.message}", e)
        }
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