package cz.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import java.time.Instant
import java.time.format.DateTimeFormatter
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject

class AuthenticationManager(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val notificationHelper = NotificationHelper(context)
    private val refreshMutex = Mutex()
    private val clientCrypto = ClientCryptoManager(context)

    companion object {
        private const val TAG = "🢄AuthenticationManager"
        private const val PREFS_NAME = "hillview_auth"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_EXPIRES_AT = "expires_at"
        private const val KEY_REFRESH_EXPIRES_AT = "refresh_expires_at"
    }

    suspend fun storeAuthToken(token: String, expiresAt: String, refreshToken: String? = null, refreshExpiresAt: String? = null): Boolean {
        Log.d(TAG, "Storing auth token, expires at: $expiresAt, has refresh token: ${refreshToken != null}, refresh expires at: $refreshExpiresAt")
        return try {
            val editor = prefs.edit()
                .putString(KEY_AUTH_TOKEN, token)
                .putString(KEY_EXPIRES_AT, expiresAt)

            if (refreshToken != null) {
                editor.putString(KEY_REFRESH_TOKEN, refreshToken)
            }

            if (refreshExpiresAt != null) {
                editor.putString(KEY_REFRESH_EXPIRES_AT, refreshExpiresAt)
            }

            editor.apply()
            Log.d(TAG, "Tokens stored successfully in SharedPreferences")

            // Clear any auth expired notifications since user is now authenticated
            notificationHelper.clearAuthExpiredNotification()

            // Register client public key after storing tokens (synchronous - must complete before uploads can start)
            try {
                Log.d(TAG, "Registering client public key after token storage")
                val keyRegistered = registerClientPublicKey(token)
                if (!keyRegistered) {
                    Log.e(TAG, "Client public key registration failed - this will prevent photo uploads")
                    return false // Fail token storage if key registration fails
                }
                Log.d(TAG, "Client public key registered successfully during token storage")
            } catch (e: Exception) {
                Log.e(TAG, "Error registering client public key during token storage", e)
                return false // Fail token storage if key registration fails
            }

            true
        } catch (e: Exception) {
            Log.e(TAG, "Error storing auth token: ${e.message}")
            false
        }
    }

    /**
     * Get a valid authentication token, automatically refreshing if needed.
     * This is the main method that should be used by all components needing auth.
     * Uses mutex to prevent concurrent refresh attempts.
     *
     * @return A valid token, or null if authentication failed/unavailable
     */
    suspend fun getValidToken(): String? {
        // First check if current token is valid (outside mutex for performance)
        val currentToken = getCurrentTokenIfValid()
        if (currentToken != null) {
            return currentToken
        }

        Log.d(TAG, "Token expired or missing, attempting refresh...")

        // Use mutex to prevent multiple simultaneous refresh attempts
        return refreshMutex.withLock {
            // Double-check inside mutex - another thread may have refreshed already
            val tokenAfterLock = getCurrentTokenIfValid()
            if (tokenAfterLock != null) {
                Log.d(TAG, "Token was refreshed by another thread")
                return@withLock tokenAfterLock
            }

            // Try to refresh the token
            if (refreshTokenIfNeeded()) {
                // Return the new token after successful refresh
                return@withLock getCurrentTokenIfValid()
            }

            Log.w(TAG, "Unable to obtain valid token (refresh failed or no refresh token)")
            return@withLock null
        }
    }

    /**
     * Get current token only if it's valid (non-expired).
     * Does not attempt refresh - for internal use only.
     */
    private fun getCurrentTokenIfValid(): String? {
        val token = prefs.getString(KEY_AUTH_TOKEN, null) ?: return null
        val expiresAt = prefs.getString(KEY_EXPIRES_AT, null) ?: return null

        // Check if token is expired
        return try {
            val expiry = Instant.from(DateTimeFormatter.ISO_INSTANT.parse(expiresAt))
            val now = Instant.now()

            if (now.isAfter(expiry.minusSeconds(60))) { // Refresh 1 minute before expiry
                Log.d(TAG, "Token is expired or expiring soon")
                null
            } else {
                Log.d(TAG, "Token is valid, expires at: $expiresAt")
                token
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing token expiry: ${e.message}")
            null
        }
    }

    /**
     * Synchronous version for cases where async is not possible.
     * WARNING: Does not attempt token refresh - may return null for expired tokens.
     * Use getValidToken() instead when possible.
     */
    fun getValidTokenSync(): String? {
        val result = getCurrentTokenIfValid()
        Log.d(TAG, "getValidTokenSync() called - result: ${if (result != null) "token found" else "null"}")
        return result
    }

    fun getTokenInfo(): Pair<String?, String?> {
        val token = prefs.getString(KEY_AUTH_TOKEN, null)
        val expiresAt = prefs.getString(KEY_EXPIRES_AT, null)
        return Pair(token, expiresAt)
    }

    fun getRefreshToken(): String? {
        return prefs.getString(KEY_REFRESH_TOKEN, null)
    }

    fun isTokenExpired(bufferMinutes: Int = 2): Boolean {
        val expiresAt = prefs.getString(KEY_EXPIRES_AT, null) ?: return true

        return try {
            val expiry = Instant.from(DateTimeFormatter.ISO_INSTANT.parse(expiresAt))
            val now = Instant.now()
            val bufferSeconds = bufferMinutes * 60L

            now.isAfter(expiry.minusSeconds(bufferSeconds))
        } catch (e: Exception) {
            Log.e(TAG, "Error checking token expiry: ${e.message}")
            true // Assume expired on error
        }
    }

    /**
     * Check if refresh token is expiring soon and needs proactive renewal
     * @param bufferDays Days before expiry to trigger renewal (default: 3)
     */
    private fun shouldRenewRefreshToken(bufferDays: Int = 3): Boolean {
        val refreshExpiresAt = prefs.getString(KEY_REFRESH_EXPIRES_AT, null) ?: run {
            Log.e(TAG, "No refresh token expiry stored - invalid token state")
            return false
        }

        return try {
            val expiry = Instant.from(DateTimeFormatter.ISO_INSTANT.parse(refreshExpiresAt))
            val now = Instant.now()
            val bufferSeconds = bufferDays * 24 * 60 * 60L // Convert days to seconds

            val shouldRenew = now.isAfter(expiry.minusSeconds(bufferSeconds))
            
            if (shouldRenew) {
                val daysRemaining = (expiry.epochSecond - now.epochSecond) / (24 * 60 * 60)
                Log.d(TAG, "Refresh token expiring in $daysRemaining days, triggering proactive renewal")
            }

            shouldRenew
        } catch (e: Exception) {
            Log.e(TAG, "Error checking refresh token renewal need: ${e.message}")
            false
        }
    }

    suspend fun refreshTokenIfNeeded(): Boolean {
        val tokenExpired = isTokenExpired()
        val needsRefreshRenewal = shouldRenewRefreshToken()
        
        if (!tokenExpired && !needsRefreshRenewal) {
            Log.d(TAG, "Token not expired and refresh token not expiring soon, no refresh needed")
            return true
        }
        
        if (tokenExpired) {
            Log.d(TAG, "Access token expired, attempting refresh")
        } else {
            Log.d(TAG, "Refresh token expiring soon, performing proactive renewal")
        }

        val refreshToken = getRefreshToken() ?: run {
            Log.w(TAG, "No refresh token available - user needs to re-authenticate")

            // Show notification if we have an access token but no refresh token
            // (This means user is logged in but can't refresh - auth will fail soon)
            if (prefs.getString(KEY_AUTH_TOKEN, null) != null) {
                notificationHelper.showAuthExpiredNotification()
            }

            return false
        }

        return performTokenRefresh(refreshToken)
    }

    suspend fun registerClientPublicKey(token: String): Boolean {
        Log.d(TAG, "Registering client public key with server")

        try {
            // Get client public key info
            val keyInfo = clientCrypto.getPublicKeyInfo() ?: run {
                Log.e(TAG, "Failed to get client public key info")
                return false
            }

            // Get server URL from shared preferences
            val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val serverUrl = uploadPrefs.getString("server_url", null) ?: run {
                Log.e(TAG, "Server URL not configured - user needs to login first")
                return false
            }

            val url = "$serverUrl/auth/register-client-key"
            val json = JSONObject().apply {
                put("public_key_pem", keyInfo.publicKeyPem)
                put("key_id", keyInfo.keyId)
                put("created_at", keyInfo.createdAt)
            }

            // Debug: Log the JSON payload
            val jsonString = json.toString()
            Log.d(TAG, "Sending JSON payload to register-client-key:")
            Log.d(TAG, "JSON length: ${jsonString.length}")
            Log.d(TAG, "Key ID: ${keyInfo.keyId}")
            Log.d(TAG, "Created at: ${keyInfo.createdAt}")
            Log.d(TAG, "PEM preview: ${keyInfo.publicKeyPem.take(50)}...")
            Log.d(TAG, "Full JSON: $jsonString")

            // Use OkHttp for the HTTP request
            val client = okhttp3.OkHttpClient()
            val mediaType = "application/json".toMediaType()
            val requestBody = jsonString.toRequestBody(mediaType)

            val request = okhttp3.Request.Builder()
                .url(url)
                .post(requestBody)
                .addHeader("Content-Type", "application/json")
                .addHeader("Authorization", "Bearer $token")
                .build()

            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                Log.d(TAG, "Client public key registered successfully")
                return true
            } else if (response.code == 409) {
                // 409 means key already exists - this is actually OK
                Log.d(TAG, "Client public key already exists on server (409) - treating as success")
                return true
            } else {
                Log.e(TAG, "Client public key registration failed with status: ${response.code}")
                val responseBody = response.body?.string()
                Log.e(TAG, "Registration error response: $responseBody")
                return false
            }

        } catch (e: Exception) {
            Log.e(TAG, "Exception during client public key registration: ${e.message}", e)
            return false
        }
    }

    private suspend fun performTokenRefresh(refreshToken: String): Boolean {
        Log.d(TAG, "Performing token refresh...")

        // Check if refresh token is expired before attempting refresh
        val refreshExpiresAt = prefs.getString(KEY_REFRESH_EXPIRES_AT, null)
        if (refreshExpiresAt != null) {
            try {
                val expiry = Instant.from(DateTimeFormatter.ISO_INSTANT.parse(refreshExpiresAt))
                val now = Instant.now()
                val bufferSeconds = 1 * 60L // 1 minute buffer
                
                if (now.isAfter(expiry.minusSeconds(bufferSeconds))) {
                    Log.w(TAG, "Refresh token expired at $refreshExpiresAt, current time: $now")
                    return false
                }
                
                val hoursRemaining = (expiry.epochSecond - now.epochSecond) / 3600
                Log.d(TAG, "Refresh token valid until $refreshExpiresAt ($hoursRemaining hours remaining)")
            } catch (dateError: Exception) {
                Log.w(TAG, "Could not parse refresh token expiry date: $refreshExpiresAt", dateError)
                // Continue with refresh attempt - let server decide
            }
        } else {
            Log.e(TAG, "No refresh token expiry stored - invalid token state, refresh will fail")
            return false
        }

        try {
            // Get server URL from shared preferences (set by upload config)
            val uploadPrefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val serverUrl = uploadPrefs.getString("server_url", null) ?: run {
                Log.e(TAG, "Server URL not configured - user needs to login first")
                return false
            }
            val url = "$serverUrl/auth/refresh"
            val json = """{"refresh_token":"$refreshToken"}"""

            // Use OkHttp for the HTTP request (assuming it's available from UploadManager)
            val client = okhttp3.OkHttpClient()
            val mediaType = "application/json".toMediaType()
            val requestBody = json.toRequestBody(mediaType)

            val request = okhttp3.Request.Builder()
                .url(url)
                .post(requestBody)
                .addHeader("Content-Type", "application/json")
                .build()

			Log.d(TAG, "Sending token refresh request to $url, body: $json")

            val response = client.newCall(request).execute()

            if (response.isSuccessful) {
                val responseBody = response.body?.string()
                if (responseBody != null) {
                    // Parse JSON response (simple manual parsing)
                    val accessTokenMatch = Regex("\"access_token\":\\s*\"([^\"]+)\"").find(responseBody)
                    val refreshTokenMatch = Regex("\"refresh_token\":\\s*\"([^\"]+)\"").find(responseBody)
                    val expiresAtMatch = Regex("\"expires_at\":\\s*\"([^\"]+)\"").find(responseBody)
                    val refreshExpiresAtMatch = Regex("\"refresh_token_expires_at\":\\s*\"([^\"]+)\"").find(responseBody)

                    if (accessTokenMatch != null && expiresAtMatch != null) {
                        val newAccessToken = accessTokenMatch.groupValues[1]
                        val newRefreshToken = refreshTokenMatch?.groupValues?.get(1)
                        val newExpiresAt = expiresAtMatch.groupValues[1]
                        val newRefreshExpiresAt = refreshExpiresAtMatch?.groupValues?.get(1)

                        Log.d(TAG, "Parsed refresh response - access expires: $newExpiresAt, refresh expires: $newRefreshExpiresAt")

                        // Store new tokens
                        val stored = storeAuthToken(newAccessToken, newExpiresAt, newRefreshToken, newRefreshExpiresAt)

                        if (stored) {
                            Log.d(TAG, "Token refresh successful")
                            return true
                        } else {
                            Log.e(TAG, "Failed to store refreshed tokens")
                        }
                    } else {
                        Log.e(TAG, "Failed to parse refresh response")
                    }
                }
            } else {
                Log.e(TAG, "Token refresh failed with status: ${response.code}")

                // If refresh token is expired/invalid, clear all auth data
                if (response.code == 401) {
                    Log.w(TAG, "Refresh token expired/invalid - clearing all auth data and notifying user")
                    clearAuthToken()

                    // Show push notification to user about auth expiry
                    notificationHelper.showAuthExpiredNotification()
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "Exception during token refresh: ${e.message}", e)
        }

        return false
    }

    fun clearAuthToken(): Boolean {
        Log.d(TAG, "Clearing auth token")
        return try {
            prefs.edit()
                .remove(KEY_AUTH_TOKEN)
                .remove(KEY_REFRESH_TOKEN)
                .remove(KEY_EXPIRES_AT)
                .remove(KEY_REFRESH_EXPIRES_AT)
                .apply()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error clearing auth token: ${e.message}")
            false
        }
    }

    /**
     * Check if we have a valid token available.
     * Uses synchronous check - does not attempt refresh.
     * For checking with refresh, use getValidToken() != null
     */
    fun hasValidToken(): Boolean {
        return getCurrentTokenIfValid() != null
    }

    /**
     * Check if we have any authentication data stored (even if expired).
     * Useful for UI state - doesn't check expiry.
     */
    fun hasStoredAuth(): Boolean {
        return prefs.getString(KEY_AUTH_TOKEN, null) != null
    }
}
