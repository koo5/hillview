package io.github.koo5.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

class UploadManager(private val context: Context) {
    
    companion object {
        private const val TAG = "🢄UploadManager"
        private const val PREFS_NAME = "hillview_upload_prefs"
        private const val PREF_SERVER_URL = "server_url"
    }
    
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val authManager = AuthenticationManager(context)
    
    suspend fun uploadPhoto(photo: PhotoEntity): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Starting upload for photo: ${photo.filename}")
            
            val file = File(photo.path)
            if (!file.exists()) {
                Log.e(TAG, "Photo file does not exist: ${photo.path}")
                return@withContext false
            }
            
            // Try upload with automatic token refresh
            return@withContext attemptUpload(file, photo.filename)
            
        } catch (e: IOException) {
            Log.e(TAG, "Network error uploading photo: ${photo.filename}", e)
            return@withContext false
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error uploading photo: ${photo.filename}", e)
            return@withContext false
        }
    }
    
    private suspend fun attemptUpload(file: File, filename: String): Boolean {
        val serverUrl = getServerUrl()
        if (serverUrl == null) {
            Log.e(TAG, "Server URL not configured. Please login first.")
            return false
        }
        
        // Get valid auth token (with automatic refresh)
        val authToken = authManager.getValidToken()
        if (authToken == null) {
            Log.e(TAG, "No valid auth token available for upload")
            return false
        }
        
        val mediaType = when (file.extension.lowercase()) {
            "jpg", "jpeg" -> "image/jpeg".toMediaType()
            "png" -> "image/png".toMediaType()
            "webp" -> "image/webp".toMediaType()
            else -> "image/jpeg".toMediaType()
        }
        
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file",
                file.name,
                file.asRequestBody(mediaType)
            )
            .addFormDataPart("description", "Auto-uploaded from Hillview Android")
            .addFormDataPart("is_public", "true")
            .build()
        
        val request = Request.Builder()
            .url("$serverUrl/photos/upload")
            .addHeader("Authorization", "Bearer $authToken")
            .post(requestBody)
            .build()
        
        Log.d(TAG, "Sending upload request.")
        
        client.newCall(request).execute().use { response ->
            when {
                response.isSuccessful -> {
                    Log.d(TAG, "Upload successful for photo: $filename")
                    Log.d(TAG, "Response: ${response.body?.string()}")
                    return true
                }
                response.code == 401 -> {
                    Log.w(TAG, "Upload failed with 401 (auth error) for photo: $filename")
                    Log.w(TAG, "Auth token may have expired during upload - should have been refreshed already")
                    Log.e(TAG, "Response body: ${response.body?.string()}")
                    return false
                }
                else -> {
                    Log.e(TAG, "Upload failed for photo: $filename")
                    Log.e(TAG, "Response code: ${response.code}")
                    Log.e(TAG, "Response message: ${response.message}")
                    Log.e(TAG, "Response body: ${response.body?.string()}")
                    return false
                }
            }
        }
    }
    
    fun setServerUrl(url: String) {
        prefs.edit().putString(PREF_SERVER_URL, url).apply()
        Log.d(TAG, "Server URL updated to: $url")
    }
    
    fun getServerUrl(): String? {
        val url = prefs.getString(PREF_SERVER_URL, null)
        if (url == null) {
            Log.w(TAG, "Server URL not configured. Please call setServerUrl() first.")
        }
        return url
    }
    
    // Auth token methods removed - now handled by AuthenticationManager
    
    suspend fun testConnection(): Boolean = withContext(Dispatchers.IO) {
        try {
            val serverUrl = getServerUrl()
            if (serverUrl == null) {
                Log.e(TAG, "Server URL not configured. Please login first.")
                return@withContext false
            }
            val authToken = authManager.getValidToken()
            
            if (authToken == null) {
                Log.e(TAG, "No valid auth token for connection test")
                return@withContext false
            }
            
            val request = Request.Builder()
                .url("$serverUrl/api/auth/me")
                .addHeader("Authorization", "Bearer $authToken")
                .get()
                .build()
            
            client.newCall(request).execute().use { response ->
                val success = response.isSuccessful
                Log.d(TAG, "Connection test result: $success")
                return@withContext success
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Connection test failed", e)
            return@withContext false
        }
    }
}