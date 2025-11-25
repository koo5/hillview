package cz.hillview.plugin

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
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

// Database imports for duplicate handling
import cz.hillview.plugin.PhotoDatabase

/**
 * Exception thrown when a duplicate file is detected and handled
 */
class DuplicateFileException(message: String) : Exception(message)

/**
 * Secure Upload Manager for Android Background Uploads
 *
 * Implements the three-phase secure upload process for PhotoEntity records:
 * 1. Request upload authorization from API server (using PhotoEntity geolocation)
 * 2. Generate client signature and upload to worker (using worker_url from auth response)
 * 3. Worker verifies JWT and forwards results to API server
 *
 * This ensures that even compromised workers cannot impersonate users.
 *
 * Also provides foreground service capabilities for persistent uploads with notifications.
 */
class SecureUploadManager : Service() {

    companion object {
        private const val TAG = "🢄Upload"
        private const val PREFS_NAME = "hillview_upload_prefs"
        private const val PREF_SERVER_URL = "server_url"

        // Foreground service constants
        private const val NOTIFICATION_ID = 2001
        private const val CHANNEL_ID = "photo_upload_foreground"
        const val ACTION_START_UPLOAD = "start_upload"
        const val ACTION_STOP_UPLOAD = "stop_upload"
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(100, TimeUnit.SECONDS)
        .writeTimeout(300, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .build()

    private val prefs: SharedPreferences by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    private val authManager by lazy { AuthenticationManager(this) }
    private val clientCrypto by lazy { ClientCryptoManager(this) }
    private val notificationHelper by lazy { NotificationHelper(this) }

    // Service-related properties
    private val binder = LocalBinder()
    private var isUploading = false

    inner class LocalBinder : Binder() {
        fun getService(): SecureUploadManager = this@SecureUploadManager
    }

    data class UploadAuthorizationResponse(
        val upload_jwt: String,
        val photo_id: String,
        val expires_at: String,
        val worker_url: String,
        val upload_authorized_at: Long  // Unix timestamp when upload was authorized
    )



	private suspend fun doWorkInternal(): Result {
        try {
            val triggerSource = inputData.getString("trigger_source") ?: "unknown"
            Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "doWork - starting unified upload processing (triggered by: $triggerSource)")

            // For scheduled runs, scan for new photos first // we want to avoid this when invoked just to upload currently captured photo
            if (triggerSource == "scheduled") {
                Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Scheduled run detected - scanning for new photos")
                scanForNewPhotos()
            }

            // Process photos one at a time with validation on each iteration

            val seen = mutableSetOf<String>()

            while (true) {
                // Check auto-upload setting on each iteration
                val prefs = applicationContext.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
                val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)

                if (!autoUploadEnabled) {
                    Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Auto upload disabled, stopping upload work")
                    break
                }

                // sleep a bit
                Thread.sleep(500L)

                // Get next photo to upload (pending priority over failed)
                val photo = photoDao.getNextPhotoForUpload(seen)
                if (photo == null) {
                    Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "No more photos to upload")
                    break
                }

				seen.add(photo.id);

                Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Next photo to process: ${photo.filename} (status: ${photo.uploadStatus})")

                // For failed uploads, check if enough time has elapsed for retry
                if (photo.uploadStatus == "failed") {
                    val timeSinceLastAttempt = System.currentTimeMillis() - photo.lastUploadAttempt
                    val requiredWaitTime = calculateBackoffTime(photo.retryCount)

                    if (timeSinceLastAttempt < requiredWaitTime) {
                        Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Skipping retry for ${photo.filename} - not enough time elapsed")
                        continue
                    }
                }

                // Validate auth token on each iteration
                val authToken = authManager.getValidToken()
                if (authToken == null) {
                    Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "🔐 No valid auth token available, stopping upload work")
                    break
                }

                // Process this photo
                try {
                    if (!validatePhotoForUpload(photo)) {
                        continue
                    }

                    val action = if (photo.uploadStatus == "failed") "retry" else "upload"
                    Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Attempting $action for ${photo.filename} with hash: ${photo.fileHash}")

                    // Mark as uploading to prevent parallel processing
                    photoDao.updateUploadStatus(photo.id, "uploading", 0L)

                    val success = secureUploadManager.secureUploadPhoto(photo)

                    if (success) {
                        Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "✅ Successfully ${action}ed ${photo.filename}")
                        photoDao.updateUploadStatus(photo.id, "completed", System.currentTimeMillis())
                    } else {
                        Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "❌ Failed to $action ${photo.filename}")
                        photoDao.updateUploadFailure(
                            photo.id,
                            "failed",
                            photo.retryCount + 1,
                            System.currentTimeMillis(),
                            "$action failed"
                        )
                    }

                } catch (e: Exception) {
                    val action = if (photo.uploadStatus == "failed") "retry" else "upload"
                    Log.e(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "💥 Error during $action for ${photo.filename}", e)
                    photoDao.updateUploadFailure(
                        photo.id,
                        "failed",
                        photo.retryCount + 1,
                        System.currentTimeMillis(),
                        e.message ?: "Unknown error"
                    )
                }
            }

            Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Photo upload worker completed successfully")
            return Result.success()

        } catch (e: Exception) {
            Log.e(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Photo upload worker failed", e)
            return Result.retry()
        }
    }


    private fun scanForNewPhotos() {
        Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Scanning for new photos")

        val directories = getPhotoDirectories()
        var newPhotosFound = 0
        var scanErrors = 0

        for (directory in directories) {
            if (!directory.exists()) {
                Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Directory does not exist: ${directory.path}")
                continue
            }

            val imageFiles = directory.listFiles { file ->
                file.isFile && file.extension.lowercase() in listOf("jpg", "jpeg", "png", "webp")
            } ?: continue

            Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Found ${imageFiles.size} image files in ${directory.path}")

            for (file in imageFiles) {
                try {

                	Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Processing file: ${file.path}")

                    // Calculate file hash for duplicate detection
                    val fileHash = PhotoUtils.calculateFileHash(file)
                    if (fileHash == null) {
                        Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Failed to calculate hash for ${file.path}")
                        scanErrors++
                        continue
                    }

                    // Check for duplicates by path or hash
                    val existingByPath = photoDao.getPhotoByPath(file.path)
                    val existingByHash = photoDao.getPhotoByHash(fileHash)

                    if (existingByPath != null || existingByHash != null) {
                        // Photo already exists, skip
                        continue
                    }

                    // Create metadata for new photo with EXIF data
                    val photoEntity = createPhotoEntityFromFile(file, fileHash)
                    photoDao.insertPhoto(photoEntity)
                    newPhotosFound++
                    Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Added new photo to database: ${file.name}")

                } catch (e: Exception) {
                    Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Failed to process photo ${file.path}: ${e.message}")
                    scanErrors++
                }

                Log.w(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "loop..");
            }
        }

        Log.d(cz.hillview.plugin.PhotoUploadWorker.Companion.TAG, "Scan complete. Added $newPhotosFound new photos, $scanErrors errors")
    }



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
            val date = Date(photo.capturedAt)
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }.format(date)
        } catch (e: Exception) {
            null
        }

        // Get client key ID for authorization
        val keyInfo = clientCrypto.getPublicKeyInfo()
            ?: throw Exception("Failed to get client key info - ensure crypto keys are available")

        val json = JSONObject().apply {
            put("filename", photo.filename)
            put("file_size", photo.fileSize)
            put("content_type", contentType)
            put("file_md5", photo.fileHash)  // MD5 hash for duplicate detection
            put("client_key_id", keyInfo.keyId)  // Key ID that will be used for signing
            put("description", "")  // Could be made configurable
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

        try {
            client.newCall(httpRequest).execute().use { response ->
                if (!response.isSuccessful) {
                    val error = response.body?.string() ?: "Unknown error"
                    throw Exception("Upload authorization failed: ${response.code} - $error")
                }

                val responseJson = JSONObject(response.body!!.string())

                // Check if this is a duplicate file detection response
                if (responseJson.optBoolean("duplicate", false)) {
                    val duplicateMessage = responseJson.optString("message", "This file has already been uploaded")
                    Log.i(TAG, "Duplicate file detected for ${photo.filename}: $duplicateMessage")

                    // Mark the local photo as completed since it already exists on the server
                    val currentTime = System.currentTimeMillis()
                    val dao = PhotoDatabase.getDatabase(this).photoDao()
                    dao.updateUploadStatus(photo.id, "completed", currentTime)

                    // Return a special response indicating duplicate was handled
                    throw DuplicateFileException("Duplicate file successfully handled: $duplicateMessage")
                }

                return UploadAuthorizationResponse(
                    upload_jwt = responseJson.getString("upload_jwt"),
                    photo_id = responseJson.getString("photo_id"),
                    expires_at = responseJson.getString("expires_at"),
                    worker_url = responseJson.getString("worker_url"),
                    upload_authorized_at = responseJson.getLong("upload_authorized_at")
                )
            }
        } catch (e: java.net.ConnectException) {
            throw Exception("❌ Cannot reach API server: ${e.message}")
        } catch (e: java.net.SocketTimeoutException) {
            throw Exception("⏱️ API server timeout: ${e.message}")
        } catch (e: java.net.UnknownHostException) {
            throw Exception("🔍 Cannot resolve API server hostname: ${e.message}")
        }
    }

    /**
     * Generate client signature for upload using authorization timestamp
     */
    private fun generateClientSignature(photoId: String, filename: String, authTimestamp: Long): SignatureData? {
        return clientCrypto.signUploadData(photoId, filename, authTimestamp)
    }

    /**
     * Upload file to worker with JWT and client signature
     */
    private suspend fun uploadToWorker(
        file: File,
        filename: String,
        uploadJwt: String,
        signature: String,
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
            .addFormDataPart("client_signature", signature)
            .build()

        val request = Request.Builder()
            .url("$workerUrl/upload")
            .addHeader("Authorization", "Bearer $uploadJwt")
            .post(requestBody)
            .build()

        Log.d(TAG, "Uploading $filename to worker $workerUrl")

        try {
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
                    Log.e(TAG, "❌ Secure upload $filename failed: $errorMsg")
                }

                return success
            }
        } catch (e: java.net.ConnectException) {
            Log.e(TAG, "❌ Cannot reach worker server for $filename: ${e.message}")
            return false
        } catch (e: java.net.SocketTimeoutException) {
            Log.e(TAG, "⏱️ Worker upload timeout for $filename: ${e.message}")
            return false
        } catch (e: java.net.UnknownHostException) {
            Log.e(TAG, "🔍 Cannot resolve worker hostname for $filename: ${e.message}")
            return false
        } catch (e: IOException) {
            Log.e(TAG, "📡 Network I/O error during worker upload for $filename: ${e.message}")
            return false
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
            Log.d(TAG, "Upload authorized, response: $authResponse")

            // Step 2: Generate client signature using authorization timestamp
            val signatureData = generateClientSignature(authResponse.photo_id, photo.filename, authResponse.upload_authorized_at)
            if (signatureData == null) {
                Log.e(TAG, "Failed to generate client signature for: ${photo.filename}")
                return@withContext false
            }

            Log.d(TAG, "Client signature generated for: ${photo.filename} with key ${signatureData.keyId}")

            // Step 3: Upload to worker (using worker_url from auth response)
            val uploadSuccess = uploadToWorker(
                file,
                photo.filename,
                authResponse.upload_jwt,
                signatureData.signature,
                authResponse.worker_url
            )

            return@withContext uploadSuccess

        } catch (e: DuplicateFileException) {
            Log.i(TAG, "✅ Duplicate file handled for ${photo.filename}: ${e.message}")
            return@withContext true
        } catch (e: java.net.ConnectException) {
            Log.w(TAG, "🌐 Connection failed for ${photo.filename}: Server unreachable (${e.message})")
            return@withContext false
        } catch (e: java.net.SocketTimeoutException) {
            Log.w(TAG, "⏱️ Upload timeout for ${photo.filename}: ${e.message}")
            return@withContext false
        } catch (e: java.net.UnknownHostException) {
            Log.w(TAG, "🔍 DNS lookup failed for ${photo.filename}: ${e.message}")
            return@withContext false
        } catch (e: IOException) {
            Log.w(TAG, "📡 Network I/O error for ${photo.filename}: ${e.message}")
            return@withContext false
        } catch (e: Exception) {
            Log.e(TAG, "💥 Unexpected error in secure upload: ${photo.filename}", e)
            return@withContext false
        }
    }

    private fun getServerUrl(): String? {
        return prefs.getString(PREF_SERVER_URL, null)
    }

    // Service lifecycle methods
    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "SecureUploadManager service created")
        createNotificationChannel()
    }

    override fun onBind(intent: Intent): IBinder {
        return binder
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_UPLOAD -> {
                val triggerSource = intent.getStringExtra("trigger_source") ?: "unknown"
                startForegroundUploadProcess(triggerSource)
            }
            ACTION_STOP_UPLOAD -> {
                stopForegroundUploadProcess()
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "SecureUploadManager service destroyed")
        isUploading = false
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Photo Upload Service",
                android.app.NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Shows upload progress for photos"
                setShowBadge(false)
                enableVibration(false)
                setSound(null, null)
            }

            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundUploadProcess(triggerSource: String = "unknown") {
        if (isUploading) {
            Log.d(TAG, "Upload already in progress")
            return
        }

        Log.d(TAG, "Starting foreground upload service (triggered by: $triggerSource)")
        isUploading = true

        val notification = createUploadNotification("Starting photo uploads...")
        startForeground(NOTIFICATION_ID, notification)

        // Store trigger source for later use in upload logic
        // TODO: Implement actual upload processing based on triggerSource
        // For "scheduled" triggers, should scan for new photos
        // For "manual" triggers, should process pending uploads only
    }

    private fun stopForegroundUploadProcess() {
        Log.d(TAG, "Stopping foreground upload service")
        isUploading = false
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    fun updateUploadProgress(message: String) {
        if (isUploading) {
            val notification = createUploadNotification(message)
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            notificationManager.notify(NOTIFICATION_ID, notification)
        }
    }

    private fun createUploadNotification(message: String): Notification {
        val intent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val stopIntent = Intent(this, SecureUploadManager::class.java).apply {
            action = ACTION_STOP_UPLOAD
        }
        val stopPendingIntent = PendingIntent.getService(
            this,
            1,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Uploading Photos")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentIntent(pendingIntent)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Stop",
                stopPendingIntent
            )
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
    }

}
