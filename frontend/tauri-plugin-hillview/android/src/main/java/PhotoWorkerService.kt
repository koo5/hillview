package cz.hillview.plugin

import android.content.Context
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.double
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

// Explicit imports for type definitions
import cz.hillview.plugin.WorkerMessage
import cz.hillview.plugin.MessageType
import cz.hillview.plugin.ConfigData
import cz.hillview.plugin.ProcessId

/**
 * Photo Worker Service - Main orchestration class for Kotlin photo processing
 *
 * Replaces the Web Worker implementation to solve "window is not defined" issues.
 * Provides single entry point for all photo operations with process management,
 * prioritization, and aborting support.
 *
 * Communication design:
 * - Single general-purpose Tauri command: processPhotos
 * - Event-based responses (or polling fallback)
 * - Maintains compatibility with existing frontend architecture
 */
class PhotoWorkerService(private val context: Context, private val plugin: ExamplePlugin? = null) {
    companion object {
        private const val TAG = "PhotoWorkerService"
        private const val MAX_CONCURRENT_PROCESSES = 5
    }

    private val json = Json { ignoreUnknownKeys = true }
    private val photoOperations = PhotoOperations(context)
    private val cullingGrid = CullingGrid::class.java // Will be instantiated per request
    private val angularRangeCuller = AngularRangeCuller()

    // Process management
    private val processTable = ConcurrentHashMap<ProcessId, ProcessInfo>()
    private val activeProcesses = ConcurrentHashMap<ProcessId, Job>()
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    /**
     * Process info for tracking active operations
     */
    private data class ProcessInfo(
        val processId: ProcessId,
        val messageId: Int,
        val priority: Priority,
        val type: ProcessType,
        val startTime: Long,
        val abortFlag: AtomicBoolean = AtomicBoolean(false)
    )

    /**
     * Parse WorkerMessage manually to avoid serialization issues
     */
    private fun parseWorkerMessage(messageJson: String): WorkerMessage {
        val jsonElement = json.parseToJsonElement(messageJson)
        val jsonObject = jsonElement.jsonObject

        val typeString = jsonObject["type"]?.jsonPrimitive?.content
            ?: throw Exception("Missing 'type' field in WorkerMessage")
        val type = MessageType.valueOf(typeString)

        val messageId = jsonObject["messageId"]?.jsonPrimitive?.content?.toIntOrNull()
            ?: throw Exception("Missing or invalid 'messageId' field in WorkerMessage")

        val processId = jsonObject["processId"]?.jsonPrimitive?.content
            ?: throw Exception("Missing 'processId' field in WorkerMessage")

        val priority = jsonObject["priority"]?.jsonPrimitive?.content?.toIntOrNull()
            ?: throw Exception("Missing or invalid 'priority' field in WorkerMessage")

        val data = jsonObject["data"]?.jsonPrimitive?.content
            ?: throw Exception("Missing 'data' field in WorkerMessage")

        return WorkerMessage(
            type = type,
            messageId = messageId,
            processId = processId,
            priority = priority,
            data = data
        )
    }

    /**
     * Parse ConfigData manually to avoid serialization issues
     */
    private fun parseConfigData(dataJson: String): ConfigData {
        val jsonElement = json.parseToJsonElement(dataJson)
        val jsonObject = jsonElement.jsonObject

        val sourcesArray = jsonObject["sources"]?.jsonArray
            ?: throw Exception("Missing 'sources' field in ConfigData")

        val sources = sourcesArray.map { sourceElement ->
            val sourceObj = sourceElement.jsonObject
            SourceConfig(
                id = sourceObj["id"]?.jsonPrimitive?.content ?: "",
                name = sourceObj["name"]?.jsonPrimitive?.content ?: "",
                type = sourceObj["type"]?.jsonPrimitive?.content ?: "",
                enabled = sourceObj["enabled"]?.jsonPrimitive?.boolean ?: false,
                color = sourceObj["color"]?.jsonPrimitive?.content ?: "#000",
                url = sourceObj["url"]?.jsonPrimitive?.content,
                subtype = sourceObj["subtype"]?.jsonPrimitive?.content,
                requests = sourceObj["requests"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            )
        }

        val expectedWorkerVersion = jsonObject["expectedWorkerVersion"]?.jsonPrimitive?.content

        return ConfigData(
            sources = sources,
            expectedWorkerVersion = expectedWorkerVersion
        )
    }

    /**
     * Parse AreaData manually to avoid serialization issues
     */
    private fun parseAreaData(dataJson: String): AreaData {
        val jsonElement = json.parseToJsonElement(dataJson)
        val jsonObject = jsonElement.jsonObject

        val sourcesArray = jsonObject["sources"]?.jsonArray
            ?: throw Exception("Missing 'sources' field in AreaData")

        val sources = sourcesArray.map { sourceElement ->
            val sourceObj = sourceElement.jsonObject
            SourceConfig(
                id = sourceObj["id"]?.jsonPrimitive?.content ?: "",
                name = sourceObj["name"]?.jsonPrimitive?.content ?: "",
                type = sourceObj["type"]?.jsonPrimitive?.content ?: "",
                enabled = sourceObj["enabled"]?.jsonPrimitive?.boolean ?: false,
                color = sourceObj["color"]?.jsonPrimitive?.content ?: "#000",
                url = sourceObj["url"]?.jsonPrimitive?.content,
                subtype = sourceObj["subtype"]?.jsonPrimitive?.content,
                requests = sourceObj["requests"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            )
        }

        val boundsObj = jsonObject["bounds"]?.jsonObject
            ?: throw Exception("Missing 'bounds' field in AreaData")

        val topLeftObj = boundsObj["top_left"]?.jsonObject
            ?: throw Exception("Missing 'top_left' in bounds")
        val bottomRightObj = boundsObj["bottom_right"]?.jsonObject
            ?: throw Exception("Missing 'bottom_right' in bounds")

        val bounds = Bounds(
            top_left = LatLng(
                lat = topLeftObj["lat"]?.jsonPrimitive?.double ?: 0.0,
                lng = topLeftObj["lng"]?.jsonPrimitive?.double ?: 0.0
            ),
            bottom_right = LatLng(
                lat = bottomRightObj["lat"]?.jsonPrimitive?.double ?: 0.0,
                lng = bottomRightObj["lng"]?.jsonPrimitive?.double ?: 0.0
            )
        )

        val maxPhotos = jsonObject["maxPhotos"]?.jsonPrimitive?.intOrNull
            ?: throw Exception("Missing or invalid 'maxPhotos' field in AreaData")

        return AreaData(
            sources = sources,
            bounds = bounds,
            maxPhotos = maxPhotos
        )
    }

    /**
     * Main entry point - single general-purpose message processing
     * Like new.worker.ts: immediate response + async processing with events
     */
    suspend fun processPhotos(
        messageJson: String,
        authTokenProvider: suspend () -> String?
    ) {
        try {
            val message = parseWorkerMessage(messageJson)
            Log.d(TAG, "PhotoWorkerService: Processing message type ${message.type} (${message.processId})")

            when (message.type) {
                MessageType.PROCESS_CONFIG -> {
                    // Launch async processing like new.worker.ts
                    serviceScope.launch {
                        processConfigMessage(message, authTokenProvider)
                    }
                }
                MessageType.PROCESS_AREA -> {
                    // Launch async processing like new.worker.ts
                    serviceScope.launch {
                        processAreaMessage(message, authTokenProvider)
                    }
                }
                MessageType.ABORT_PROCESS -> {
                    abortProcess(message.processId)
                }
                MessageType.CLEANUP -> {
                    cleanup()
                }
            }

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Error processing message", error)
            // Send error event to frontend like new.worker.ts does
            sendErrorEvent("Error processing message: ${error.message}")
        }
    }

    /**
     * Process config update - translation of worker's CONFIG message handling
     */
    private suspend fun processConfigMessage(
        message: WorkerMessage,
        authTokenProvider: suspend () -> String?
    ) {
        val config = parseConfigData(message.data)

        // Abort any existing lower priority processes
        abortLowerPriorityProcesses(message.priority)

        // Create process info
        val processInfo = ProcessInfo(
            processId = message.processId,
            messageId = message.messageId,
            priority = message.priority,
            type = ProcessType.CONFIG,
            startTime = System.currentTimeMillis()
        )
        processTable[message.processId] = processInfo

        try {
            // Process synchronously and send photos update
            val photos = photoOperations.processConfig(
                processId = message.processId,
                messageId = message.messageId,
                config = config,
                shouldAbort = { processInfo.abortFlag.get() },
                authTokenProvider = authTokenProvider
            )

            if (!processInfo.abortFlag.get()) {
                // Send photos update to frontend like new.worker.ts does
                sendPhotosUpdate(photos, emptyMap())
            }

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Config processing error (${message.processId})", error)
            // Send error event to frontend like new.worker.ts does
            sendErrorEvent("Config processing error: ${error.message}")
        } finally {
            processTable.remove(message.processId)
            activeProcesses.remove(message.processId)
        }
    }

    /**
     * Process area update - translation of worker's AREA message handling
     */
    private suspend fun processAreaMessage(
        message: WorkerMessage,
        authTokenProvider: suspend () -> String?
    ) {
        val areaData = parseAreaData(message.data)

        // Abort any existing lower priority processes
        abortLowerPriorityProcesses(message.priority)

        // Create process info
        val processInfo = ProcessInfo(
            processId = message.processId,
            messageId = message.messageId,
            priority = message.priority,
            type = ProcessType.AREA,
            startTime = System.currentTimeMillis()
        )
        processTable[message.processId] = processInfo

        try {
            // Process area photos synchronously and send photos update
            val sourcesPhotosInArea = photoOperations.processArea(
                processId = message.processId,
                sources = areaData.sources,
                bounds = areaData.bounds,
                shouldAbort = { processInfo.abortFlag.get() },
                authTokenProvider = authTokenProvider
            )

            if (!processInfo.abortFlag.get()) {
                // Apply culling if photos exceed maxPhotos
                val totalPhotos = sourcesPhotosInArea.values.sumOf { it.size }
                val finalPhotos = if (totalPhotos > areaData.maxPhotos) {
                    Log.d(TAG, "PhotoWorkerService: Applying culling - $totalPhotos photos > ${areaData.maxPhotos} limit")

                    val gridCuller = CullingGrid(areaData.bounds)
                    val culledPhotos = gridCuller.cullPhotos(sourcesPhotosInArea, areaData.maxPhotos)

                    Log.d(TAG, "PhotoWorkerService: Grid culling complete - ${culledPhotos.size} photos selected")
                    culledPhotos
                } else {
                    sourcesPhotosInArea.values.flatten()
                }

                // Send photos update to frontend like new.worker.ts does
                sendPhotosUpdate(finalPhotos, sourcesPhotosInArea)
            }

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Area processing error (${message.processId})", error)
            // Send error event to frontend like new.worker.ts does
            sendErrorEvent("Area processing error: ${error.message}")
        } finally {
            processTable.remove(message.processId)
            activeProcesses.remove(message.processId)
        }
    }

    /**
     * Process range culling - for user movement scenarios
     */
    suspend fun processRangeCulling(
        photos: List<PhotoData>,
        center: LatLng,
        range: Double,
        maxPhotos: Int
    ): List<PhotoData> {
        return angularRangeCuller.cullPhotosInRange(photos, center, range, maxPhotos)
    }

    /**
     * Abort a specific process
     */
    private fun abortProcess(processId: ProcessId) {
        Log.d(TAG, "PhotoWorkerService: Aborting process $processId")

        processTable[processId]?.abortFlag?.set(true)
        activeProcesses[processId]?.cancel()
        activeProcesses.remove(processId)
        processTable.remove(processId)
    }

    /**
     * Abort lower priority processes - translation of worker priority logic
     */
    private fun abortLowerPriorityProcesses(newPriority: Priority) {
        val processesToAbort = processTable.values.filter { it.priority > newPriority }

        for (process in processesToAbort) {
            Log.d(TAG, "PhotoWorkerService: Aborting lower priority process ${process.processId} (priority ${process.priority} < $newPriority)")
            abortProcess(process.processId)
        }
    }

    /**
     * Send photos update to frontend via Tauri events (like new.worker.ts postMessage)
     */
    private suspend fun sendPhotosUpdate(photos: List<PhotoData>, sourcesPhotosInArea: Map<String, List<PhotoData>>) {
        try {
            // Create photosUpdate message like new.worker.ts sends
            val eventData = app.tauri.plugin.JSObject()
            eventData.put("type", "photosUpdate")
            eventData.put("photosInArea", serializePhotoDataList(photos))
            eventData.put("photosInRange", serializePhotoDataList(photos)) // For now, same as area photos
            eventData.put("timestamp", System.currentTimeMillis())

            Log.d(TAG, "PhotoWorkerService: Queuing photosUpdate message with ${photos.size} photos")

            // Use message queue instead of direct event triggering
            plugin?.queueMessage("photo-worker-update", eventData)

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Error creating photos update message", error)
        }
    }

    /**
     * Send error event to frontend via Tauri events (like new.worker.ts postMessage error)
     */
    private fun sendErrorEvent(errorMessage: String) {
        try {
            // Create error message like new.worker.ts sends
            val eventData = app.tauri.plugin.JSObject()
            eventData.put("type", "error")
            eventData.put("error", errorMessage)
            eventData.put("timestamp", System.currentTimeMillis())

            Log.d(TAG, "PhotoWorkerService: Queuing error message: $errorMessage")

            // Use message queue instead of direct event triggering
            plugin?.queueMessage("photo-worker-error", eventData)

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Error creating error message", error)
        }
    }

    /**
     * Get active process count for monitoring
     */
    fun getActiveProcessCount(): Int = processTable.size

    /**
     * Get process status for debugging
     */
    fun getProcessStatus(): Map<ProcessId, String> {
        return processTable.mapValues { (_, info) ->
            "${info.type}:${info.priority}:${System.currentTimeMillis() - info.startTime}ms"
        }
    }

    /**
     * Clean up all resources
     */
    fun cleanup() {
        Log.d(TAG, "PhotoWorkerService: Cleaning up all resources")

        // Abort all active processes
        processTable.keys.forEach { processId ->
            abortProcess(processId)
        }

        // Cancel service scope
        serviceScope.cancel()

        // Clean up photo operations
        photoOperations.cleanup()
    }

    /**
     * Set max photos in area for photo operations
     */
    fun setMaxPhotosInArea(maxPhotos: Int) {
        photoOperations.setMaxPhotosInArea(maxPhotos)
    }

    /**
     * Manually serialize PhotoData list to JSON to avoid serialization compiler plugin issues
     */
    private fun serializePhotoDataList(photos: List<PhotoData>): String {
        if (photos.isEmpty()) return "[]"

        val jsonArray = photos.joinToString(separator = ",", prefix = "[", postfix = "]") { photo ->
            """
            {
                "id": "${photo.id}",
                "uid": "${photo.uid}",
                "source_type": "${photo.source_type}",
                "file": ${if (photo.file != null) "\"${photo.file}\"" else "null"},
                "url": ${if (photo.url != null) "\"${photo.url}\"" else "null"},
                "coord": {
                    "lat": ${photo.coord.lat},
                    "lng": ${photo.coord.lng}
                },
                "bearing": ${photo.bearing},
                "altitude": ${photo.altitude ?: "null"},
                "source": "${photo.source}",
                "isDevicePhoto": ${photo.isDevicePhoto}
            }
            """.trimIndent()
        }

        return jsonArray
    }
}

/**
 * Area processing data structure
 */
@kotlinx.serialization.Serializable
private data class AreaData(
    val sources: List<SourceConfig>,
    val bounds: Bounds,
    val maxPhotos: Int
)