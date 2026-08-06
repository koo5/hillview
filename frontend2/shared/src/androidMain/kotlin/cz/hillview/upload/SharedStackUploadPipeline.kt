package cz.hillview.upload

import android.content.Context
import android.graphics.BitmapFactory
import android.util.Log
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadLogic
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.PhotoUtils
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
private const val TAG = "SharedStackUpload"

class SharedStackUploadPipeline(
    private val context: Context,
) : UploadPipeline {
    private val _stats = MutableStateFlow(QueueStats())
    override val stats: StateFlow<QueueStats> = _stats.asStateFlow()

    private val uploadLogic by lazy { PhotoUploadLogic(context) }

    override suspend fun onPhotoCaptured(upload: PendingUpload) {
        try {
            withContext(Dispatchers.IO) {
                // filePath is a locator: an absolute path, or a content:// URI
                // when the capture went through MediaStore. Everything below
                // works off the bytes, so both are handled the same way — and
                // the shared upload path reads them the same way too.
                val bytes = PhotoUtils.readBytesFromPath(context, upload.filePath)
                    ?: throw IllegalStateException("could not read ${upload.filePath}")
                // Decode bounds only — no bitmap allocation.
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)

                uploadLogic.registerCapturedPhoto(
                    id = null,
                    filename = upload.filename,
                    path = upload.filePath,
                    latitude = upload.latitude ?: 0.0,
                    longitude = upload.longitude ?: 0.0,
                    altitude = upload.altitude,
                    bearing = upload.bearing,
                    capturedAt = upload.capturedAtMs ?: System.currentTimeMillis(),
                    // EXIF GPSHPositioningError carries the real accuracy; the DB
                    // column mirrors the Tauri AddPhotoArgs default when absent.
                    accuracy = 0.0,
                    width = bounds.outWidth.coerceAtLeast(0),
                    height = bounds.outHeight.coerceAtLeast(0),
                    fileSize = bytes.size.toLong(),
                    fileHash = PhotoUtils.calculateHash(bytes),
                )
                PhotoUploadManager(context).startAutomaticUpload("capture")
            }
        } catch (e: Exception) {
            // A photo that can't be ingested must not take the app down —
            // the file is still on disk, and the drain's directory scan or a
            // later retry can pick it up.
            Log.e(TAG, "could not ingest ${upload.filePath}", e)
            _stats.value = _stats.value.copy(lastError = e.message ?: "capture ingest failed")
            return
        }
        refreshStats()
    }

    private var lastStatusSyncMs = 0L

    override suspend fun refreshStats() {
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()

            // While photos sit in server-side processing, re-query their
            // status (rate-limited — the stats poll runs every ~2s) so the
            // visible counts converge without waiting for the next drain.
            // The Tauri app gets the same effect from its my-photos page;
            // background convergence still rides the post-drain sync worker.
            if (dao.getProcessingCount() > 0) {
                val now = System.currentTimeMillis()
                if (now - lastStatusSyncMs > 10_000) {
                    lastStatusSyncMs = now
                    try {
                        uploadLogic.syncProcessingPhotosStatus()
                    } catch (e: Exception) {
                        // The stats poll must never throw; the next drain's
                        // sync worker remains the fallback.
                    }
                }
            }

            _stats.value = QueueStats(
                pending = dao.getPendingUploadCount() + dao.getUploadingCount() +
                    dao.getProcessingCount(),
                done = dao.getCompletedUploadCount(),
                failed = dao.getFailedUploadCount(),
            )
        }
    }

}
