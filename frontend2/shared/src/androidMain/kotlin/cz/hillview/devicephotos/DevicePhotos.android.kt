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

    override suspend fun page(page: Int, pageSize: Int): DevicePhotosPage =
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            val photos = dao.getPhotosPaginated(pageSize, (page - 1) * pageSize).map {
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
                )
            }
            val total = dao.getTotalPhotoCount()
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

    override suspend fun retryUploads() {
        withContext(Dispatchers.IO) {
            PhotoUploadManager(context).startAutomaticUpload("retry_button")
        }
    }
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
