package io.github.koo5.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import java.time.Instant
import java.time.format.DateTimeFormatter

class AuthenticationManager(private val context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    companion object {
        private const val TAG = "AuthenticationManager"
        private const val PREFS_NAME = "hillview_auth"
        private const val KEY_AUTH_TOKEN = "auth_token"
        private const val KEY_EXPIRES_AT = "expires_at"
    }

    fun storeAuthToken(token: String, expiresAt: String): Boolean {
        Log.d(TAG, "Storing auth token, expires at: $expiresAt")
        return try {
            prefs.edit()
                .putString(KEY_AUTH_TOKEN, token)
                .putString(KEY_EXPIRES_AT, expiresAt)
                .apply()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error storing auth token: ${e.message}")
            false
        }
    }

    fun getValidToken(): String? {
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

    fun getTokenInfo(): Pair<String?, String?> {
        val token = prefs.getString(KEY_AUTH_TOKEN, null)
        val expiresAt = prefs.getString(KEY_EXPIRES_AT, null)
        return Pair(token, expiresAt)
    }

    fun clearAuthToken(): Boolean {
        Log.d(TAG, "Clearing auth token")
        return try {
            prefs.edit()
                .remove(KEY_AUTH_TOKEN)
                .remove(KEY_EXPIRES_AT)
                .apply()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error clearing auth token: ${e.message}")
            false
        }
    }

    fun hasValidToken(): Boolean {
        return getValidToken() != null
    }
}