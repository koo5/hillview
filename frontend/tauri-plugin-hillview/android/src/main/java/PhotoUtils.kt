package cz.hillview.plugin

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.*

object PhotoUtils {
    private const val TAG = "🢄PhotoUtils"

    // Thread-local date formatters to avoid creating new instances repeatedly
    // SimpleDateFormat is not thread-safe, so we use ThreadLocal
    val isoDateFormat: ThreadLocal<SimpleDateFormat> = ThreadLocal.withInitial {
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }
    }

    // Common EXIF date formats - thread-local for safety
    val exifDateFormats: ThreadLocal<List<SimpleDateFormat>> = ThreadLocal.withInitial {
        listOf(
            SimpleDateFormat("yyyy:MM:dd HH:mm:ss", Locale.US),      // Standard EXIF format
            SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US),      // ISO format
            SimpleDateFormat("yyyy:MM:dd'T'HH:mm:ss", Locale.US),    // Mixed format
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US),    // ISO with T separator
            SimpleDateFormat("yyyy/MM/dd HH:mm:ss", Locale.US)
        )
    }

    /**
     * Parse a date string using common EXIF formats
     * @return parsed Date or null if no format matches
     */
    fun parseExifDate(dateString: String): Date? {
        val formats = exifDateFormats.get() ?: return null
        for (format in formats) {
            try {
                val date = format.parse(dateString)
                if (date != null) return date
            } catch (e: Exception) {
                // Try next format
            }
        }
        return null
    }

    /**
     * Check if path is a content:// URI
     */
    fun isContentUri(path: String) = path.startsWith("content://")

    /**
     * Get content type from filename extension
     */
    fun getContentType(filename: String): String {
        return when (filename.substringAfterLast('.').lowercase()) {
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "webp" -> "image/webp"
            else -> "image/jpeg"
        }
    }

    /**
     * Read bytes from a path (either file path or content:// URI)
     */
    fun readBytesFromPath(context: Context, path: String): ByteArray? {
        return try {
            if (isContentUri(path)) {
                val uri = Uri.parse(path)
                context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            } else {
                File(path).readBytes()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read bytes from path: $path", e)
            null
        }
    }

    /**
     * Check if a path exists (either file path or content:// URI)
     */
    fun pathExists(context: Context, path: String): Boolean {
        return try {
            if (isContentUri(path)) {
                val uri = Uri.parse(path)
                context.contentResolver.openInputStream(uri)?.use { true } ?: false
            } else {
                File(path).exists()
            }
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Convert timestamp to ISO 8601 format string
     * @param timestamp Unix timestamp in milliseconds
     * @return ISO 8601 formatted string (e.g., "2023-12-01T15:30:45Z") or null if conversion fails
     */
    fun formatTimestampToIso(timestamp: Long): String? {
        return try {
            val date = Date(timestamp)
            isoDateFormat.get()?.format(date)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to format timestamp $timestamp to ISO format", e)
            null
        }
    }

    /**
     * Generate a unique photo ID using timestamp and file hash
     * @param fileHash MD5 hash of the photo file
     * @param idPrefix Optional prefix for the ID (defaults to "device")
     * @return Unique photo ID in format: "prefix_timestamp_hash8chars"
     */
    fun generatePhotoId(fileHash: String, idPrefix: String = "device"): String {
        return "${idPrefix}_${System.currentTimeMillis()}_${fileHash.take(8)}"
    }

    /**
     * Generate a unique photo ID using timestamp and file hash (simplified version)
     * @param fileHash MD5 hash of the photo file
     * @return Unique photo ID in format: "timestamp_hash8chars"
     */
    fun generatePhotoId(fileHash: String): String {
        return "${System.currentTimeMillis()}_${fileHash.take(8)}"
    }
    
    /**
     * Calculate MD5 hash of a file
     * @return MD5 hash as hex string, or null if calculation fails
     */
    fun calculateFileHash(file: File): String? {
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
    
    /**
     * Create PhotoEntity from file with EXIF data extraction
     * @param file The image file to process
     * @param fileHash Pre-calculated hash of the file
     * @param idPrefix Prefix for the generated ID
     * @return PhotoEntity with extracted metadata
     */
    fun createPhotoEntityFromFile(file: File, fileHash: String, idPrefix: String = "device"): PhotoEntity {
        var latitude = 0.0
        var longitude = 0.0
        var altitude = 0.0
        var bearing = 0.0
        var width = 0
        var height = 0
        var timestamp = file.lastModified()

        try {
            val exif = ExifInterface(file.path)

            // Extract GPS coordinates
            val coords = extractGpsCoordinates(exif)
            latitude = coords.first
            longitude = coords.second

            // Extract altitude
            altitude = extractAltitude(exif)

            // Extract bearing/direction
            bearing = extractBearing(exif)

            // Extract image dimensions
            val dimensions = extractImageDimensions(exif)
            width = dimensions.first
            height = dimensions.second

            // Extract timestamp
            timestamp = extractTimestamp(exif, file.lastModified())

            Log.d(TAG, "Extracted EXIF data for ${file.name}: lat=$latitude, lng=$longitude, alt=$altitude, bearing=$bearing, ${width}x${height}")

        } catch (e: IOException) {
            Log.w(TAG, "Failed to read EXIF data from ${file.path}: ${e.message}")
            // Continue with default values
        }

        return PhotoEntity(
            id = generatePhotoId(fileHash, idPrefix),
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
    
    /**
     * Convert URI to file path, with fallback to temp file copy
     * @param context Android context for content resolver
     * @param uri URI to convert
     * @return File path string, or null if conversion fails
     */
    fun getFilePathFromUri(context: Context, uri: Uri): String? {
        return when (uri.scheme) {
            "file" -> uri.path
            "content" -> {
                // Try to get actual file path first
                getContentUriPath(context, uri) 
                    ?: copyUriToTempFile(context, uri) // Fallback to temp file
            }
            else -> {
                Log.w(TAG, "Unsupported URI scheme: ${uri.scheme}")
                null
            }
        }
    }
    
    private fun getContentUriPath(context: Context, uri: Uri): String? {
        try {
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val columnIndex = cursor.getColumnIndex("_data")
                    if (columnIndex != -1) {
                        return cursor.getString(columnIndex)
                    }
                }
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "No permission to access content URI: $uri")
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "Invalid content URI: $uri")
        }
        return null
    }
    
    private fun copyUriToTempFile(context: Context, uri: Uri): String? {
        try {
            val inputStream = context.contentResolver.openInputStream(uri)
                ?: return null
            
            val tempFile = File(context.cacheDir, "temp_import_${System.currentTimeMillis()}")
            inputStream.use { input ->
                tempFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
            return tempFile.absolutePath
        } catch (e: IOException) {
            Log.e(TAG, "Failed to copy URI to temp file: $uri", e)
        } catch (e: SecurityException) {
            Log.e(TAG, "No permission to read URI: $uri", e)
        }
        return null
    }
    
    private fun extractGpsCoordinates(exif: ExifInterface): Pair<Double, Double> {
        // Method 1: Use built-in getLatLong (most reliable)
        val latLong = FloatArray(2)
        @Suppress("DEPRECATION")
        if (exif.getLatLong(latLong)) {
            val latitude = latLong[0].toDouble()
            val longitude = latLong[1].toDouble()
            Log.v(TAG, "GPS coordinates from getLatLong: $latitude, $longitude")
            return Pair(latitude, longitude)
        }

        // Method 2: Manual parsing of GPS attributes
        val latRef = exif.getAttribute(ExifInterface.TAG_GPS_LATITUDE_REF)
        val lngRef = exif.getAttribute(ExifInterface.TAG_GPS_LONGITUDE_REF)
        val latStr = exif.getAttribute(ExifInterface.TAG_GPS_LATITUDE)
        val lngStr = exif.getAttribute(ExifInterface.TAG_GPS_LONGITUDE)

        if (latRef != null && lngRef != null && latStr != null && lngStr != null) {
            try {
                var latitude = convertDMSToDD(latStr)
                var longitude = convertDMSToDD(lngStr)

                // Apply hemisphere corrections
                if (latRef == "S") latitude = -latitude
                if (lngRef == "W") longitude = -longitude

                Log.v(TAG, "GPS coordinates from manual parsing: $latitude, $longitude")
                return Pair(latitude, longitude)
            } catch (e: NumberFormatException) {
                Log.w(TAG, "Failed to parse GPS coordinates: invalid number format in $latStr, $lngStr")
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "Failed to parse GPS coordinates: invalid DMS format")
            }
        }

        Log.v(TAG, "No GPS coordinates found")
        return Pair(0.0, 0.0)
    }
    
    private fun extractAltitude(exif: ExifInterface): Double {
        val altitudeStr = exif.getAttribute(ExifInterface.TAG_GPS_ALTITUDE) ?: return 0.0
        val altitudeRefStr = exif.getAttribute(ExifInterface.TAG_GPS_ALTITUDE_REF)
        
        return try {
            var altitude = convertRationalToDecimal(altitudeStr)
            // Apply sea level reference (0 = above sea level, 1 = below sea level)
            if (altitudeRefStr == "1") {
                altitude = -altitude
            }
            Log.v(TAG, "Altitude from EXIF: $altitude")
            altitude
        } catch (e: NumberFormatException) {
            Log.w(TAG, "Failed to parse altitude: invalid number format in $altitudeStr")
            0.0
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "Failed to parse altitude: invalid rational format")
            0.0
        }
    }
    
    private fun extractBearing(exif: ExifInterface): Double {
        val bearingStr = exif.getAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION) ?: return 0.0
        
        return try {
            val bearing = convertRationalToDecimal(bearingStr)
            Log.v(TAG, "Bearing from EXIF: $bearing")
            bearing
        } catch (e: NumberFormatException) {
            Log.w(TAG, "Failed to parse bearing: invalid number format in $bearingStr")
            0.0
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "Failed to parse bearing: invalid rational format")
            0.0
        }
    }
    
    private fun extractImageDimensions(exif: ExifInterface): Pair<Int, Int> {
        // Method 1: Standard EXIF dimension tags
        var width = exif.getAttributeInt(ExifInterface.TAG_IMAGE_WIDTH, 0)
        var height = exif.getAttributeInt(ExifInterface.TAG_IMAGE_LENGTH, 0)

        if (width > 0 && height > 0) {
            Log.v(TAG, "Image dimensions from EXIF: ${width}x${height}")
            return Pair(width, height)
        }

        // Method 2: Try pixel dimension tags
        width = exif.getAttributeInt(ExifInterface.TAG_PIXEL_X_DIMENSION, 0)
        height = exif.getAttributeInt(ExifInterface.TAG_PIXEL_Y_DIMENSION, 0)

        if (width > 0 && height > 0) {
            Log.v(TAG, "Image dimensions from pixel tags: ${width}x${height}")
            return Pair(width, height)
        }

        Log.v(TAG, "No image dimensions found in EXIF")
        return Pair(0, 0)
    }
    
    private fun extractTimestamp(exif: ExifInterface, fallbackTimestamp: Long): Long {
        // Try multiple EXIF timestamp fields in order of preference
        val timestampFields = arrayOf(
            ExifInterface.TAG_DATETIME_ORIGINAL,
            ExifInterface.TAG_DATETIME_DIGITIZED,
            ExifInterface.TAG_DATETIME
        )

        for (field in timestampFields) {
            val timestampStr = exif.getAttribute(field) ?: continue
            
            try {
                // EXIF timestamp format: "YYYY:MM:DD HH:MM:SS"
                val parts = timestampStr.split(" ")
                if (parts.size != 2) continue
                
                val dateParts = parts[0].split(":")
                val timeParts = parts[1].split(":")
                
                if (dateParts.size != 3 || timeParts.size != 3) continue
                
                val year = dateParts[0].toInt()
                val month = dateParts[1].toInt() - 1 // Calendar months are 0-based
                val day = dateParts[2].toInt()
                val hour = timeParts[0].toInt()
                val minute = timeParts[1].toInt()
                val second = timeParts[2].toInt()
                
                val calendar = java.util.Calendar.getInstance()
                calendar.set(year, month, day, hour, minute, second)
                val timestamp = calendar.timeInMillis
                
                Log.v(TAG, "Timestamp from $field: $timestampStr -> $timestamp")
                return timestamp
            } catch (e: NumberFormatException) {
                Log.w(TAG, "Failed to parse timestamp from $field: invalid number format in $timestampStr")
                continue
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "Failed to parse timestamp from $field: invalid date/time values in $timestampStr")
                continue
            }
        }

        Log.v(TAG, "Using fallback timestamp: $fallbackTimestamp")
        return fallbackTimestamp
    }
    
    private fun convertDMSToDD(dmsStr: String): Double {
        // Parse degrees/minutes/seconds format: "latitude,longitude"
        // Example: "37/1,54/1,25883/1000" -> degrees=37, minutes=54, seconds=25.883
        val parts = dmsStr.split(",")
        if (parts.size != 3) {
            throw IllegalArgumentException("Invalid DMS format: expected 3 parts, got ${parts.size}")
        }
        
        val degrees = convertRationalToDecimal(parts[0])
        val minutes = convertRationalToDecimal(parts[1])
        val seconds = convertRationalToDecimal(parts[2])
        
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    }
    
    private fun convertRationalToDecimal(rational: String): Double {
        // Parse rational format: "numerator/denominator"
        val parts = rational.split("/")
        return when (parts.size) {
            1 -> parts[0].toDouble()
            2 -> {
                val numerator = parts[0].toDouble()
                val denominator = parts[1].toDouble()
                if (denominator == 0.0) {
                    throw IllegalArgumentException("Division by zero in rational: $rational")
                }
                numerator / denominator
            }
            else -> throw IllegalArgumentException("Invalid rational format: $rational")
        }
    }
}