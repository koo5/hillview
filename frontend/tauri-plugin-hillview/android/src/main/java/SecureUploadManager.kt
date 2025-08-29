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
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

/**
 * Secure Upload Manager for Android Background Uploads
 * 
 * Implements the three-phase secure upload process for PhotoEntity records:
 * 1. Request upload authorization from API server (using PhotoEntity geolocation)
 * 2. Generate client signature and upload to worker (using worker_url from auth response)  
 * 3. Worker verifies JWT and forwards results to API server
 * 
 * This ensures that even compromised workers cannot impersonate users.
 */
class SecureUploadManager(private val context: Context) {
    
    companion object {
        private const val TAG = "🔐SecureUploadManager"
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
    private val clientCrypto = ClientCryptoManager(context)
    
    data class UploadAuthorizationResponse(
        val upload_jwt: String,
        val photo_id: String,
        val expires_at: String,
        val worker_url: String
    )
    
    /**
     * Request upload authorization from API server using PhotoEntity data
     */
    private suspend fun requestUploadAuthorization(photo: PhotoEntity, file: File): UploadAuthorizationResponse {
        val serverUrl = getServerUrl() ?: throw Exception("Server URL not configured")
        val authToken = authManager.getValidToken() ?: throw Exception("No valid auth token")
        
        val contentType = when (file.extension.lowercase()) {
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "webp" -> "image/webp"
            else -> "image/jpeg"
        }
        
        // Convert timestamp to ISO format for captured_at
        val capturedAt = try {
            val date = Date(photo.timestamp)
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }.format(date)
        } catch (e: Exception) {
            null
        }
        
        val json = JSONObject().apply {
            put("filename", photo.filename)
            put("file_size", photo.fileSize)
            put("content_type", contentType)
            put("description", "Auto-uploaded from Hillview Android")  // Could be made configurable
            put("is_public", true)  // Could be made configurable
            // Use PhotoEntity geolocation data
            put("latitude", photo.latitude)
            put("longitude", photo.longitude)
            if (photo.altitude > 0) put("altitude", photo.altitude)
            if (photo.bearing != 0.0) put("compass_angle", photo.bearing)
            capturedAt?.let { put("captured_at", it) }
        }
        
        val requestBody = json.toString().toRequestBody("application/json".toMediaType())
        val httpRequest = Request.Builder()
            .url("$serverUrl/photos/authorize-upload")
            .addHeader("Authorization", "Bearer $authToken")
            .post(requestBody)
            .build()
        
        Log.d(TAG, "Requesting upload authorization for: ${photo.filename}")
        
        client.newCall(httpRequest).execute().use { response ->
            if (!response.isSuccessful) {
                val error = response.body?.string() ?: "Unknown error"
                throw Exception("Upload authorization failed: ${response.code} - $error")
            }
            
            val responseJson = JSONObject(response.body!!.string())
            return UploadAuthorizationResponse(
                upload_jwt = responseJson.getString("upload_jwt"),
                photo_id = responseJson.getString("photo_id"),
                expires_at = responseJson.getString("expires_at"),
                worker_url = responseJson.getString("worker_url")
            )
        }
    }
    
    /**
     * Generate client signature for upload
     */
    private fun generateClientSignature(photoId: String, filename: String): String? {
        val timestamp = System.currentTimeMillis() / 1000
        return clientCrypto.signUploadData(photoId, filename, timestamp)
    }
    
    /**
     * Upload file to worker with JWT and client signature
     */
    private suspend fun uploadToWorker(
        file: File,
        filename: String,
        uploadJwt: String,
        clientSignature: String,
        workerUrl: String
    ): Boolean {
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
                filename,  // Use original filename from PhotoEntity
                file.asRequestBody(mediaType)
            )
            .addFormDataPart("client_signature", clientSignature)
            .build()
        
        val request = Request.Builder()
            .url("$workerUrl/upload")
            .addHeader("Authorization", "Bearer $uploadJwt")
            .post(requestBody)
            .build()
        
        Log.d(TAG, "Uploading to worker: $filename")
        
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val error = response.body?.string() ?: "Unknown error"
                Log.e(TAG, "Worker upload failed: ${response.code} - $error")
                return false
            }
            
            val responseJson = JSONObject(response.body!!.string())
            val success = responseJson.optBoolean("success", false)
            
            if (success) {
                Log.d(TAG, "✅ Secure upload completed: $filename")
            } else {
                val errorMsg = responseJson.optString("error", "Unknown worker error")
                Log.e(TAG, "❌ Worker processing failed: $errorMsg")
            }
            
            return success
        }
    }
    
    /**
     * Perform secure upload of a PhotoEntity record
     */
    suspend fun secureUploadPhoto(photo: PhotoEntity): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Starting secure upload for photo: ${photo.filename}")
            
            val file = File(photo.path)
            if (!file.exists()) {
                Log.e(TAG, "Photo file does not exist: ${photo.path}")
                return@withContext false
            }
            
            // Step 1: Request upload authorization (includes PhotoEntity geolocation)
            val authResponse = requestUploadAuthorization(photo, file)
            Log.d(TAG, "Upload authorized, photo_id: ${authResponse.photo_id}")
            
            // Step 2: Generate client signature
            val clientSignature = generateClientSignature(authResponse.photo_id, photo.filename)
            if (clientSignature == null) {
                Log.e(TAG, "Failed to generate client signature for: ${photo.filename}")
                return@withContext false
            }
            
            Log.d(TAG, "Client signature generated for: ${photo.filename}")
            
            // Step 3: Upload to worker (using worker_url from auth response)
            val uploadSuccess = uploadToWorker(
                file, 
                photo.filename,
                authResponse.upload_jwt, 
                clientSignature,
                authResponse.worker_url
            )
            
            if (uploadSuccess) {
                Log.d(TAG, "✅ Secure upload successful: ${photo.filename}")
            } else {
                Log.e(TAG, "❌ Secure upload failed: ${photo.filename}")
            }
            
            return@withContext uploadSuccess
            
        } catch (e: IOException) {
            Log.e(TAG, "Network error in secure upload: ${photo.filename}", e)
            return@withContext false
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error in secure upload: ${photo.filename}", e)
            return@withContext false
        }
    }
    
    private fun getServerUrl(): String? {
        return prefs.getString(PREF_SERVER_URL, null)
    }
    
    fun setServerUrl(url: String) {
        prefs.edit().putString(PREF_SERVER_URL, url).apply()
        Log.d(TAG, "Server URL set to: $url")
    }
}