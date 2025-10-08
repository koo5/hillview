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
                val url = buildStreamUrl(source, bounds, authToken)
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

                    when {
                        currentLine.isEmpty() -> {
                            // Empty line signals end of event
                            if (eventData.isNotEmpty()) {
                                try {
                                    val message = parseStreamMessage(eventData.toString(), eventType)
                                    emit(message)
                                } catch (e: Exception) {
                                    Log.e(TAG, "Failed to parse stream message: ${e.message}")
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
                    val photos = photosArray.map { photoElement ->
                        json.decodeFromJsonElement<PhotoData>(photoElement)
                    }
                    StreamMessage.Photos(photos)
                }

                "stream_complete" -> {
                    val total = jsonData["total"]?.toString()?.toIntOrNull()
                    StreamMessage.StreamComplete(total)
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

    private fun buildStreamUrl(source: SourceConfig, bounds: Bounds, authToken: String?): String {
        val baseUrl = source.url ?: throw IllegalArgumentException("Stream source missing URL")

        return buildString {
            append(baseUrl)
            append("?")

            // Add bounds parameters
            append("bounds=${bounds.top_left.lat},${bounds.top_left.lng},${bounds.bottom_right.lat},${bounds.bottom_right.lng}")

            // Add auth token if available
            authToken?.let {
                append("&token=$it")
            }

            // Ensure SSE format
            append("&format=stream")
        }
    }

    private fun convertToPhotoData(photo: PhotoData, source: SourceConfig): PhotoData {
        return photo.copy(
            uid = "${source.id}-${photo.id}",
            source_type = source.type,
            source = source
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