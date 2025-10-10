package cz.hillview.plugin

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*
import okhttp3.*
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

/**
 * Stream Photo Loader - EventSource implementation for real-time photo streaming
 *
 * Faithful translation of StreamSourceLoader.ts with EventSource functionality
 * using OkHttp for Server-Sent Events (SSE) streaming.
 */
class StreamPhotoLoader {
    companion object {
        private const val TAG = "StreamPhotoLoader"
        private const val CONNECTION_TIMEOUT_SECONDS = 30L
        private const val READ_TIMEOUT_SECONDS = 60L
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(CONNECTION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

    private val json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
    }

    suspend fun loadPhotos(
        source: SourceConfig,
        bounds: Bounds?,
        maxPhotos: Int,
        authToken: String?,
        shouldAbort: () -> Boolean
    ): List<PhotoData> {
        if (bounds == null) {
            Log.d(TAG, "StreamPhotoLoader: Started ${source.id} without bounds - waiting for area update")
            return emptyList()
        }

        return loadPhotosWithEventSource(source, bounds, maxPhotos, authToken, shouldAbort)
    }

    private suspend fun loadPhotosWithEventSource(
        source: SourceConfig,
        bounds: Bounds,
        maxPhotos: Int,
        authToken: String?,
        shouldAbort: () -> Boolean
    ): List<PhotoData> {
        val photos = mutableListOf<PhotoData>()
        var retryCount = 0
        val maxRetries = 1

        while (retryCount <= maxRetries && !shouldAbort()) {
            try {
                val url = buildStreamUrl(source, bounds, maxPhotos, authToken)
                Log.d(TAG, "StreamPhotoLoader: Starting stream from $url (attempt ${retryCount + 1}/${maxRetries + 1})")

                var streamCompleted = false
                var streamError: String? = null

                streamEventSource(url, shouldAbort).collect { message ->
                    if (shouldAbort()) return@collect

                    when (message) {
                        is StreamMessage.Photos -> {
                            Log.d(TAG, "StreamPhotoLoader: Received ${message.photos.size} photos")

                            val convertedPhotos = message.photos.map { photo ->
                                convertToPhotoData(photo, source)
                            }

                            photos.addAll(convertedPhotos)

                            // Apply bounds filtering and respect maxPhotos limit
                            val filteredPhotos = filterPhotosInBounds(photos, bounds)
                            if (filteredPhotos.size >= maxPhotos) {
                                Log.d(TAG, "StreamPhotoLoader: Reached maxPhotos limit ($maxPhotos)")
                                streamCompleted = true
                                return@collect
                            }
                        }

                        is StreamMessage.StreamComplete -> {
                            Log.d(TAG, "StreamPhotoLoader: Stream completed for ${source.id}")
                            streamCompleted = true
                            return@collect
                        }

                        is StreamMessage.IgnoreMessage -> {
                            // Do nothing, continue streaming
                        }

                        is StreamMessage.Error -> {
                            Log.e(TAG, "StreamPhotoLoader: Stream error: ${message.message}")
                            streamError = message.message
                            return@collect
                        }
                    }
                }

                // Handle completion or error after collect
                streamError?.let { error ->
                    throw Exception("Stream error: $error")
                }

                if (streamCompleted) {
                    return filterPhotosInBounds(photos, bounds).take(maxPhotos)
                }

                // If we reach here, stream completed normally
                return filterPhotosInBounds(photos, bounds).take(maxPhotos)

            } catch (e: Exception) {
                Log.e(TAG, "StreamPhotoLoader: Error on attempt ${retryCount + 1}: ${e.message}")

                if (retryCount >= maxRetries) {
                    throw e
                }

                // Check if this looks like an auth error and we should retry
                if (e.message?.contains("401") == true || e.message?.contains("auth") == true) {
                    retryCount++
                    delay(1000) // Brief delay before retry
                    Log.d(TAG, "StreamPhotoLoader: Retrying with fresh auth token")
                    continue
                } else {
                    throw e // Non-auth errors don't retry
                }
            }
        }

        return emptyList()
    }

    private fun streamEventSource(url: String, shouldAbort: () -> Boolean): Flow<StreamMessage> = flow {
        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .header("Cache-Control", "no-cache")
            .build()

        val response = client.newCall(request).execute()

        if (!response.isSuccessful) {
            throw Exception("HTTP ${response.code}: ${response.message}")
        }

        response.body?.byteStream()?.let { inputStream ->
            BufferedReader(InputStreamReader(inputStream)).use { reader ->
                val eventData = StringBuilder()
                var eventType: String? = null

                while (!shouldAbort()) {
                    val line = reader.readLine() ?: break
                    val currentLine = line

                    // Debug: Log all raw SSE lines
                    Log.d(TAG, "StreamPhotoLoader: Raw SSE line: '$currentLine'")

                    when {
                        currentLine.isEmpty() -> {
                            // Empty line signals end of event
                            if (eventData.isNotEmpty()) {
                                try {
                                    Log.d(TAG, "StreamPhotoLoader: Processing event data: '$eventData' with type: '$eventType'")
                                    val message = parseStreamMessage(eventData.toString(), eventType)
                                    Log.d(TAG, "StreamPhotoLoader: Parsed message type: ${message::class.simpleName}")
                                    emit(message)
                                } catch (e: Exception) {
                                    Log.e(TAG, "Failed to parse stream message: ${e.message}")
                                    Log.e(TAG, "Raw data that failed to parse: '$eventData'")
                                    emit(StreamMessage.Error("Parse error: ${e.message}"))
                                }

                                eventData.clear()
                                eventType = null
                            }
                        }

                        currentLine.startsWith("data: ") -> {
                            eventData.append(currentLine.substring(6))
                        }

                        currentLine.startsWith("event: ") -> {
                            eventType = currentLine.substring(7)
                        }

                        currentLine.startsWith("retry: ") -> {
                            // Handle retry directive if needed
                        }
                    }
                }
            }
        }
    }

    private fun parseStreamMessage(data: String, eventType: String?): StreamMessage {
        return try {
            val jsonData = json.parseToJsonElement(data).jsonObject
            val type = jsonData["type"]?.toString()?.replace("\"", "") ?: eventType ?: "unknown"

            when (type) {
                "photos" -> {
                    val photosArray = jsonData["photos"]?.jsonArray ?: JsonArray(emptyList())
                    Log.d(TAG, "StreamPhotoLoader: Found photos array with ${photosArray.size} elements")
                    val photos = photosArray.mapNotNull { photoElement ->
                        try {
                            val photo = parsePhotoJson(photoElement.jsonObject)
                            Log.d(TAG, "StreamPhotoLoader: Successfully parsed photo ${photo.id}")
                            photo
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to parse photo: ${e.message}")
                            Log.w(TAG, "Raw photo data: ${photoElement}")
                            null
                        }
                    }
                    Log.d(TAG, "StreamPhotoLoader: Parsed ${photos.size} photos successfully")
                    StreamMessage.Photos(photos)
                }

                "stream_complete" -> {
                    val total = jsonData["total"]?.toString()?.toIntOrNull()
                    StreamMessage.StreamComplete(total)
                }

                "region_complete" -> {
                    // Ignore region_complete messages - they're just progress info
                    Log.d(TAG, "StreamPhotoLoader: Region completed (ignoring)")
                    StreamMessage.IgnoreMessage
                }

                "error" -> {
                    val message = jsonData["message"]?.toString()?.replace("\"", "") ?: "Unknown stream error"
                    StreamMessage.Error(message)
                }

                else -> {
                    Log.w(TAG, "Unknown stream message type: $type")
                    StreamMessage.Error("Unknown message type: $type")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse stream data: $data", e)
            StreamMessage.Error("Parse error: ${e.message}")
        }
    }

    private fun buildStreamUrl(source: SourceConfig, bounds: Bounds, maxPhotos: Int, authToken: String?): String {
        val baseUrl = source.url ?: throw IllegalArgumentException("Stream source missing URL")

        return buildString {
            append(baseUrl)
            append("?")

            // Add bounds parameters using the same format as working TypeScript implementation
            append("top_left_lat=${bounds.top_left.lat}")
            append("&top_left_lon=${bounds.top_left.lng}")  // Note: lon not lng
            append("&bottom_right_lat=${bounds.bottom_right.lat}")
            append("&bottom_right_lon=${bounds.bottom_right.lng}")  // Note: lon not lng

            // Add client_id parameter (required by server)
            val clientId = "default"  // Match TypeScript default
            append("&client_id=$clientId")

            // Add max_photos parameter
            append("&max_photos=$maxPhotos")

            // Add auth token if available
            authToken?.let {
                append("&token=$it")
            }

            // Note: format=stream not needed - /mapillary endpoint returns SSE by default
        }
    }

    /**
     * Parse photo JSON to handle external stream endpoint formats:
     * 1. Mapillary endpoint: geometry.coordinates, thumb_1024_url, compass_angle, etc.
     * 2. Hillview endpoint: geometry.coordinates, filename + sizes, bearing, etc.
     */
    private fun parsePhotoJson(photoJson: JsonObject): PhotoData {
        val id = photoJson["id"]?.jsonPrimitive?.content
            ?: throw IllegalArgumentException("Photo missing id")

        // Extract coordinates from geometry.coordinates [lng, lat] (both endpoints use this format)
        val coords = photoJson["geometry"]?.jsonObject?.get("coordinates")?.jsonArray
            ?: throw IllegalArgumentException("Photo missing geometry.coordinates")

        val lng = coords[0].jsonPrimitive.double
        val lat = coords[1].jsonPrimitive.double
        val coord = LatLng(lat, lng)

        // Extract bearing with endpoint-specific fallbacks
        // Mapillary: compass_angle, computed_compass_angle, computed_bearing
        // Hillview: bearing, computed_bearing
        val bearing = photoJson["bearing"]?.jsonPrimitive?.doubleOrNull
            ?: photoJson["computed_bearing"]?.jsonPrimitive?.doubleOrNull
            ?: photoJson["compass_angle"]?.jsonPrimitive?.doubleOrNull
            ?: photoJson["computed_compass_angle"]?.jsonPrimitive?.doubleOrNull
            ?: 0.0

        // Extract altitude with fallbacks
        val altitude = photoJson["computed_altitude"]?.jsonPrimitive?.doubleOrNull
            ?: photoJson["altitude"]?.jsonPrimitive?.doubleOrNull
            ?: 0.0

        // Extract URL/file with endpoint-specific formats
        // Mapillary: thumb_1024_url
        // Hillview: filename (sizes handled separately)
        val url = photoJson["thumb_1024_url"]?.jsonPrimitive?.content
            ?: photoJson["url"]?.jsonPrimitive?.content
            ?: ""

        val file = photoJson["filename"]?.jsonPrimitive?.content
            ?: photoJson["file"]?.jsonPrimitive?.content
            ?: "stream_$id"

        // Extract captured_at as-is (ISO string - no conversion)
        val capturedAt = photoJson["captured_at"]?.jsonPrimitive?.content

        // Extract is_pano
        val isPano = photoJson["is_pano"]?.jsonPrimitive?.booleanOrNull

        // Extract creator (both endpoints support this)
        val creator = photoJson["creator"]?.jsonObject?.let { creatorObj ->
            val creatorId = creatorObj["id"]?.jsonPrimitive?.content
            val username = creatorObj["username"]?.jsonPrimitive?.content
            if (creatorId != null && username != null) {
                Creator(id = creatorId, username = username)
            } else null
        }

        // Extract fileHash from file_md5 (Hillview endpoint)
        val fileHash = photoJson["file_md5"]?.jsonPrimitive?.content

        return PhotoData(
            id = id,
            uid = "stream-$id", // Will be replaced by convertToPhotoData
            source_type = "stream",
            file = file,
            url = url,
            coord = coord,
            bearing = bearing,
            altitude = altitude,
            source = "stream", // Just source ID
            isDevicePhoto = false,
            captured_at = capturedAt,
            is_pano = isPano,
            creator = creator,
            fileHash = fileHash
        )
    }

    private fun convertToPhotoData(photo: PhotoData, source: SourceConfig): PhotoData {
        return photo.copy(
            uid = "${source.id}-${photo.id}",
            source_type = source.type,
            source = source.id
        )
    }

    private fun filterPhotosInBounds(photos: List<PhotoData>, bounds: Bounds): List<PhotoData> {
        return photos.filter { photo ->
            photo.coord.lat <= bounds.top_left.lat &&
            photo.coord.lat >= bounds.bottom_right.lat &&
            photo.coord.lng >= bounds.top_left.lng &&
            photo.coord.lng <= bounds.bottom_right.lng
        }
    }
}