package cz.hillview.upload

import android.content.Context
import android.graphics.BitmapFactory
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadLogic
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.PhotoUtils
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * Capture → the shared-kt upload stack (see /shared-kt/README.md): registers
 * the photo in the shared Room DB (PhotoUploadLogic.registerCapturedPhoto —
 * the same ingestion the Tauri app's addPhotoToDatabase command uses, with
 * this class doing what Rust does there: MD5, dimensions, file size) and
 * pokes PhotoUploadManager, whose WorkManager jobs run the drain (coalescing
 * windows, wifi-only, foreground promotion, status sync). Stats come
 * straight from the shared DB's upload-status counts.
 */
class SharedStackUploadPipeline(
    private val context: Context,
) : UploadPipeline {
    private val _stats = MutableStateFlow(QueueStats())
    override val stats: StateFlow<QueueStats> = _stats.asStateFlow()

    private val uploadLogic by lazy { PhotoUploadLogic(context) }

    override suspend fun onPhotoCaptured(upload: PendingUpload) {
        withContext(Dispatchers.IO) {
            val file = File(upload.filePath)
            val fileHash = PhotoUtils.calculateFileHash(file)
                ?: throw IllegalStateException("could not hash ${upload.filePath}")
            // Decode bounds only — no bitmap allocation.
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(upload.filePath, bounds)

            uploadLogic.registerCapturedPhoto(
                id = null,
                filename = upload.filename,
                path = upload.filePath,
                latitude = upload.latitude ?: 0.0,
                longitude = upload.longitude ?: 0.0,
                altitude = upload.altitude,
                bearing = upload.bearing,
                capturedAt = file.lastModified(),
                // EXIF GPSHPositioningError carries the real accuracy; the DB
                // column mirrors the Tauri AddPhotoArgs default when absent.
                accuracy = 0.0,
                width = bounds.outWidth.coerceAtLeast(0),
                height = bounds.outHeight.coerceAtLeast(0),
                fileSize = file.length(),
                fileHash = fileHash,
            )
            PhotoUploadManager(context).startAutomaticUpload("capture")
        }
        refreshStats()
    }

    override suspend fun refreshStats() {
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            _stats.value = QueueStats(
                pending = dao.getPendingUploadCount() + dao.getUploadingCount() +
                    dao.getProcessingCount(),
                done = dao.getCompletedUploadCount(),
                failed = dao.getFailedUploadCount(),
            )
        }
    }

}
