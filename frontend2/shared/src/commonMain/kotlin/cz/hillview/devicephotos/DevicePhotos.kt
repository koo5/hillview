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
    /** When the last upload attempt happened, or null if never attempted. */
    val lastAttemptAtMs: Long? = null,
    /** Whatever the last failure said — the reason a row is stuck. */
    val uploadError: String? = null,
    /**
     * The file the row points at is gone. Rows outlive their bytes (a test
     * run deleted, a gallery cleanup, storage reclaimed) and such a row can
     * never upload — it is the main thing worth deleting in bulk.
     */
    val fileMissing: Boolean = false,
    /**
     * The licence THIS photo goes out under, snapshotted at capture. Null on
     * rows taken before licences were per-photo; those still upload under the
     * global setting, which is what the card says.
     */
    val license: String? = null,
)

/**
 * What the list is showing. With tens of thousands of rows, scrolling is
 * not how anyone finds anything — the real questions are "what is stuck",
 * "what failed and why", "what can I delete". So the filter IS the
 * navigation, and its counts are the map.
 */
enum class PhotoFilter(val label: String, val status: String?) {
    All("All", null),
    Pending("Pending", "pending"),
    Failed("Failed", "failed"),
    Uploading("Uploading", "uploading"),
    Processing("Processing", "processing"),
    Completed("Done", "completed"),
}

/**
 * The queue, by stage rather than by lump. "Pending" used to fold three
 * different situations into one number — waiting for a drain, bytes in
 * flight, and uploaded-but-the-server-is-still-processing — and the last
 * of those reads as "stuck" precisely when everything is working
 * (user-raised: a forced upload succeeded and the line still said
 * "1 pending"). A queue display is only reassuring if it moves when the
 * queue does.
 */
data class StatusCounts(
    /** Not yet attempted (or re-queued): waiting for a drain. */
    val waiting: Int,
    /** Bytes in flight right now. */
    val uploading: Int,
    /** On the server, its pipeline still chewing. */
    val processing: Int,
    val done: Int,
    val failed: Int,
) {
    /** What a drain could act on — the Upload-now button's question. */
    val actionable: Int get() = waiting + failed
}

data class DevicePhotosPage(
    val photos: List<DevicePhotoCard>,
    val totalCount: Int,
    val hasMore: Boolean,
    val counts: StatusCounts,
)

/** The screen's data seam — the shared Room DB on Android, empty on desktop. */
interface DevicePhotoBrowser {
    suspend fun page(page: Int, pageSize: Int, filter: PhotoFilter = PhotoFilter.All): DevicePhotosPage

    /** Row counts per filter, for the chips — one cheap COUNT each. */
    suspend fun counts(): Map<PhotoFilter, Int>

    /**
     * Forget a photo. [alsoFile] deletes the bytes too; without it only the
     * row goes, which is what you want for a row whose file is already gone.
     * Never touches the server — a completed upload stays uploaded.
     */
    suspend fun delete(id: String, alsoFile: Boolean)

    /**
     * The original's per-card button is a GLOBAL retry:
     * PhotoUploadManager.startAutomaticUpload("retry_button"), which
     * bypasses the wifi-only constraint.
     */
    suspend fun retryUploads()

    /**
     * Force this one photo out now — bypasses the failed-row backoff, the
     * wifi-only constraint and the auto-upload toggle, none of which an
     * explicit "upload THIS" tap should be silently swallowed by.
     */
    suspend fun retryUpload(id: String)

    /**
     * Relicense a single photo. A DIVERGENCE from the original, where the
     * licence is one global setting read at upload time: here it is a
     * property of the photo, fixed when the shutter fired, so a setting
     * change cannot silently relicense a queue.
     *
     * Only offered while the row has not gone out — once the server has it,
     * its copy is the one that counts and there is no endpoint to amend it.
     */
    suspend fun changeLicense(id: String, license: String)
}

/** A row whose licence is still ours to change (not yet on the server). */
fun licenseEditable(status: String): Boolean =
    status == "pending" || status == "failed"

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
    // "processing" deliberately falls through to the raw status, as in the
    // original — its wording is ported, quirks and all, and a lone
    // capitalisation here would be an undeclared divergence. (Reverted once
    // already, caught by DevicePhotosRulesTest.)
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
