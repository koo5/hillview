package cz.hillview.plugin

import kotlinx.serialization.Serializable

/**
 * Photo Worker Types - Core data structures for photo worker implementation
 *
 * This is a faithful translation of TypeScript photoWorkerTypes.ts to maintain
 * 100% compatibility with the existing Web Worker implementation.
 */

@Serializable
enum class MessageType {
    PROCESS_CONFIG,
    PROCESS_AREA,
    ABORT_PROCESS,
    CLEANUP
}

@Serializable
enum class ResponseType {
    PROCESS_STARTED,
    CONFIG_COMPLETE,
    AREA_COMPLETE,
    PROCESS_ABORTED,
    CLEANUP_COMPLETE,
    ERROR
}

// Type aliases for clarity and consistency with TypeScript
typealias ProcessId = String
typealias SourceId = String
typealias Priority = Int
typealias FileHash = String
typealias PhotoIndex = Int
typealias CellKey = String

@Serializable
data class WorkerMessage(
    val type: MessageType,
    val messageId: Int,
    val processId: ProcessId,
    val priority: Priority,
    val data: String // JSON string for flexible data structure
)

@Serializable
data class WorkerResponse(
    val messageId: Int,
    val type: ResponseType,
    val processId: ProcessId,
    val data: String // JSON string for flexible data structure
)

@Serializable
data class ConfigCompleteData(
    val photos: List<PhotoData>
)

@Serializable
data class AreaCompleteData(
    val photos: List<PhotoData>,
    val sourcesPhotosInArea: Map<String, List<PhotoData>>
)

@Serializable
data class LatLng(
    val lat: Double,
    val lng: Double
)

@Serializable
data class Bounds(
    val top_left: LatLng,
    val bottom_right: LatLng
)

@Serializable
data class PhotoData(
    val id: String,
    val uid: String,
    val source_type: String,
    val file: String? = null,
    val url: String? = null,
    val coord: LatLng,
    val bearing: Double,
    val altitude: Double? = null,
    val source: SourceConfig,
    val isDevicePhoto: Boolean = false,
    val timestamp: Long? = null,
    val accuracy: Double? = null,
    val fileHash: String? = null,
    val range_distance: Double? = null // Added during range culling
)

@Serializable
data class SourceConfig(
    val id: String,
    val name: String,
    val type: String, // "device" or "stream"
    val enabled: Boolean,
    val color: String,
    val url: String? = null,
    val subtype: String? = null,
    val requests: List<String> = emptyList()
)

// Process management types
enum class ProcessType {
    CONFIG, AREA, SOURCES_PHOTOS_IN_AREA
}

data class ProcessInfo(
    val id: String,
    val type: ProcessType,
    val messageId: Int,
    val startTime: Long,
    var shouldAbort: Boolean = false
)


@Serializable
data class ConfigData(
    val sources: List<SourceConfig>,
    val expectedWorkerVersion: String? = null
)

@Serializable
data class PhotoResponse(
    val photosInArea: List<PhotoData>,
    val photosInRange: List<PhotoData>,
    val hasMore: Boolean,
    val error: String? = null
)

// State management types
data class StateData<T>(
    var data: T? = null,
    var lastUpdateId: Int = -1,
    var lastProcessedId: Int = -1
)

// Stream message types for EventSource
@Serializable
sealed class StreamMessage {
    @Serializable
    data class Photos(val photos: List<PhotoData>) : StreamMessage()

    @Serializable
    data class StreamComplete(val total: Int? = null) : StreamMessage()

    @Serializable
    data class Error(val message: String) : StreamMessage()
}

