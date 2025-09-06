package cz.hillview.plugin

import android.app.Activity
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import app.tauri.plugin.JSObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.*

class PhotoScanManager(
    private val activity: Activity,
    private val database: PhotoDatabase
) {
    companion object {
        private const val TAG = "PhotoScanManager"
    }

    suspend fun refreshPhotoScan(): JSObject {
        return try {
            val directories = getPhotoDirectories()
            var newPhotosFound = 0
            var scanErrors = 0
            val photoDao = database.photoDao()
            
            for (directory in directories) {
                if (!directory.exists()) {
                    Log.d(TAG, "Directory does not exist: ${directory.path}")
                    continue
                }

                val imageFiles = directory.listFiles { file ->
                    file.isFile && isImageFile(file.name)
                }

                imageFiles?.forEach { file ->
                    try {
                        Log.v(TAG, "Processing file: ${file.path}")
                        
                        // Calculate file hash for duplicate detection
                        val fileHash = calculateFileHash(file)
                        if (fileHash == null) {
                            Log.w(TAG, "❌ Failed to calculate hash for ${file.path}")
                            scanErrors++
                            return@forEach
                        }
                        Log.v(TAG, "✅ File hash calculated: ${fileHash.take(8)}...")

                        // Check if photo already exists in database
                        val existingByPath = photoDao.getPhotoByPath(file.path)
                        val existingByHash = photoDao.getPhotoByHash(fileHash)

                        if (existingByPath != null) {
                            Log.v(TAG, "⏭️ Photo already exists in database by path: ${file.name}")
                            return@forEach
                        }
                        if (existingByHash != null) {
                            Log.v(TAG, "⏭️ Photo already exists in database by hash: ${file.name}")
                            return@forEach
                        }

                        // Create metadata for new photo with EXIF data - this will check GPS validity
                        val photoEntity = createPhotoEntityFromFile(file, fileHash)
                        if (photoEntity == null) {
                            Log.i(TAG, "🚫 Skipping photo without valid GPS data: ${file.name}")
                            return@forEach
                        }

                        photoDao.insertPhoto(photoEntity)
                        newPhotosFound++
                        Log.d(TAG, "📸 New photo added: ${file.name}")

                    } catch (e: Exception) {
                        Log.e(TAG, "❌ Error processing photo ${file.path}: ${e.message}", e)
                        scanErrors++
                    }
                }

                // Also scan subdirectories (like Import20241206_143022)
                directory.listFiles { dir -> dir.isDirectory }?.forEach { subDir ->
                    if (subDir.name.startsWith("Import")) {
                        Log.d(TAG, "Scanning import subdirectory: ${subDir.path}")
                        val subImageFiles = subDir.listFiles { file ->
                            file.isFile && isImageFile(file.name)
                        }
                        
                        subImageFiles?.forEach { file ->
                            try {
                                val fileHash = calculateFileHash(file)
                                if (fileHash != null) {
                                    val existingByPath = photoDao.getPhotoByPath(file.path)
                                    val existingByHash = photoDao.getPhotoByHash(fileHash)

                                    if (existingByPath != null || existingByHash != null) {
                                        return@forEach // Already exists
                                    }

                                    val photoEntity = createPhotoEntityFromFile(file, fileHash)
                                    if (photoEntity != null) {
                                        photoDao.insertPhoto(photoEntity)
                                        newPhotosFound++
                                    }
                                }
                            } catch (e: Exception) {
                                Log.w(TAG, "Failed to process photo ${file.path}", e)
                                scanErrors++
                            }
                        }
                    }
                }
            }

            Log.i(TAG, "📊 Photo scan completed: $newPhotosFound new photos, $scanErrors errors")

            val result = JSObject()
            result.put("photosAdded", newPhotosFound)
            result.put("scanErrors", scanErrors)
            result.put("success", true)
            result
        } catch (e: Exception) {
            Log.e(TAG, "❌ Photo scan failed: ${e.message}", e)
            val result = JSObject()
            result.put("photosAdded", 0)
            result.put("scanErrors", 1)
            result.put("success", false)
            result.put("error", e.message)
            result
        }
    }

    private fun getPhotoDirectories(): List<File> {
        val directories = mutableListOf<File>()
        val externalStorage = "/storage/emulated/0"
        val picturesDir = File(externalStorage, "Pictures")
        
        directories.add(File(picturesDir, "Hillview"))
        directories.add(File(picturesDir, ".Hillview"))
        
        Log.d(TAG, "Scanning photo directories: ${directories.map { it.path }}")
        return directories
    }

    private fun calculateFileHash(file: File): String? {
        return try {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().use { inputStream ->
                val buffer = ByteArray(8192)
                var bytesRead: Int
                while (inputStream.read(buffer).also { bytesRead = it } != -1) {
                    digest.update(buffer, 0, bytesRead)
                }
            }
            digest.digest().joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to calculate hash for ${file.path}", e)
            null
        }
    }

    fun createPhotoEntityFromFile(file: File, fileHash: String): PhotoEntity? {
        Log.v(TAG, "🔍 Creating photo entity for: ${file.path}")
        
        var latitude = 0.0
        var longitude = 0.0
        var altitude = 0.0
        var bearing = 0.0
        var timestamp = System.currentTimeMillis() / 1000 // Default to current time
        var hasValidGPS = false
        var width = 0
        var height = 0
        
        try {
            val exif = ExifInterface(file.path)
            
            // Check for GPS coordinates
            val latLong = FloatArray(2)
            if (exif.getLatLong(latLong)) {
                latitude = latLong[0].toDouble()
                longitude = latLong[1].toDouble()
                hasValidGPS = true
                Log.v(TAG, "✅ GPS coordinates found: $latitude, $longitude")
            } else {
                Log.v(TAG, "❌ No GPS coordinates found in EXIF data")
            }
            
            // Read altitude if available
            exif.getAttribute(ExifInterface.TAG_GPS_ALTITUDE)?.let {
                altitude = it.toDoubleOrNull() ?: 0.0
                if (altitude != 0.0) {
                    Log.v(TAG, "📏 Altitude found: ${altitude}m")
                }
            }
            
            // Read bearing/direction if available  
            exif.getAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION)?.let {
                bearing = it.toDoubleOrNull() ?: 0.0
                if (bearing != 0.0) {
                    Log.v(TAG, "🧭 Bearing found: ${bearing}°")
                }
            }
            
            // Parse EXIF timestamp if available
            exif.getAttribute(ExifInterface.TAG_DATETIME)?.let { dateTimeStr ->
                try {
                    val sdf = SimpleDateFormat("yyyy:MM:dd HH:mm:ss", Locale.US)
                    val exifTimestamp = sdf.parse(dateTimeStr)?.time?.div(1000) ?: timestamp
                    timestamp = exifTimestamp
                    Log.v(TAG, "📅 EXIF timestamp found: $dateTimeStr")
                } catch (e: Exception) {
                    Log.w(TAG, "⚠️ Failed to parse EXIF timestamp '$dateTimeStr': ${e.message}")
                }
            }
            
            // Get image dimensions
            width = exif.getAttributeInt(ExifInterface.TAG_IMAGE_WIDTH, 0)
            height = exif.getAttributeInt(ExifInterface.TAG_IMAGE_LENGTH, 0)
            
        } catch (e: Exception) {
            Log.w(TAG, "❌ Failed to read EXIF data from ${file.path}: ${e.message}")
            return null // Cannot process file without EXIF access
        }
        
        // Reject photos without valid GPS coordinates
        if (!hasValidGPS || (latitude == 0.0 && longitude == 0.0)) {
            Log.i(TAG, "🚫 Photo ${file.name} has no valid GPS coordinates - skipping")
            return null
        }
        
        // Validate GPS coordinates are reasonable
        if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
            Log.w(TAG, "🚫 Photo ${file.name} has invalid GPS coordinates ($latitude, $longitude) - skipping")
            return null
        }
        
        Log.v(TAG, "✅ Creating photo entity for ${file.name} with GPS ($latitude, $longitude)")
        
        return PhotoEntity(
            id = UUID.randomUUID().toString(),
            filename = file.name,
            path = file.path,
            latitude = latitude,
            longitude = longitude,
            altitude = altitude,
            bearing = bearing,
            timestamp = timestamp,
            accuracy = 5.0, // Default accuracy
            width = width,
            height = height,
            fileSize = file.length(),
            createdAt = System.currentTimeMillis(),
            uploadStatus = "pending",
            fileHash = fileHash
        )
    }

    private fun isImageFile(filename: String): Boolean {
        val imageExtensions = setOf("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif")
        val extension = filename.substringAfterLast('.', "").lowercase()
        return extension in imageExtensions
    }
}