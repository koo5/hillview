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
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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
import androidx.work.ListenableWorker
import androidx.exifinterface.media.ExifInterface

// Database imports for duplicate handling
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoEntity

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
class PhotoUploadLogic(private val context: Context) {
	private val database: PhotoDatabase = PhotoDatabase.getDatabase(context)
	private val photoDao = database.photoDao()

	companion object {
		private const val TAG = "🢄Upload"
		private const val PREFS_NAME = "hillview_upload_prefs"
		private const val PREF_SERVER_URL = "server_url"

		// Foreground service constants
		private const val NOTIFICATION_ID = 2001
		private const val CHANNEL_ID = "photo_upload_foreground"
		const val ACTION_START_UPLOAD = "start_upload"
		const val ACTION_STOP_UPLOAD = "stop_upload"

		private val workerMutex = Mutex()
	}

	private val client = OkHttpClient.Builder()
		.connectTimeout(100, TimeUnit.SECONDS)
		.writeTimeout(300, TimeUnit.SECONDS)
		.readTimeout(300, TimeUnit.SECONDS)
		.build()

	private val prefs: SharedPreferences by lazy { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
	private val authManager by lazy { AuthenticationManager(context) }
	private val clientCrypto by lazy { ClientCryptoManager(context) }
	private val notificationHelper by lazy { NotificationHelper(context) }



	data class UploadAuthorizationResponse(
		val upload_jwt: String,
		val photo_id: String,
		val expires_at: String,
		val worker_url: String,
		val upload_authorized_at: Long  // Unix timestamp when upload was authorized
	)


	suspend fun doWorkInternal(triggerSource: String, photoId: String?): androidx.work.ListenableWorker.Result {
		workerMutex.withLock {

			try {

				Log.d(
					TAG,
					"doWork - starting unified upload processing (triggered by: $triggerSource), specific photo ID: $photoId"
				)

				// For scheduled runs, scan for new photos first // we want to avoid this when invoked just to upload currently captured photo
				if (triggerSource == "scheduled") {
					Log.d(
						TAG,
						"Scheduled run detected - scanning for new photos"
					)
					scanForNewPhotos()
				}

				// Process photos one at a time with validation on each iteration

				val seen = mutableSetOf<String>()

				while (true) {
					// Check auto-upload setting on each iteration
					val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
					val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)

					if (!autoUploadEnabled && !photoId.isNullOrEmpty()) {
						Log.d(
							TAG,
							"Auto upload disabled, stopping upload work"
						)
						break
					}

					// sleep a bit
					Thread.sleep(100L)

					// Get next photo to upload (pending priority over failed)
					val photo: PhotoEntity?

					if (!photoId.isNullOrEmpty())
					{
						// avoid completed photos
						photo = photoDao.getPhotoById(photoId)
					}
					else
					{
						photo = photoDao.getNextPhotoForUpload(seen, System.currentTimeMillis() - 1000 * 60 * 10)
					}

					if (photo == null) {
						Log.d(TAG, "No more photos to upload")
						break
					}

					seen.add(photo.id);

					Log.d(
						TAG,
						"Next photo to process: ${photo.filename} (status: ${photo.uploadStatus})"
					)

					// For failed uploads, check if enough time has elapsed for retry
					if (photo.uploadStatus == "failed") {
						val timeSinceLastAttempt = System.currentTimeMillis() - photo.lastUploadAttempt
						val requiredWaitTime = calculateBackoffTime(photo.retryCount)

						if (timeSinceLastAttempt < requiredWaitTime) {
							Log.d(
								TAG,
								"Skipping retry for ${photo.filename} - not enough time elapsed"
							)
							continue
						}
					}

					// Validate auth token on each iteration
					val authToken = authManager.getValidToken()
					if (authToken == null) {
						Log.w(
							TAG,
							"🔐 No valid auth token available, stopping upload work"
						)
						break
					}

					// Process this photo
					try {
						if (!validatePhotoForUpload(photo)) {
							continue
						}

						val action = if (photo.uploadStatus == "failed") "retry" else "upload"
						Log.d(
							TAG,
							"Attempting $action for ${photo.filename} with hash: ${photo.fileHash}"
						)

						photoDao.updateUploadStatus(photo.id, "uploading", System.currentTimeMillis())

						val success = secureUploadPhoto(photo)

						if (success) {
							Log.d(
								TAG,
								"✅ Successfully ${action}ed ${photo.filename}"
							)
							photoDao.updateUploadStatus(photo.id, "completed", System.currentTimeMillis())
						} else {
							Log.w(
								TAG,
								"❌ Failed to $action ${photo.filename}"
							)
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
						Log.e(
							TAG,
							"💥 Error during $action for ${photo.filename}",
							e
						)
						photoDao.updateUploadFailure(
							photo.id,
							"failed",
							photo.retryCount + 1,
							System.currentTimeMillis(),
							e.message ?: "Unknown error"
						)
					}
				}

				Log.d(TAG, "Photo upload worker completed successfully")
				return ListenableWorker.Result.success()

			} catch (e: Exception) {
				Log.e(TAG, "Photo upload worker failed", e)
				return ListenableWorker.Result.retry()
			}
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

			Log.d(
				TAG,
				"Found ${imageFiles.size} image files in ${directory.path}"
			)

			for (file in imageFiles) {
				try {

					Log.w(TAG, "Processing file: ${file.path}")

					// Calculate file hash for duplicate detection
					val fileHash = PhotoUtils.calculateFileHash(file)
					if (fileHash == null) {
						Log.w(
							TAG,
							"Failed to calculate hash for ${file.path}"
						)
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
					Log.d(
						TAG,
						"Added new photo to database: ${file.name}"
					)

				} catch (e: Exception) {
					Log.w(
						TAG,
						"Failed to process photo ${file.path}: ${e.message}"
					)
					scanErrors++
				}

				Log.w(TAG, "loop..");
			}
		}

		Log.d(
			TAG,
			"Scan complete. Added $newPhotosFound new photos, $scanErrors errors"
		)
	}


	suspend fun secureUploadPhoto(photo: PhotoEntity): Boolean = withContext(Dispatchers.IO) {
		try {
			Log.d(TAG, "Starting secure upload for photo: ${photo.filename}")

			if (!PhotoUtils.pathExists(context, photo.path)) {
				Log.e(TAG, "Photo file does not exist: ${photo.path}")
				return@withContext false
			}

			// Step 1: Request upload authorization (includes PhotoEntity geolocation)
			// Note: Uses photo.fileSize from database, doesn't need to read file yet
			val authResponse = requestUploadAuthorization(photo)
			Log.d(TAG, "Upload authorized, response: $authResponse")

			// Step 2: Generate client signature using authorization timestamp
			val signatureData =
				generateClientSignature(authResponse.photo_id, photo.filename, authResponse.upload_authorized_at)
			if (signatureData == null) {
				Log.e(TAG, "Failed to generate client signature for: ${photo.filename}")
				return@withContext false
			}

			Log.d(TAG, "Client signature generated for: ${photo.filename} with key ${signatureData.keyId}")

			// Step 3: Upload to worker (using worker_url from auth response)
			// Read file bytes only now, when we actually need them
			val fileBytes = PhotoUtils.readBytesFromPath(context, photo.path)
			if (fileBytes == null) {
				Log.e(TAG, "Failed to read photo file for upload: ${photo.path}")
				return@withContext false
			}

			val uploadSuccess = uploadToWorker(
				fileBytes,
				photo.filename,
				authResponse.upload_jwt,
				signatureData.signature,
				authResponse.worker_url,
				photo.id
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


	/**
	 * Request upload authorization from API server using PhotoEntity data
	 */
	private suspend fun requestUploadAuthorization(photo: PhotoEntity): UploadAuthorizationResponse {
		val serverUrl = getServerUrl() ?: throw Exception("Server URL not configured")
		val authToken = authManager.getValidToken() ?: throw Exception("No valid auth token")
		val contentType = PhotoUtils.getContentType(photo.filename)

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
					val dao = photoDao
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
		fileBytes: ByteArray,
		filename: String,
		uploadJwt: String,
		signature: String,
		workerUrl: String,
		photoId: String
	): Boolean {
		val mediaType = PhotoUtils.getContentType(filename).toMediaType()

		val requestBody = MultipartBody.Builder()
			.setType(MultipartBody.FORM)
			.addFormDataPart(
				"file",
				filename,
				fileBytes.toRequestBody(mediaType)
			)
			.addFormDataPart("client_signature", signature)
			.build()

		val request = Request.Builder()
			.url("$workerUrl/upload")
			.addHeader("Authorization", "Bearer $uploadJwt")
			.post(requestBody)
			.build()

		Log.d(TAG, "Uploading $filename to worker $workerUrl")

		// Start heartbeat coroutine to update lastUploadAttempt during upload
		val heartbeatJob = CoroutineScope(Dispatchers.IO).launch {
			while (isActive) {
				delay(30_000) // Every 30 seconds
				try {
					val database = PhotoDatabase.getDatabase(context)
					database.photoDao().updateUploadHeartbeat(photoId, System.currentTimeMillis())
					Log.v(TAG, "Updated upload heartbeat for $filename")
				} catch (e: Exception) {
					Log.w(TAG, "Failed to update heartbeat for $filename: ${e.message}")
				}
			}
		}

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
		} finally {
			heartbeatJob.cancel()
		}
	}


	private fun getServerUrl(): String? {
		return prefs.getString(PREF_SERVER_URL, null)
	}



    private fun getPhotoDirectories(): List<File> {
        val directories = mutableListOf<File>()

        // Get external storage path
        //val externalStorage = System.getenv("EXTERNAL_STORAGE") ?: "/storage/emulated/0"
        val externalStorage = "/storage/emulated/0"
        val picturesDir = File(externalStorage, "Pictures")

        // Add Hillview directories in Pictures (where photos are actually saved)
        directories.add(File(picturesDir, "Hillview"))    // /storage/emulated/0/Pictures/Hillview
        //directories.add(File(picturesDir, ".Hillview"))   // /storage/emulated/0/Pictures/.Hillview (hidden)

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
                capturedAt = timestamp,
                accuracy = 0.0, // Not available from EXIF
                width = width,
                height = height,
                fileSize = file.length(),
                createdAt = System.currentTimeMillis(),
                uploadStatus = "pending",
                fileHash = fileHash
        )
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

    private suspend fun validatePhotoForUpload(photo: PhotoEntity): Boolean {
        // Check if file still exists (works for both file paths and content:// URIs)
        if (!PhotoUtils.pathExists(context, photo.path)) {
            Log.w(TAG, "Photo file no longer exists: ${photo.path}, marking as failed")
            photoDao.updateUploadFailure(
                photo.id,
                "failed",
                photo.retryCount + 1,
                System.currentTimeMillis(),
                "File no longer exists"
            )
            return false
        }

        // Validate MD5 hash
        if (photo.fileHash.isEmpty() || photo.fileHash.length != 32 || !photo.fileHash.matches(Regex("[a-fA-F0-9]{32}"))) {
            Log.w(TAG, "Invalid MD5 hash for ${photo.filename}: '${photo.fileHash}' (length: ${photo.fileHash.length})")
            photoDao.updateUploadFailure(
                photo.id,
                "failed",
                photo.retryCount + 1,
                System.currentTimeMillis(),
                "Invalid MD5 hash: ${photo.fileHash}"
            )
            return false
        }

        return true
    }

    private fun calculateBackoffTime(retryCount: Int): Long {
        // Exponential backoff: 1min, 2min, 4min, 8min, 16min, 32min, 1hr, 2hr, 4hr, 8hr, 16hr, 1.3days, 2.6days, 5.2days, 7days (max)
        val baseDelay = 60_000L // 1 minute
        val maxDelay = 7 * 24 * 60 * 60 * 1000L // 7 days in milliseconds
        val exponentialDelay = baseDelay * (1L shl retryCount)
        return minOf(exponentialDelay, maxDelay)
    }


}
