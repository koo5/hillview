package cz.hillview.devicephotos

import android.content.Context
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.PhotoUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * The screen's data, straight from the shared Room DB — the same rows the
 * Tauri route reads through cmd.get_device_photos.
 */
class DaoDevicePhotoBrowser(private val context: Context) : DevicePhotoBrowser {

    override suspend fun page(page: Int, pageSize: Int, filter: PhotoFilter): DevicePhotosPage =
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            val offset = (page - 1) * pageSize
            val rows = filter.status?.let { dao.getPhotosByStatusPaginated(it, pageSize, offset) }
                ?: dao.getPhotosPaginated(pageSize, offset)
            val photos = rows.map {
                DevicePhotoCard(
                    id = it.id,
                    filename = it.filename,
                    locator = it.path,
                    sizeBytes = it.fileSize,
                    capturedAtMs = it.capturedAt,
                    latitude = it.latitude,
                    longitude = it.longitude,
                    // 0 is the DB's "unset" for bearing, as everywhere.
                    bearingDeg = it.bearing.takeIf { b -> b != 0.0 },
                    width = it.width,
                    height = it.height,
                    uploadStatus = it.uploadStatus,
                    retryCount = it.retryCount,
                    lastAttemptAtMs = it.lastUploadAttempt.takeIf { t -> t > 0 },
                    uploadError = it.uploadError.takeIf { e -> e.isNotBlank() },
                    // One stat() per visible row: rows outlive their bytes,
                    // and such a row can never upload no matter how often it
                    // is retried, so it is worth saying so on the card.
                    fileMissing = !locatorExists(context, it.path),
                )
            }
            val total = if (filter.status == null) {
                dao.getTotalPhotoCount()
            } else {
                dao.countByUploadStatus(filter.status)
            }
            DevicePhotosPage(
                photos = photos,
                totalCount = total,
                hasMore = page * pageSize < total,
                counts = StatusCounts(
                    pending = dao.getPendingUploadCount() + dao.getUploadingCount() +
                        dao.getProcessingCount(),
                    done = dao.getCompletedUploadCount(),
                    failed = dao.getFailedUploadCount(),
                ),
            )
        }

    override suspend fun counts(): Map<PhotoFilter, Int> = withContext(Dispatchers.IO) {
        val dao = PhotoDatabase.getDatabase(context).photoDao()
        PhotoFilter.entries.associateWith { filter ->
            filter.status?.let { dao.countByUploadStatus(it) } ?: dao.getTotalPhotoCount()
        }
    }

    override suspend fun delete(id: String, alsoFile: Boolean) = withContext(Dispatchers.IO) {
        val dao = PhotoDatabase.getDatabase(context).photoDao()
        if (alsoFile) {
            dao.getPhotoById(id)?.let { row ->
                try {
                    if (row.path.startsWith("content:")) {
                        context.contentResolver.delete(android.net.Uri.parse(row.path), null, null)
                    } else {
                        java.io.File(row.path).delete()
                    }
                } catch (e: Exception) {
                    // The row goes regardless: a file we cannot delete is
                    // exactly as unwanted as one we can.
                    android.util.Log.w("DevicePhotos", "could not delete ${row.path}", e)
                }
            }
        }
        dao.deletePhoto(id)
    }

    override suspend fun retryUploads() {
        withContext(Dispatchers.IO) {
            PhotoUploadManager(context).startAutomaticUpload("retry_button")
        }
    }
}

/** Does the locator still resolve to bytes? Path or content:// alike. */
private fun locatorExists(context: Context, locator: String): Boolean = try {
    if (locator.startsWith("content:")) {
        context.contentResolver.openAssetFileDescriptor(
            android.net.Uri.parse(locator), "r",
        )?.use { true } ?: false
    } else {
        java.io.File(locator).exists()
    }
} catch (e: Exception) {
    false
}

@Composable
actual fun PhotoThumbnail(locator: String, modifier: Modifier) {
    val context = LocalContext.current
    var bitmap by remember(locator) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(locator) {
        bitmap = withContext(Dispatchers.IO) {
            runCatching {
                // readBytesFromPath handles both file paths and content://
                // (shared-kt, the same branch the upload path uses).
                val bytes = PhotoUtils.readBytesFromPath(context, locator)
                    ?: return@runCatching null
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
                val sample = maxOf(1, bounds.outWidth / 512)
                BitmapFactory.decodeByteArray(
                    bytes, 0, bytes.size,
                    BitmapFactory.Options().apply { inSampleSize = sample },
                )?.asImageBitmap()
            }.getOrNull()
        }
    }
    val current = bitmap
    if (current != null) {
        Image(
            bitmap = current,
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = modifier,
        )
    } else {
        Box(modifier)
    }
}
