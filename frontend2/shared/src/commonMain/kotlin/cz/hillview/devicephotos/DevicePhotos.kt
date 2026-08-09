package cz.hillview.devicephotos

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.roundToLong

/** One row of the device-photos screen — a capture and its upload fate. */
data class DevicePhotoCard(
    val id: String,
    val filename: String,
    /** Absolute path or content:// URI — whatever the storage chain produced. */
    val locator: String,
    val sizeBytes: Long,
    val capturedAtMs: Long,
    val latitude: Double,
    val longitude: Double,
    val bearingDeg: Double?,
    val width: Int,
    val height: Int,
    val uploadStatus: String,
    val retryCount: Int,
)

data class StatusCounts(val pending: Int, val done: Int, val failed: Int)

data class DevicePhotosPage(
    val photos: List<DevicePhotoCard>,
    val totalCount: Int,
    val hasMore: Boolean,
    val counts: StatusCounts,
)

/** The screen's data seam — the shared Room DB on Android, empty on desktop. */
interface DevicePhotoBrowser {
    suspend fun page(page: Int, pageSize: Int): DevicePhotosPage

    /**
     * The original's per-card button is a GLOBAL retry:
     * PhotoUploadManager.startAutomaticUpload("retry_button"), which
     * bypasses the wifi-only constraint.
     */
    suspend fun retryUploads()
}

/** The thumbnail: decoded from the locator on Android, a placeholder elsewhere. */
@Composable
expect fun PhotoThumbnail(locator: String, modifier: Modifier)

// --- the route's little display rules, ported verbatim ---

/** Status → label, exactly the original's wording. */
fun uploadStatusLabel(status: String): String = when (status) {
    "completed" -> "Completed"
    "pending" -> "upload Pending"
    "uploading" -> "Uploading"
    "failed" -> "upload Failed"
    else -> status
}

/** Status → colour, the original's palette. */
fun uploadStatusColor(status: String): Color = when (status) {
    "completed" -> Color(0xFF10B981)
    "pending" -> Color(0xFFF59E0B)
    "uploading" -> Color(0xFF3B82F6)
    "failed" -> Color(0xFFEF4444)
    else -> Color(0xFF6B7280)
}

/**
 * The original's formatFileSize: toFixed(2) then parseFloat, i.e. two
 * decimals with trailing zeros stripped.
 */
fun formatFileSize(bytes: Long): String {
    if (bytes == 0L) return "0 B"
    val units = listOf("B", "KB", "MB", "GB")
    val index = minOf(
        (ln(bytes.toDouble()) / ln(1024.0)).toInt(),
        units.size - 1,
    )
    val value = bytes / 1024.0.pow(index)
    val rounded = (value * 100).roundToLong() / 100.0
    val text = if (rounded == rounded.toLong().toDouble()) {
        rounded.toLong().toString()
    } else {
        rounded.toString()
    }
    return "$text ${units[index]}"
}

/** Locale date/time — java.text on both JVM-family targets. */
expect fun formatLocalDate(epochMs: Long): String
expect fun formatLocalTime(epochMs: Long): String
