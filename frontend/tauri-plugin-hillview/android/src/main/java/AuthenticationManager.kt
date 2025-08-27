package io.github.koo5.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import java.time.Instant
import java.time.format.DateTimeFormatter
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class AuthenticationManager(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val notificationHelper = NotificationHelper(context)
    private val refreshMutex = Mutex()

    companion object {
        private const val TAG = "🢄AuthenticationManager"
        private const val PREFS_NAME = "hillview_auth"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_EXPIRES_AT = "expires_at"
    }

    fun storeAuthToken(token: String, expiresAt: String, refreshToken: String? = null): Boolean {
        Log.d(TAG, "Storing auth token, expires at: $expiresAt, has refresh token: ${refreshToken != null}")
        return try {
            val editor = prefs.edit()
                .putString(KEY_AUTH_TOKEN, token)
                .putString(KEY_EXPIRES_AT, expiresAt)
            
            if (refreshToken != null) {
                editor.putString(KEY_REFRESH_TOKEN, refreshToken)
            }
            
            editor.apply()
            
            // Clear any auth expired notifications since user is now authenticated
            notificationHelper.clearAuthExpiredNotification()
            
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
        return getCurrentTokenIfValid()
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
    
    suspend fun refreshTokenIfNeeded(): Boolean {
        if (!isTokenExpired()) {
            Log.d(TAG, "Token not expired, no refresh needed")
            return true
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
    
    private suspend fun performTokenRefresh(refreshToken: String): Boolean {
        Log.d(TAG, "Performing token refresh...")
        
        try {
            val url = "http://10.0.2.2:8055/api/auth/refresh" // Android emulator backend URL
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
            
            val response = client.newCall(request).execute()
            
            if (response.isSuccessful) {
                val responseBody = response.body?.string()
                if (responseBody != null) {
                    // Parse JSON response (simple manual parsing)
                    val accessTokenMatch = Regex("\"access_token\":\\s*\"([^\"]+)\"").find(responseBody)
                    val refreshTokenMatch = Regex("\"refresh_token\":\\s*\"([^\"]+)\"").find(responseBody)
                    val expiresAtMatch = Regex("\"expires_at\":\\s*\"([^\"]+)\"").find(responseBody)
                    
                    if (accessTokenMatch != null && expiresAtMatch != null) {
                        val newAccessToken = accessTokenMatch.groupValues[1]
                        val newRefreshToken = refreshTokenMatch?.groupValues?.get(1)
                        val newExpiresAt = expiresAtMatch.groupValues[1]
                        
                        // Store new tokens
                        val stored = storeAuthToken(newAccessToken, newExpiresAt, newRefreshToken)
                        
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