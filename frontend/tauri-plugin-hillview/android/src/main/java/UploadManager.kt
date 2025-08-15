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
        private const val TAG = "UploadManager"
        private const val PREFS_NAME = "hillview_upload_prefs"
        private const val PREF_SERVER_URL = "server_url"
        private const val PREF_AUTH_TOKEN = "auth_token"
        private const val DEFAULT_SERVER_URL = "http://localhost:8055"
    }
    
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    
    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    
    suspend fun uploadPhoto(photo: PhotoEntity): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Starting upload for photo: ${photo.filename}")
            
            val file = File(photo.path)
            if (!file.exists()) {
                Log.e(TAG, "Photo file does not exist: ${photo.path}")
                return@withContext false
            }
            
            val serverUrl = getServerUrl()
            val authToken = getAuthToken()
            
            if (authToken.isNullOrEmpty()) {
                Log.e(TAG, "No auth token available for upload")
                return@withContext false
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
                .url("$serverUrl/api/photos/upload")
                .addHeader("Authorization", "Bearer $authToken")
                .post(requestBody)
                .build()
            
            Log.d(TAG, "Sending upload request to: $serverUrl/api/photos/upload")
            
            client.newCall(request).execute().use { response ->
                val success = response.isSuccessful
                
                if (success) {
                    Log.d(TAG, "Upload successful for photo: ${photo.filename}")
                    Log.d(TAG, "Response: ${response.body?.string()}")
                } else {
                    Log.e(TAG, "Upload failed for photo: ${photo.filename}")
                    Log.e(TAG, "Response code: ${response.code}")
                    Log.e(TAG, "Response message: ${response.message}")
                    Log.e(TAG, "Response body: ${response.body?.string()}")
                }
                
                return@withContext success
            }
            
        } catch (e: IOException) {
            Log.e(TAG, "Network error uploading photo: ${photo.filename}", e)
            return@withContext false
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error uploading photo: ${photo.filename}", e)
            return@withContext false
        }
    }
    
    fun setServerUrl(url: String) {
        prefs.edit().putString(PREF_SERVER_URL, url).apply()
        Log.d(TAG, "Server URL updated to: $url")
    }
    
    fun getServerUrl(): String {
        return prefs.getString(PREF_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
    }
    
    fun setAuthToken(token: String) {
        prefs.edit().putString(PREF_AUTH_TOKEN, token).apply()
        Log.d(TAG, "Auth token updated")
    }
    
    fun getAuthToken(): String? {
        return prefs.getString(PREF_AUTH_TOKEN, null)
    }
    
    fun clearAuthToken() {
        prefs.edit().remove(PREF_AUTH_TOKEN).apply()
        Log.d(TAG, "Auth token cleared")
    }
    
    suspend fun testConnection(): Boolean = withContext(Dispatchers.IO) {
        try {
            val serverUrl = getServerUrl()
            val request = Request.Builder()
                .url("$serverUrl/api/auth/me")
                .addHeader("Authorization", "Bearer ${getAuthToken()}")
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