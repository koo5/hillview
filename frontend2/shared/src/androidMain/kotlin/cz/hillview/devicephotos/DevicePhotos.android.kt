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
import cz.hillview.plugin.EventLog
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.PhotoUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import cz.hillview.plugin.hvTag

/**
 * The screen's data, straight from the shared Room DB — the same rows the
 * Tauri route reads through cmd.get_device_photos.
 */
class DaoDevicePhotoBrowser(private val context: Context) : DevicePhotoBrowser {
    // The edit/anonymization logic lives with the drain in shared-kt; this
    // is the same instance shape the Tauri plugin's commands use.
    private val logic by lazy { cz.hillview.plugin.PhotoUploadLogic(context) }

    /** Ratings and wanted deletions — see docs/photo-outbox.md. */
    private val outbox by lazy { cz.hillview.plugin.PhotoOutbox(context) }


    override suspend fun page(page: Int, pageSize: Int, filter: PhotoFilter): DevicePhotosPage =
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            val offset = (page - 1) * pageSize
            val rows = filter.status?.let { dao.getPhotosByStatusPaginated(it, pageSize, offset) }
                ?: dao.getPhotosPaginated(pageSize, offset)
            // One query for the whole page rather than two per row: a page of
            // fifty cards was fifty rating lookups and fifty deletion
            // lookups, on the thread that draws the list.
            val wishes = outbox.forPhotos(rows.map { it.id })
            val photos = rows.map { toCard(it, wishes[it.id]) }
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
                    waiting = dao.getPendingUploadCount(),
                    uploading = dao.getUploadingCount(),
                    processing = dao.getProcessingCount(),
                    done = dao.getCompletedUploadCount(),
                    failed = dao.getFailedUploadCount(),
                ),
            )
        }

    /**
     * One row as the screen sees it. Shared by the list and the single-photo
     * screen so a card cannot mean two different things depending on which
     * one drew it.
     */
    private fun toCard(
        it: cz.hillview.plugin.PhotoEntity,
        wishes: cz.hillview.plugin.PhotoWishes?,
    ) = DevicePhotoCard(
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
        // One stat() per visible row: rows outlive their bytes, and such a
        // row can never upload no matter how often it is retried, so it is
        // worth saying so on the card.
        fileMissing = !locatorExists(context, it.path),
        license = it.license,
        anonymization = logic.getPhotoAnonymizationState(it.id)?.state ?: "auto",
        rating = wishes?.rating,
        serverDeletion = when (wishes?.deletion) {
            cz.hillview.plugin.DeletionWish.Pending -> ServerDeletion.Pending
            cz.hillview.plugin.DeletionWish.Pushed -> ServerDeletion.Done
            null -> null
        },
        onServer = it.serverPhotoId != null,
    )

    override suspend fun card(id: String): DevicePhotoCard? = withContext(Dispatchers.IO) {
        val row = PhotoDatabase.getDatabase(context).photoDao().getPhotoById(id)
            ?: return@withContext null
        toCard(row, outbox.forPhotos(listOf(id))[id])
    }

    override suspend fun idForLocator(locator: String): String? = withContext(Dispatchers.IO) {
        val id = PhotoDatabase.getDatabase(context).photoDao().getPhotoByPath(locator)?.id
        android.util.Log.d(hvTag("DevicePhotos"), "row for $locator -> $id")
        id
    }

    override suspend fun cardForMarker(source: String, markerId: String): DevicePhotoCard? =
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            val row = when (source) {
                // A device marker IS the row (DevicePhotoLoader: id =
                // photoEntity.id).
                "device" -> dao.getPhotoById(markerId)
                // A hillview marker carries the server's id; the row that
                // sent it, if this is the device that did, knows it.
                "hillview" -> dao.getPhotoByServerPhotoId(markerId)
                else -> null
            } ?: return@withContext null
            toCard(row, outbox.forPhotos(listOf(row.id))[row.id])
        }

    override suspend fun canRate(): Boolean = withContext(Dispatchers.IO) {
        outbox.currentUserId() != null
    }

    override suspend fun deleteEverywhere(id: String) = withContext(Dispatchers.IO) {
        val row = PhotoDatabase.getDatabase(context).photoDao().getPhotoById(id)
            ?: return@withContext
        // Only when there IS something up there. A wish for a photo the
        // server has never seen can never be pushed — getPushable joins on
        // serverPhotoId — so it would sit forever keeping the row alive as a
        // tombstone for a deletion that has nothing to delete.
        if (row.serverPhotoId != null) {
            outbox.wantDeleted(id, wanted = true, forgetLocally = true)
        }
        delete(id, alsoFile = true)
        PhotoUploadManager(context).reconcile("delete_everywhere")
    }

    override suspend fun counts(): Map<PhotoFilter, Int> = withContext(Dispatchers.IO) {
        val dao = PhotoDatabase.getDatabase(context).photoDao()
        PhotoFilter.entries.associateWith { filter ->
            filter.status?.let { dao.countByUploadStatus(it) } ?: dao.getTotalPhotoCount()
        }
    }

    override suspend fun delete(id: String, alsoFile: Boolean) = withContext(Dispatchers.IO) {
        val dao = PhotoDatabase.getDatabase(context).photoDao()
        // A row with an unpushed server deletion hanging off it is not a row
        // to remove: the outbox wish is a CHILD of it, so dropping it here
        // would cascade the wish away and leave the photo published. The file
        // still goes if that is what was asked; the row stays as a tombstone
        // until the pusher has done its work, and then removes itself.
        val deletionPending = outbox.deletionState(id) == cz.hillview.plugin.DeletionWish.Pending
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
                    android.util.Log.w(hvTag("DevicePhotos"), "could not delete ${row.path}", e)
                }
            }
        }
        if (deletionPending) {
            android.util.Log.i(
                hvTag("DevicePhotos"),
                "keeping row $id until its server deletion has been pushed",
            )
        } else {
            dao.deletePhoto(id)
        }
        Unit
    }

    override suspend fun setRating(id: String, rating: String?) = withContext(Dispatchers.IO) {
        outbox.setRating(id, rating)
        // The row is only pushable once the photo has a server id, so there
        // is nothing to wake for one that has not been uploaded — but for one
        // that has, a rating should not wait for the next capture to nudge
        // the drain awake.
        PhotoUploadManager(context).reconcile("rating")
    }

    override suspend fun setServerDeletion(id: String, wanted: Boolean) = withContext(Dispatchers.IO) {
        // forgetLocally: a photo the user has told the server to forget is
        // one they have finished with here too. The row survives only as the
        // wish's carrier, and the pusher removes it the moment the server
        // confirms — see DELETE_FORGET_LOCALLY.
        outbox.wantDeleted(id, wanted, forgetLocally = wanted)
        // Withdrawing one makes the photo an upload candidate again, and
        // asking for one takes it out of the queue; both change what the
        // schedule should be.
        PhotoUploadManager(context).reconcile("server_deletion")
    }

    override suspend fun retryUploads() {
        withContext(Dispatchers.IO) {
            PhotoUploadManager(context).startAutomaticUpload("retry_button")
        }
    }

    override suspend fun retryUpload(id: String) {
        withContext(Dispatchers.IO) {
            PhotoUploadManager(context).startManualUpload(id)
        }
    }

    override suspend fun setAnonymization(id: String, value: String?) = withContext(Dispatchers.IO) {
        // The same edit the Tauri plugin's create_edit command records; the
        // drain's processPendingEdits turns it into a re-upload (override
        // set, version bumped, status back to pending).
        val action = org.json.JSONObject()
            .put("action", "set_anonymization_override")
            .put("value", value?.let { org.json.JSONArray(it) } ?: org.json.JSONObject.NULL)
        logic.createEdit(id, action)
        EventLog.record("upload", "anonymization -> ${value ?: "auto"} for $id, re-upload queued")
        // Targeted: the edit is applied at the top of the drain, so the row
        // is pending by the time the targeted fetch looks for it. The force
        // path bypasses the gate deliberately — an explicit "upload THIS
        // again" is not automatic uploading.
        PhotoUploadManager(context).startManualUpload(id)
    }

    override suspend fun changeLicense(id: String, license: String) = withContext(Dispatchers.IO) {
        PhotoDatabase.getDatabase(context).photoDao().updateLicense(id, license)
        EventLog.record("upload", "license set to $license for $id")
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

/**
 * A subsampled decode, STREAMED — never the whole file at once.
 *
 * The previous spelling read the entire JPEG into a ByteArray first
 * (`readBytesFromPath`) and decoded from that. For one card at a time that is
 * merely wasteful; for a page of fifty it is fifty multi-megabyte
 * allocations, and for the shutter's confirmation thumbnail it is a 4-25 MB
 * allocation per photo taken, competing with the capture pipeline for exactly
 * the memory it needs. The decoder can read a stream and skip most of it, so
 * it does.
 *
 * Two passes over the stream: one for the dimensions, one for the pixels.
 * The first reads only the JPEG header.
 */
private fun decodeSampled(context: Context, locator: String, targetPx: Int): ImageBitmap? =
    runCatching {
        fun open(): java.io.InputStream? =
            if (locator.startsWith("content:")) {
                context.contentResolver.openInputStream(android.net.Uri.parse(locator))
            } else {
                java.io.File(locator).takeIf { it.exists() }?.inputStream()
            }

        val startedAt = android.os.SystemClock.elapsedRealtime()
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        val opened = open()
        if (opened == null) {
            // Said out loud rather than returning a blank box: a thumbnail
            // that silently does not appear is indistinguishable from one
            // that is still loading, and the difference is the whole
            // question when a row's bytes have gone missing.
            android.util.Log.w(hvTag("DevicePhotos"), "no thumbnail: cannot open $locator")
            return@runCatching null
        }
        // A STATEMENT, not a value: in bounds-only mode decodeStream returns
        // null by design — it fills `bounds` and decodes nothing. Chaining
        // `open()?.use { decodeStream(...) } ?: return null` therefore reads
        // as "the file could not be opened" on every single call, and the
        // thumbnail silently never appears. Cost a measurement run to find.
        opened.use { BitmapFactory.decodeStream(it, null, bounds) }
        val sample = maxOf(1, bounds.outWidth / targetPx.coerceAtLeast(1))
        val decoded = open()?.use {
            BitmapFactory.decodeStream(
                it, null,
                BitmapFactory.Options().apply { inSampleSize = sample },
            )
        }?.asImageBitmap()
        // What this costs, measured where it actually runs. The question "is
        // the shutter's thumbnail too expensive to do in an interval run"
        // only has a phone-shaped answer, and a guess at it is how the
        // decision gets made badly.
        android.util.Log.d(
            hvTag("DevicePhotos"),
            "thumbnail ${bounds.outWidth}px /$sample -> ${targetPx}px in " +
                "${android.os.SystemClock.elapsedRealtime() - startedAt} ms",
        )
        decoded
    }.getOrNull()

@Composable
actual fun PhotoThumbnail(locator: String, modifier: Modifier, targetPx: Int) {
    val context = LocalContext.current
    var bitmap by remember(locator, targetPx) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(locator, targetPx) {
        bitmap = withContext(Dispatchers.IO) {
            decodeSampled(context, locator, targetPx)
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
