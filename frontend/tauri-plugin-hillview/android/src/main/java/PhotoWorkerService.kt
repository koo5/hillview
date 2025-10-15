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
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.put
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

        // Photo processing constants - should match photoWorkerConstants.ts
        private const val MAX_PHOTOS_IN_AREA = 400
        private const val MAX_PHOTOS_IN_RANGE = 200
        private const val DEFAULT_RANGE_METERS = 1000.0
    }

    private val json = Json { ignoreUnknownKeys = true }
    private val photoOperations = PhotoOperations(context)
    private val cullingGrid = CullingGrid::class.java // Will be instantiated per request
    private val angularRangeCuller = AngularRangeCuller()

    // Process management
    private val processTable = ConcurrentHashMap<ProcessId, ProcessInfo>()
    private val activeProcesses = ConcurrentHashMap<ProcessId, Job>()
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var messageIdCounter = 0

    // Persistent state like new.worker.ts currentState.sourcesPhotosInArea.data
    private val sourcesPhotosInArea = ConcurrentHashMap<String, List<PhotoData>>()

    // Store current sources, bounds and range state like new.worker.ts
    private var currentSources: List<SourceConfig> = emptyList()
    private var lastProcessedBounds: Bounds? = null
    private var lastProcessedRange: Double = DEFAULT_RANGE_METERS

    /**
     * Process info for tracking active operations
     */
    private data class ProcessInfo(
        val processId: ProcessId,
        val messageId: Int,
        val priority: Priority,
        val type: ProcessType,
        val startTime: Long,
        val abortFlag: AtomicBoolean = AtomicBoolean(false),
        val cancellationScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
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

        val range = jsonObject["range"]?.jsonPrimitive?.content?.toDoubleOrNull()
            ?: DEFAULT_RANGE_METERS // Default range if not provided

        return AreaData(
            sources = sources,
            bounds = bounds,
            maxPhotos = maxPhotos,
            range = range
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

        // Launch config processing in the process's own cancellable scope
        val job = processInfo.cancellationScope.launch {
            try {
                // Store current sources state like new.worker.ts
                currentSources = config.sources

                // Implement selective clearing like new.worker.ts updatePhotosInArea callback
                val enabledSourceIds = config.sources.filter { it.enabled }.map { it.id }.toSet()

                // Remove photos from disabled sources (like new.worker.ts lines 253-258)
                val sourcesToRemove = this@PhotoWorkerService.sourcesPhotosInArea.keys.filter { !enabledSourceIds.contains(it) }
                sourcesToRemove.forEach { sourceId ->
                    Log.d(TAG, "PhotoWorkerService: Clearing photos from disabled source: $sourceId")
                    this@PhotoWorkerService.sourcesPhotosInArea.remove(sourceId)
                }

                // Send current photos (enabled sources remain visible, disabled sources cleared)
                val allPhotos = this@PhotoWorkerService.sourcesPhotosInArea.values.flatten()
                sendPhotosUpdate(allPhotos, this@PhotoWorkerService.sourcesPhotosInArea.toMap())

            Log.d(TAG, "PhotoWorkerService: Config processing complete - kept ${allPhotos.size} photos from enabled sources")

            // Trigger area update after config to ensure streaming sources load with current bounds
            // This matches the behavior of simplePhotoWorker.ts lines 263-271
            if (lastProcessedBounds != null) {
                Log.d(TAG, "PhotoWorkerService: Queuing area update after config to load streaming sources...")

                // Create area message like web worker does (goes through message queue and priority system)
                // Build JSON manually to match existing pattern (parseAreaData expects this format)
                val areaDataJson = buildJsonObject {
                    putJsonArray("sources") {
                        currentSources.forEach { source ->
                            addJsonObject {
                                put("id", source.id)
                                put("type", source.type)
                                put("enabled", source.enabled)
                                put("url", source.url ?: "")
                            }
                        }
                    }
                    putJsonObject("bounds") {
                        putJsonObject("top_left") {
                            put("lat", lastProcessedBounds!!.top_left.lat)
                            put("lng", lastProcessedBounds!!.top_left.lng)
                        }
                        putJsonObject("bottom_right") {
                            put("lat", lastProcessedBounds!!.bottom_right.lat)
                            put("lng", lastProcessedBounds!!.bottom_right.lng)
                        }
                    }
                    put("maxPhotos", MAX_PHOTOS_IN_AREA)
                    put("range", lastProcessedRange)
                }.toString()

                val areaMessage = WorkerMessage(
                    type = MessageType.PROCESS_AREA,
                    messageId = ++messageIdCounter,
                    processId = "auto_area_after_config_${System.currentTimeMillis()}",
                    priority = 2, // Same priority as normal area updates
                    data = areaDataJson
                )

                // Process through normal message handling (respects priority and queue)
                serviceScope.launch {
                    processAreaMessage(areaMessage, authTokenProvider)
                }
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

        // Store the job for potential cancellation
        activeProcesses[message.processId] = job
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

        // Launch area processing in the process's own cancellable scope
        val job = processInfo.cancellationScope.launch {
            try {
                // Store current bounds and range for post-config area updates (like new.worker.ts)
                lastProcessedBounds = areaData.bounds
                lastProcessedRange = areaData.range

                // Process area photos with per-source loading status callbacks
                val sourcesPhotosInArea = photoOperations.processArea(
                processId = message.processId,
                sources = areaData.sources,
                bounds = areaData.bounds,
                shouldAbort = { processInfo.abortFlag.get() },
                authTokenProvider = authTokenProvider,
                onSourceLoadingStatus = { sourceId, isLoading, progress, error ->
                    sendLoadingStatusEvent(sourceId, isLoading, progress, error)
                }
            )

                if (!processInfo.abortFlag.get()) {
                    // Update persistent state with new photos from area processing
                    this@PhotoWorkerService.sourcesPhotosInArea.putAll(sourcesPhotosInArea)

                    // Apply culling if photos exceed maxPhotos
                    val totalPhotos = this@PhotoWorkerService.sourcesPhotosInArea.values.sumOf { it.size }
                    val finalPhotos = if (totalPhotos > areaData.maxPhotos) {
                        Log.d(TAG, "PhotoWorkerService: Applying culling - $totalPhotos photos > ${areaData.maxPhotos} limit")

                        val gridCuller = CullingGrid(areaData.bounds)
                        val culledPhotos = gridCuller.cullPhotos(this@PhotoWorkerService.sourcesPhotosInArea.toMap(), areaData.maxPhotos)

                        Log.d(TAG, "PhotoWorkerService: Grid culling complete - ${culledPhotos.size} photos selected")
                        culledPhotos
                    } else {
                        this@PhotoWorkerService.sourcesPhotosInArea.values.flatten()
                    }

                    // Send photos update to frontend like new.worker.ts does
                    sendPhotosUpdate(finalPhotos, this@PhotoWorkerService.sourcesPhotosInArea.toMap(), areaData.bounds, areaData.range)
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

        // Store the job for potential cancellation
        activeProcesses[message.processId] = job
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
     * Abort a specific process with proper coroutine cancellation
     */
    private fun abortProcess(processId: ProcessId) {
        Log.d(TAG, "PhotoWorkerService: Aborting process $processId")

        val processInfo = processTable[processId]
        if (processInfo != null) {
            // Set abort flag for legacy shouldAbort() checks
            processInfo.abortFlag.set(true)

            // Cancel the process's coroutine scope properly
            try {
                processInfo.cancellationScope.cancel("Process $processId aborted by higher priority operation")
                Log.d(TAG, "PhotoWorkerService: Cancelled coroutine scope for process $processId")
            } catch (e: Exception) {
                Log.w(TAG, "PhotoWorkerService: Error cancelling scope for process $processId: ${e.message}")
            }
        }

        // Cancel any active coroutine job
        activeProcesses[processId]?.cancel()

        // Clean up tracking maps
        activeProcesses.remove(processId)
        processTable.remove(processId)

        Log.d(TAG, "PhotoWorkerService: Process $processId cleanup complete")
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
    private suspend fun sendPhotosUpdate(
        photos: List<PhotoData>,
        sourcesPhotosInArea: Map<String, List<PhotoData>>,
        bounds: Bounds? = null,
        range: Double? = null
    ) {
        try {
            // Apply angular range culling if bounds and range are available
            val photosInRange = if (bounds != null && range != null) {
                val center = LatLng(
                    lat = (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
                    lng = (bounds.top_left.lng + bounds.bottom_right.lng) / 2
                )
                val rangePhotos = angularRangeCuller.cullPhotosInRange(photos, center, range, MAX_PHOTOS_IN_RANGE).toMutableList()

                // Sort photos in range by bearing for consistent navigation order (like new.worker.ts)
                sortPhotosByBearing(rangePhotos)

                rangePhotos
            } else {
                // For config updates without range info, use the photos as-is
                photos
            }

            // Create photosUpdate message like new.worker.ts sends
            val eventData = app.tauri.plugin.JSObject()
            eventData.put("type", "photosUpdate")
            eventData.put("photosInArea", serializePhotoDataList(photos))
            eventData.put("photosInRange", serializePhotoDataList(photosInRange))
            eventData.put("timestamp", System.currentTimeMillis())

            Log.d(TAG, "PhotoWorkerService: Queuing photosUpdate message with ${photos.size} area photos and ${photosInRange.size} range photos")

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
     * Send loading status event to frontend via Tauri events (like StreamSourceLoader updateLoadingStatus)
     */
    private fun sendLoadingStatusEvent(sourceId: String, isLoading: Boolean, progress: String? = null, error: String? = null) {
        try {
            // Create loading status message like StreamSourceLoader sends
            val eventData = app.tauri.plugin.JSObject()
            eventData.put("sourceId", sourceId)
            eventData.put("isLoading", isLoading)
            if (progress != null) {
                eventData.put("progress", progress)
            }
            if (error != null) {
                eventData.put("error", error)
            }

            Log.d(TAG, "PhotoWorkerService: Queuing loading status for $sourceId: loading=$isLoading, progress=$progress")

            // Use message queue instead of direct event triggering
            plugin?.queueMessage("photo-worker-loading-status", eventData)

        } catch (error: Exception) {
            Log.e(TAG, "PhotoWorkerService: Error creating loading status message", error)
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
                "sizes": ${if (photo.sizes != null) serializeSizes(photo.sizes!!) else "null"},
                "isDevicePhoto": ${photo.isDevicePhoto}
            }
            """.trimIndent()
        }

        return jsonArray
    }

    private fun serializeSizes(sizes: Map<String, PhotoSize>): String {
        val sizesJson = sizes.entries.joinToString(", ") { (key, size) ->
            """
            "$key": {
                "url": "${size.url}",
                "width": ${size.width},
                "height": ${size.height}
            }
            """.trimIndent()
        }
        return "{ $sizesJson }"
    }
}

/**
 * Area processing data structure
 */
@kotlinx.serialization.Serializable
private data class AreaData(
    val sources: List<SourceConfig>,
    val bounds: Bounds,
    val maxPhotos: Int,
    val range: Double
)