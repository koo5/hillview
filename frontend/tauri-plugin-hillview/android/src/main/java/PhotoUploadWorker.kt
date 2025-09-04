package cz.hillview.plugin

import android.content.Context
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.Data
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.security.MessageDigest

class PhotoUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "🢄PhotoUploadWorker"
        const val WORK_NAME = "photo_upload_work"
        const val KEY_AUTO_UPLOAD_ENABLED = "auto_upload_enabled"
    }

    private val database = PhotoDatabase.getDatabase(applicationContext)
    private val photoDao = database.photoDao()
    private val secureUploadManager = SecureUploadManager(applicationContext)
    private val authManager = AuthenticationManager(applicationContext)

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Starting photo upload worker")

            // Read current auto-upload setting from SharedPreferences (not stale inputData)
            val prefs = applicationContext.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)
            Log.d(TAG, "Auto upload enabled (from SharedPrefs): $autoUploadEnabled")

            // First scan for new photos
            scanForNewPhotos()

            // Then process upload queue if auto upload is enabled
            if (autoUploadEnabled) {
                // Get valid auth token (automatically refreshes if needed)
                val authToken = authManager.getValidToken()
                if (authToken == null) {
                    Log.w(TAG, "🔐 No valid auth token available (refresh failed or no refresh token), skipping upload work")
                    return@withContext Result.success()
                }

                Log.d(TAG, "🔐 Valid auth token obtained, proceeding with uploads")
                processUploadQueue()
                retryFailedUploads()
            }

            Log.d(TAG, "Photo upload worker completed successfully")
            Result.success()

        } catch (e: Exception) {
            Log.e(TAG, "Photo upload worker failed", e)
            Result.retry()
        }
    }

    private fun scanForNewPhotos() {
        Log.d(TAG, "Scanning for new photos")

        val directories = getPhotoDirectories()
        var newPhotosFound = 0
        var scanErrors = 0

        for (directory in directories) {
            if (!directory.exists()) {
                Log.d(TAG, "Directory does not exist: ${directory.path}")
                continue
            }

            val imageFiles = directory.listFiles { file ->
                file.isFile && file.extension.lowercase() in listOf("jpg", "jpeg", "png", "webp")
            } ?: continue

            Log.d(TAG, "Found ${imageFiles.size} image files in ${directory.path}")

            for (file in imageFiles) {
                try {

                	Log.w(TAG, "Processing file: ${file.path}")

                    // Calculate file hash for duplicate detection
                    val fileHash = calculateFileHash(file)
                    if (fileHash == null) {
                        Log.w(TAG, "Failed to calculate hash for ${file.path}")
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
                    Log.d(TAG, "Added new photo to database: ${file.name}")

                } catch (e: Exception) {
                    Log.w(TAG, "Failed to process photo ${file.path}: ${e.message}")
                    scanErrors++
                }

                Log.w(TAG, "loop..");
            }
        }

        Log.d(TAG, "Scan complete. Added $newPhotosFound new photos, $scanErrors errors")
    }

    private suspend fun processUploadQueue() {
        Log.d(TAG, "Processing upload queue")

        val pendingUploads = photoDao.getPendingUploads()
        Log.d(TAG, "Found ${pendingUploads.size} pending uploads")

        for (photo in pendingUploads) {
            try {
                // Check if file still exists
                if (!File(photo.path).exists()) {
                    Log.w(TAG, "Photo file no longer exists: ${photo.path}")
                    photoDao.updateUploadStatus(photo.id, "failed", 0L)
                    continue
                }

                // Update status to uploading
                photoDao.updateUploadStatus(photo.id, "uploading", 0L)

                // Attempt upload
                val success = secureUploadManager.secureUploadPhoto(photo)

                if (success) {
                    Log.d(TAG, "Successfully uploaded photo: ${photo.filename}")
                    photoDao.updateUploadStatus(photo.id, "completed", System.currentTimeMillis())
                } else {
                    Log.w(TAG, "Failed to upload photo: ${photo.filename}")
                    photoDao.updateUploadFailure(
                        photo.id,
                        "failed",
                        photo.retryCount + 1,
                        System.currentTimeMillis(),
                        "Upload failed"
                    )
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error uploading photo ${photo.filename}", e)
                photoDao.updateUploadFailure(
                    photo.id,
                    "failed",
                    photo.retryCount + 1,
                    System.currentTimeMillis(),
                    e.message ?: "Unknown error"
                )
            }
        }
    }

    private suspend fun retryFailedUploads() {
        Log.d(TAG, "Checking for failed uploads to retry")

        val failedUploads = photoDao.getFailedUploadsForRetry()
        Log.d(TAG, "Found ${failedUploads.size} failed uploads eligible for retry")

        for (photo in failedUploads) {
            // Exponential backoff: wait longer between retries
            val timeSinceLastAttempt = System.currentTimeMillis() - photo.lastUploadAttempt
            val requiredWaitTime = calculateBackoffTime(photo.retryCount)

            if (timeSinceLastAttempt < requiredWaitTime) {
                Log.d(TAG, "Skipping retry for ${photo.filename} - not enough time elapsed")
                continue
            }

            try {
                if (!File(photo.path).exists()) {
                    Log.w(TAG, "Photo file no longer exists: ${photo.path}")
                    continue
                }

                photoDao.updateUploadStatus(photo.id, "uploading", 0L)

                val success = secureUploadManager.secureUploadPhoto(photo)

                if (success) {
                    Log.d(TAG, "Successfully retried upload for photo: ${photo.filename}")
                    photoDao.updateUploadStatus(photo.id, "completed", System.currentTimeMillis())
                } else {
                    Log.w(TAG, "Retry failed for photo: ${photo.filename}")
                    photoDao.updateUploadFailure(
                        photo.id,
                        "failed",
                        photo.retryCount + 1,
                        System.currentTimeMillis(),
                        "Retry failed"
                    )
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error retrying upload for photo ${photo.filename}", e)
                photoDao.updateUploadFailure(
                    photo.id,
                    "failed",
                    photo.retryCount + 1,
                    System.currentTimeMillis(),
                    e.message ?: "Unknown error"
                )
            }
        }
    }

    private fun getPhotoDirectories(): List<File> {
        val directories = mutableListOf<File>()

        // Get external storage path
        //val externalStorage = System.getenv("EXTERNAL_STORAGE") ?: "/storage/emulated/0"
        val externalStorage = "/storage/emulated/0"
        val picturesDir = File(externalStorage, "Pictures")

        // Add Hillview directories in Pictures (where photos are actually saved)
        directories.add(File(picturesDir, "Hillview"))    // /storage/emulated/0/Pictures/Hillview
        directories.add(File(picturesDir, ".Hillview"))   // /storage/emulated/0/Pictures/.Hillview (hidden)

        Log.d(TAG, "Scanning photo directories: ${directories.map { it.path }}")
        return directories
    }

    private fun createPhotoEntityFromFile(file: File, fileHash: String): PhotoEntity {
        var latitude = 0.0
        var longitude = 0.0
        var altitude = 0.0
        var bearing = 0.0
        var width = 0
        var height = 0
        var timestamp = file.lastModified()

            try {
                // Extract EXIF data
                val exif = ExifInterface(file.path)

                // Get GPS coordinates with multiple format support
                val coords = extractGpsCoordinates(exif)
                latitude = coords.first
                longitude = coords.second

                // Get altitude with multiple format support
                altitude = extractAltitude(exif) ?: 0.0

                // Get bearing/direction with multiple format support
                bearing = extractBearing(exif) ?: 0.0

                // Get image dimensions from multiple sources
                val dimensions = extractImageDimensions(exif)
                width = dimensions.first
                height = dimensions.second

                // Get timestamp from multiple EXIF fields
                timestamp = extractTimestamp(exif, file.lastModified())

                Log.i(TAG, "Extracted EXIF data for ${file.name}: lat=$latitude, lng=$longitude, alt=$altitude, bearing=$bearing, ${width}x${height}")

        } catch (e: IOException) {
            Log.w(TAG, "Failed to read EXIF data from ${file.path}: ${e.message}")
        }

        return PhotoEntity(
                id = "device_${System.currentTimeMillis()}_${fileHash.take(8)}",
                filename = file.name,
                path = file.path,
                latitude = latitude,
                longitude = longitude,
                altitude = altitude,
                bearing = bearing,
                timestamp = timestamp,
                accuracy = 0.0, // Not available from EXIF
                width = width,
                height = height,
                fileSize = file.length(),
                createdAt = System.currentTimeMillis(),
                uploadStatus = "pending",
            autoUploadEnabled = true,
            fileHash = fileHash
        )
    }

    private fun calculateFileHash(file: File): String? {
        return try {
            val digest = MessageDigest.getInstance("MD5")
            file.inputStream().use { fis ->
                val buffer = ByteArray(8192)
                var bytesRead: Int
                while (fis.read(buffer).also { bytesRead = it } != -1) {
                    digest.update(buffer, 0, bytesRead)
                }
            }
            digest.digest().joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to calculate hash for ${file.path}", e)
            null
        }
    }

    private fun extractGpsCoordinates(exif: ExifInterface): Pair<Double, Double> {
        var latitude: Double
        var longitude: Double

        // Method 1: Use built-in getLatLong (most reliable)
        val latLong = FloatArray(2)
        @Suppress("DEPRECATION")
        if (exif.getLatLong(latLong)) {
            latitude = latLong[0].toDouble()
            longitude = latLong[1].toDouble()
            Log.v(TAG, "GPS coordinates from getLatLong: $latitude, $longitude")
            return Pair(latitude, longitude)
        }

        // Method 2: Manual parsing of GPS tags (for our own format and others)
        try {
            val latRef = exif.getAttribute(ExifInterface.TAG_GPS_LATITUDE_REF)
            val latStr = exif.getAttribute(ExifInterface.TAG_GPS_LATITUDE)
            val lonRef = exif.getAttribute(ExifInterface.TAG_GPS_LONGITUDE_REF)
            val lonStr = exif.getAttribute(ExifInterface.TAG_GPS_LONGITUDE)

            if (latStr != null && lonStr != null) {
                latitude = parseGpsCoordinate(latStr)
                longitude = parseGpsCoordinate(lonStr)

                // Apply hemisphere corrections
                if (latRef == "S") latitude = -latitude
                if (lonRef == "W") longitude = -longitude

                Log.v(TAG, "GPS coordinates from manual parsing: $latitude, $longitude")
                return Pair(latitude, longitude)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to manually parse GPS coordinates: ${e.message}")
        }

        return Pair(0.0, 0.0)
    }

    private fun parseGpsCoordinate(coordinate: String): Double {
        // Handle different coordinate formats:
        // "40/1,26/1,4610/100" (degrees, minutes, seconds as rationals)
        // "40.123456" (decimal degrees)
        // "40,26.076833" (degrees, decimal minutes)

        return try {
            if (coordinate.contains("/")) {
                // Rational format: "deg/1,min/1,sec/100"
                val parts = coordinate.split(",")
                var degrees = 0.0
                var minutes = 0.0
                var seconds = 0.0

                if (parts.isNotEmpty()) {
                    val degParts = parts[0].split("/")
                    if (degParts.size == 2) {
                        degrees = degParts[0].toDouble() / degParts[1].toDouble()
                    }
                }

                if (parts.size > 1) {
                    val minParts = parts[1].split("/")
                    if (minParts.size == 2) {
                        minutes = minParts[0].toDouble() / minParts[1].toDouble()
                    }
                }

                if (parts.size > 2) {
                    val secParts = parts[2].split("/")
                    if (secParts.size == 2) {
                        seconds = secParts[0].toDouble() / secParts[1].toDouble()
                    }
                }

                degrees + minutes / 60.0 + seconds / 3600.0
            } else {
                // Decimal format
                coordinate.toDouble()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse GPS coordinate: $coordinate")
            0.0
        }
    }

    private fun extractAltitude(exif: ExifInterface): Double? {
        return try {
            // Method 1: Use built-in getAltitude
            val altitude = exif.getAltitude(Double.NaN)
            if (!altitude.isNaN()) {
                Log.v(TAG, "Altitude from getAltitude: $altitude")
                return altitude
            }

            // Method 2: Manual parsing
            val altitudeRef = exif.getAttribute(ExifInterface.TAG_GPS_ALTITUDE_REF)
            val altitudeStr = exif.getAttribute(ExifInterface.TAG_GPS_ALTITUDE)

            if (altitudeStr != null) {
                val altValue = if (altitudeStr.contains("/")) {
                    val parts = altitudeStr.split("/")
                    if (parts.size == 2) {
                        parts[0].toDouble() / parts[1].toDouble()
                    } else {
                        altitudeStr.toDouble()
                    }
                } else {
                    altitudeStr.toDouble()
                }

                // Apply reference (0 = above sea level, 1 = below sea level)
                val finalAltitude = if (altitudeRef == "1") -altValue else altValue
                Log.v(TAG, "Altitude from manual parsing: $finalAltitude")
                finalAltitude
            } else {
                null
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to extract altitude: ${e.message}")
            null
        }
    }

    private fun extractBearing(exif: ExifInterface): Double? {
        return try {
            // Try multiple bearing/direction tags
            val bearingTags = listOf(
                ExifInterface.TAG_GPS_IMG_DIRECTION,      // Image direction
                ExifInterface.TAG_GPS_DEST_BEARING,       // Destination bearing (our format)
                "GPSImgDirection",                        // Alternative tag name
                "GPSDestBearing"                          // Alternative tag name
            )

            for (tag in bearingTags) {
                val bearingStr = exif.getAttribute(tag)
                if (bearingStr != null) {
                    val bearing = if (bearingStr.contains("/")) {
                        val parts = bearingStr.split("/")
                        if (parts.size == 2) {
                            parts[0].toDouble() / parts[1].toDouble()
                        } else {
                            bearingStr.toDouble()
                        }
                    } else {
                        bearingStr.toDouble()
                    }

                    Log.v(TAG, "Bearing from $tag: $bearing")
                    return bearing
                }
            }

            null
        } catch (e: Exception) {
            Log.w(TAG, "Failed to extract bearing: ${e.message}")
            null
        }
    }

    private fun extractImageDimensions(exif: ExifInterface): Pair<Int, Int> {
        // Try multiple dimension tags in order of preference
        val widthTags = listOf(
            ExifInterface.TAG_IMAGE_WIDTH,
            ExifInterface.TAG_PIXEL_X_DIMENSION,
            "ImageWidth",
            "PixelXDimension"
        )

        val heightTags = listOf(
            ExifInterface.TAG_IMAGE_LENGTH,
            ExifInterface.TAG_PIXEL_Y_DIMENSION,
            "ImageLength",
            "PixelYDimension"
        )

        var width = 0
        var height = 0

        for (tag in widthTags) {
            val w = exif.getAttributeInt(tag, 0)
            if (w > 0) {
                width = w
                break
            }
        }

        for (tag in heightTags) {
            val h = exif.getAttributeInt(tag, 0)
            if (h > 0) {
                height = h
                break
            }
        }

        Log.v(TAG, "Image dimensions: ${width}x${height}")
        return Pair(width, height)
    }

    private fun extractTimestamp(exif: ExifInterface, fallbackTime: Long): Long {
        // Try multiple timestamp formats in order of preference
        val timestampTags = listOf(
            ExifInterface.TAG_DATETIME_ORIGINAL,    // Original capture time
            ExifInterface.TAG_DATETIME_DIGITIZED,   // Digitized time
            ExifInterface.TAG_DATETIME,             // File modification time
            "DateTimeOriginal",
            "DateTimeDigitized",
            "DateTime"
        )

        val dateFormats = listOf(
            "yyyy:MM:dd HH:mm:ss",      // Standard EXIF format
            "yyyy-MM-dd HH:mm:ss",      // ISO format
            "yyyy:MM:dd'T'HH:mm:ss",    // Mixed format
            "yyyy-MM-dd'T'HH:mm:ss"     // ISO with T separator
        )

        for (tag in timestampTags) {
            val dateTimeStr = exif.getAttribute(tag)
            if (dateTimeStr != null) {
                for (format in dateFormats) {
                    try {
                        val sdf = java.text.SimpleDateFormat(format, java.util.Locale.US)
                        val date = sdf.parse(dateTimeStr)
                        if (date != null) {
                            Log.v(TAG, "Timestamp from $tag: $dateTimeStr -> ${date.time}")
                            return date.time
                        }
                    } catch (e: Exception) {
                        // Try next format
                    }
                }
            }
        }

        Log.v(TAG, "Using fallback timestamp: $fallbackTime")
        return fallbackTime
    }

    private fun calculateBackoffTime(retryCount: Int): Long {
        // Exponential backoff: 1min, 2min, 4min, 8min, 16min
        val baseDelay = 60_000L // 1 minute
        return baseDelay * (1L shl minOf(retryCount, 4))
    }
}
