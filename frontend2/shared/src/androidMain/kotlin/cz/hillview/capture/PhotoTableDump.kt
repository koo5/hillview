package cz.hillview.capture

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import cz.hillview.plugin.EventLog
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoEntity
import cz.hillview.plugin.accuracyMOrNull
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.BufferedInputStream
import java.io.IOException
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import android.util.AtomicFile
import cz.hillview.plugin.hvTag

/**
 * The photos table, written out beside the photos so they survive the app.
 *
 * The problem this exists for (user-raised, 2026-09-08): the stamp — where a
 * photo was taken, which way the camera faced, how it was exposed — lives in
 * the photos TABLE, and the table lives in the app's private database. A
 * photo saved to DCIM survives an uninstall; the row that gives it meaning
 * does not. Without EXIF in the file (the fast-write default, see
 * UploadSettings.writeExif) the surviving JPEG is then a picture of
 * somewhere, taken at some time, pointing some way.
 *
 * So the table is dumped to a public folder, unconditionally and with no
 * setting to turn it off — "in all cases", because a safety net that is off
 * by default is not one. That is a deliberate departure from the geo-tracking
 * export next door (GeoTrackingManager.writeExportCsv), which is opt-in and
 * asks for a folder: a location history that outlives the app is a privacy
 * decision to put to the user, whereas a manifest of the photos they took and
 * are publishing is the same data as the photos themselves.
 *
 * The Tauri app needs none of this: it holds the JPEG bytes in memory and
 * splices an EXIF segment in before writing (device_photos.rs), so its files
 * are self-describing at no extra cost. CameraX writes the file itself, which
 * is why an EXIF pass here means copying the whole 4–25 MB file per shot —
 * the reason the default is off, and therefore the reason for this file.
 */
object PhotoTableDump {

    private val TAG = hvTag("PhotoTableDump")
    private const val PREFS = "hillview_photo_dump"
    private const val PREF_SHARDS = "last_shard_count"
    private const val PREF_AT = "last_dump_at"
    private const val PREF_WHERE = "last_dump_where"
    private const val PREF_COUNT = "last_dump_count"
    private const val PREF_DELTA_FORMAT = "delta_format"
    private const val PREF_ACTIVE_SHARD = "active_shard"
    private const val PREF_ACTIVE_ROWS = "active_rows"
    private const val PREF_CHANGE_CHECKPOINT = "change_checkpoint"
    private const val PREF_LEGACY_SHARDS = "legacy_shard_count"

    /**
     * The active MediaStore row for each segment, replaced only after staging
     * completes so a failed write leaves the previous complete CSV available.
     */
    private const val PREF_URIS = "last_shard_uris"

    /** Whether the last write landed somewhere that survives an uninstall. */
    private const val PREF_DURABLE = "last_dump_durable"

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val writing = Mutex()
    private val captureDumpRequests = Channel<Unit>(capacity = Channel.CONFLATED)

    /**
     * Wire the triggers. Called once from the Application.
     *
     * Three of them, and the same reasoning as the geo dump's: leaving the
     * app is when the file most needs to be current; app start catches up
     * after a crash or a swipe-away that skipped that; and the capture pulse
     * bounds the loss inside a shoot that does neither.
     *
     * Only the capture pulse is SPACED. App start and backgrounding check the
     * coalesced SQLite change queue and return without reading photo rows when
     * nothing changed. Captures arrive by the thousand, so their trigger yields
     * as the table grows.
     */
    fun install(context: Context, captureEvents: cz.hillview.capture.CaptureEvents) {
        val app = context.applicationContext
        requestDump(app, "app start")
        ProcessLifecycleOwner.get().lifecycle.addObserver(
            object : DefaultLifecycleObserver {
                override fun onStop(owner: LifecycleOwner) = requestDump(app, "background")
            },
        )
        scope.launch {
            captureEvents.captured.collect { captureDumpRequests.trySend(Unit) }
        }
        scope.launch {
            for (ignored in captureDumpRequests) {
                runDumpRequest(app, "capture", spaced = true, force = false)
            }
        }
    }

    /**
     * Write the changed photo states since the previous successful dump.
     *
     * SQLite triggers coalesce edits by photo ID, including physical deletes.
     * Each output row carries a monotonically increasing change ID and an
     * upsert/delete action. Readers apply rows in order and keep the latest
     * state for each ID. A segment is capped at [PHOTO_DUMP_SHARD_ROWS] rows;
     * later dumps replace only the active segment.
     *
     * [spaced] adds the size-scaled interval on top (see
     * [photoDumpIntervalMs]) — the capture pulse's freshness/IO tradeoff.
     * [force] is the manual button, which queues a current state for every
     * photo even when nothing changed, because the file may be missing.
     */
    fun requestDump(
        context: Context,
        reason: String,
        spaced: Boolean = false,
        force: Boolean = false,
    ) {
        val app = context.applicationContext
        scope.launch {
            runDumpRequest(app, reason, spaced, force)
        }
    }

    private suspend fun runDumpRequest(
        app: Context,
        reason: String,
        spaced: Boolean,
        force: Boolean,
    ) {
        writing.withLock {
            try {
                dumpNow(app, reason, spaced, force)
            } catch (e: Exception) {
                Log.w(TAG, "dump ($reason) failed", e)
                EventLog.record("export", "photo table dump FAILED: ${e.message}")
            }
        }
    }

    internal fun dumpNow(app: Context, reason: String, spaced: Boolean, force: Boolean) {
        val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val database = PhotoDatabase.getDatabase(app)
        val dao = database.photoDao()
        val total = dao.getTotalPhotoCount()
        if (!force && spaced && now - prefs.getLong(PREF_AT, 0L) < photoDumpIntervalMs(total)) return

        val db = database.openHelper.writableDatabase
        if (force) queueAllPhotosForExport(db)

        val oldUris = prefs.getString(PREF_URIS, "").orEmpty().split(",")
        val outputUris = oldUris.toMutableList()
        val wasDeltaFormat = prefs.getBoolean(PREF_DELTA_FORMAT, false)
        if (!wasDeltaFormat && total > 0 && pendingPhotoChanges(db, 1).isEmpty()) {
            // Recovery for an install whose preferences or ledger predate the
            // incremental format: establish a baseline once, then stay delta-only.
            queueAllPhotosForExport(db)
        }
        val oldShardCount = prefs.getInt(PREF_SHARDS, 0)
        val legacyShardCount = if (wasDeltaFormat) {
            prefs.getInt(PREF_LEGACY_SHARDS, 0)
        } else {
            oldShardCount
        }
        var shard = prefs.getInt(PREF_ACTIVE_SHARD, 0)
        var activeRows = prefs.getInt(PREF_ACTIVE_ROWS, 0)
        var checkpoint = prefs.getLong(PREF_CHANGE_CHECKPOINT, 0L)
        var shards = if (wasDeltaFormat) oldShardCount else 0
        val previousWhere = prefs.getString(PREF_WHERE, null)
        var where = previousWhere
        var durable = prefs.getBoolean(PREF_DURABLE, false)
        var writtenRows = 0

        if (wasDeltaFormat) {
            val activeUri = resolveSegmentUri(app, shard, outputUris)
            readDeltaMetadata(app, activeUri, previousWhere, photoDumpFileName(shard))?.let { metadata ->
                checkpoint = maxOf(checkpoint, metadata.checkpoint)
                activeRows = metadata.rows
                if (activeRows >= PHOTO_DUMP_SHARD_ROWS) {
                    shard++
                    activeRows = 0
                }
                prefs.edit().putLong(PREF_CHANGE_CHECKPOINT, checkpoint)
                    .putInt(PREF_ACTIVE_SHARD, shard).putInt(PREF_ACTIVE_ROWS, activeRows).commit()
            }
            // If the process died after publishing a complete staged file but
            // before clearing its queue, its on-file checkpoint makes this safe.
            acknowledgePhotoChanges(db, checkpoint)
        }

        // The old snapshot's files become the first log segments. On an upgraded
        // install, the migration queued every existing row; the first write
        // replaces each old segment through a staged, complete replacement.
        if (!wasDeltaFormat && total == 0) {
            val firstUri = resolveSegmentUri(app, 0, outputUris)
            val result = writeCsvAtomic(app, photoDumpFileName(0), firstUri) { out ->
                val writer = out.bufferedWriter(Charsets.UTF_8)
                writer.write(deltaFilePrefix(0L, 0))
                writer.write(photoTableDeltaHeader())
                writer.flush()
            }
            where = result.where
            durable = result.durable
            while (outputUris.isEmpty()) outputUris += ""
            outputUris[0] = result.uri.orEmpty()
            prefs.edit().putBoolean(PREF_DELTA_FORMAT, true)
                .putInt(PREF_ACTIVE_SHARD, 0).putInt(PREF_ACTIVE_ROWS, 0)
                .putLong(PREF_CHANGE_CHECKPOINT, 0L).putInt(PREF_SHARDS, 1)
                .putInt(PREF_LEGACY_SHARDS, legacyShardCount)
                .putString(PREF_URIS, outputUris.joinToString(","))
                .putString(PREF_WHERE, where).putBoolean(PREF_DURABLE, durable)
                .putLong(PREF_AT, now).putInt(PREF_COUNT, total).commit()
            shards = 1
        }

        while (true) {
            val roomInSegment = PHOTO_DUMP_SHARD_ROWS - activeRows
            if (roomInSegment <= 0) {
                shard++
                activeRows = 0
                continue
            }
            val changes = pendingPhotoChanges(db, roomInSegment)
            if (changes.isEmpty()) break

            val fileName = photoDumpFileName(shard)
            val previousUri = resolveSegmentUri(app, shard, outputUris)
            val isExistingDeltaSegment = wasDeltaFormat || writtenRows > 0 || shard > 0
            val nextRows = activeRows + changes.size
            val nextCheckpoint = maxOf(checkpoint, changes.last().changeId)
            val result = writeCsvAtomic(app, fileName, previousUri) { output ->
                val writer = output.bufferedWriter(Charsets.UTF_8)
                writer.write(deltaFilePrefix(nextCheckpoint, nextRows))
                if (isExistingDeltaSegment && activeRows > 0) {
                    writer.flush()
                    if (!copyAfterFirstLine(app, previousUri, previousWhere, fileName, output)) {
                        throw IOException("could not read the current photo-index segment")
                    }
                } else {
                    writer.write(photoTableDeltaHeader())
                }
                val rowText = StringBuilder(1_200)
                for (batch in changes.chunked(32)) {
                    val photosById = database.photoDao()
                        .getPhotosByIds(batch.map { it.photoId })
                        .associateBy { it.id }
                    for (change in batch) {
                        rowText.setLength(0)
                        val photo = photosById[change.photoId]
                        if (photo == null) {
                            appendPhotoTableTombstone(rowText, change.photoId, change.changeId)
                        } else {
                            appendPhotoTableDeltaRow(rowText, photo, change.changeId)
                        }
                        writer.append(rowText)
                    }
                }
                writer.flush()
            }

            // The staged file is complete before it replaces the active segment.
            // Persist its checkpoint first; a restart can then safely clear any
            // matching ledger rows left by a crash between these two operations.
            checkpoint = nextCheckpoint
            activeRows = nextRows
            where = result.where
            durable = result.durable
            while (outputUris.size <= shard) outputUris += ""
            outputUris[shard] = result.uri.orEmpty()
            shards = maxOf(shards, shard + 1)
            val saved = prefs.edit().putBoolean(PREF_DELTA_FORMAT, true)
                .putLong(PREF_CHANGE_CHECKPOINT, checkpoint)
                .putInt(PREF_ACTIVE_SHARD, shard).putInt(PREF_ACTIVE_ROWS, activeRows)
                .putInt(PREF_SHARDS, shards).putString(PREF_URIS, outputUris.joinToString(","))
                .putInt(PREF_LEGACY_SHARDS, legacyShardCount)
                .putBoolean(PREF_DURABLE, durable).putString(PREF_WHERE, where)
                .putLong(PREF_AT, now).putInt(PREF_COUNT, total).commit()
            if (!saved) throw IOException("could not save photo-index checkpoint")
            acknowledgePhotoChanges(db, checkpoint)
            writtenRows += changes.size
            if (activeRows == PHOTO_DUMP_SHARD_ROWS) {
                shard++
                activeRows = 0
                prefs.edit().putInt(PREF_ACTIVE_SHARD, shard).putInt(PREF_ACTIVE_ROWS, 0).commit()
            }
        }

        // Once the migration's one-time seed has drained, remove obsolete tail
        // snapshot files that no longer have a corresponding delta segment.
        if (legacyShardCount > shards) {
            for (oldShard in shards until legacyShardCount) {
                deleteCsv(app, photoDumpFileName(oldShard))
            }
            prefs.edit().putInt(PREF_LEGACY_SHARDS, shards).commit()
        }
        prefs.edit().putLong(PREF_AT, now).putInt(PREF_COUNT, total).commit()
        Log.i(TAG, "exported $writtenRows changed photo rows to $shards file(s) ($reason) -> $where")
        if (where != null && where != previousWhere) {
            EventLog.record(
                "export",
                if (durable) "photo index → $where"
                else "photo index → $where — app-private, will NOT survive an uninstall",
            )
        }
    }

    private data class PendingChange(val photoId: String, val changeId: Long)
    private data class DeltaMetadata(val checkpoint: Long, val rows: Int)

    private fun pendingPhotoChanges(
        db: androidx.sqlite.db.SupportSQLiteDatabase,
        limit: Int,
    ): List<PendingChange> {
        val cursor = db.query(
            "SELECT photoId, changeId FROM photo_export_changes " +
                "ORDER BY changeId, photoId LIMIT ?",
            arrayOf(limit),
        )
        return cursor.use {
            buildList {
                while (it.moveToNext()) add(PendingChange(it.getString(0), it.getLong(1)))
            }
        }
    }

    private fun acknowledgePhotoChanges(
        db: androidx.sqlite.db.SupportSQLiteDatabase,
        checkpoint: Long,
    ) {
        db.execSQL("DELETE FROM photo_export_changes WHERE changeId <= ?", arrayOf(checkpoint))
    }

    /** A forced manual export queues the current state of every row once. */
    private fun queueAllPhotosForExport(db: androidx.sqlite.db.SupportSQLiteDatabase) {
        db.beginTransaction()
        try {
            // The AFTER UPDATE trigger assigns a fresh sequence to each row and
            // coalesces it with any already-pending change for that photo.
            db.execSQL("UPDATE photos SET id = id")
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun copyAfterFirstLine(
        app: Context,
        uri: String?,
        path: String?,
        fileName: String,
        output: OutputStream,
    ): Boolean {
        val input = uri?.let { app.contentResolver.openInputStream(Uri.parse(it)) }
            ?: path?.let(::File)?.let { reported ->
                val directory = if (reported.isDirectory) reported else reported.parentFile
                directory?.let { File(it, fileName) }?.takeIf { it.isFile }?.inputStream()
            }
            ?: return false
        BufferedInputStream(input).use { source ->
            // The first line is the per-replacement checkpoint. The CSV header
            // and records after it can be copied byte-for-byte, including JSON
            // cells that contain quoted newlines.
            var byte: Int
            do {
                byte = source.read()
            } while (byte >= 0 && byte != '\n'.code)
            if (byte < 0) return false
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val read = source.read(buffer)
                if (read < 0) break
                output.write(buffer, 0, read)
            }
        }
        return true
    }

    private fun readDeltaMetadata(
        app: Context,
        uri: String?,
        path: String?,
        fileName: String,
    ): DeltaMetadata? {
        val input = uri?.let { app.contentResolver.openInputStream(Uri.parse(it)) }
            ?: path?.let(::File)?.let { reported ->
                val directory = if (reported.isDirectory) reported else reported.parentFile
                directory?.let { File(it, fileName) }?.takeIf { it.isFile }?.inputStream()
            }
            ?: return null
        return BufferedInputStream(input).use { source ->
            val line = buildString {
                while (length < 256) {
                    val byte = source.read()
                    if (byte < 0 || byte == '\n'.code) break
                    append(byte.toChar())
                }
            }
            val match = Regex("^#hillview_photo_delta=1,checkpoint=(\\d+),rows=(\\d+)$")
                .matchEntire(line) ?: return@use null
            DeltaMetadata(match.groupValues[1].toLong(), match.groupValues[2].toInt())
        }
    }

    private fun resolveSegmentUri(app: Context, shard: Int, uris: MutableList<String>): String? {
        val remembered = uris.getOrNull(shard)?.takeIf { it.isNotEmpty() }
        if (remembered != null && canReadUri(app, remembered)) return remembered
        val relativePath = "${Environment.DIRECTORY_DOCUMENTS}/${PhotoStorage.folderBase}/"
        val found = findInMediaStore(app, relativePath, photoDumpFileName(shard))?.toString()
        if (found != null) {
            while (uris.size <= shard) uris += ""
            uris[shard] = found
        }
        return found
    }

    private fun canReadUri(app: Context, uri: String): Boolean = try {
        app.contentResolver.openInputStream(Uri.parse(uri))?.use { true } ?: false
    } catch (_: Exception) {
        false
    }

    /**
     * Write it now and say what happened — the settings button, which wants
     * an answer rather than a fire-and-forget. Forced: the usual reason to
     * press it is that the file is not where it should be, which the content
     * hash cannot know.
     */
    suspend fun dumpNowForResult(context: Context): String {
        val app = context.applicationContext
        // IO, explicitly. This is a suspend function, which says nothing
        // about WHICH thread — it inherits the caller's, and the caller is a
        // button in a Compose screen, so the caller's is the main thread.
        // Room refuses that outright, so the button threw every time it was
        // pressed and reported "failed" without ever reaching the writer
        // (emulator-caught, 2026-09-17: "Cannot access database on the main
        // thread"). The automatic triggers were never affected — they come
        // off `scope`, which is IO.
        return withContext(Dispatchers.IO) { writing.withLock {
            try {
                dumpNow(app, "manual", spaced = false, force = true)
                lastDumpLabel(app) ?: "nothing to write"
            } catch (e: Exception) {
                Log.w(TAG, "manual dump failed", e)
                EventLog.record("export", "photo table dump FAILED: ${e.message}")
                "failed: ${e.message ?: e::class.simpleName}"
            }
        } }
    }

    /** "1234 photos → Documents/Hillview2/photos.csv" — for the settings row. */
    fun lastDumpLabel(context: Context): String? {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val where = prefs.getString(PREF_WHERE, null) ?: return null
        val count = prefs.getInt(PREF_COUNT, 0)
        val shards = prefs.getInt(PREF_SHARDS, 1)
        val files = if (shards > 1) " (+${shards - 1} more file(s))" else ""
        val head = "$count photos → $where$files"
        // The app-private fallback is a path most people cannot reach and
        // that the system deletes with the app — the exact failure this
        // feature exists to prevent — so the row says what that means rather
        // than printing a directory and leaving the reader to notice.
        return if (prefs.getBoolean(PREF_DURABLE, false)) {
            head
        } else {
            "$head\n\u26a0\ufe0f app-private — this copy goes when the app does."
        }
    }

    /**
     * Where the CSV lands, preferred first.
     *
     * NOT beside the photos, which is the obvious answer and the wrong one:
     * DCIM accepts only images and video (MediaProvider enforces the type per
     * public directory), so a .csv there is refused. Documents/ takes any
     * type, survives uninstall, is reachable to a file manager, and is named
     * after the same folder as the photos so the pairing is visible.
     *
     * Both public routes can fail — no permission below API 29, a row owned
     * by something else, a provider that says no — so the last link is the
     * app-private directory. It dies with the app, which defeats the point,
     * but a dump that exists while the app does still beats none.
     */
    /**
     * Where a shard landed, and whether that place outlives the app.
     * [uri] is the media row to write to next time — see [PREF_URIS].
     */
    internal data class WriteResult(
        val where: String,
        val uri: String?,
        val durable: Boolean,
    )

    private fun writeCsvAtomic(
        app: Context,
        fileName: String,
        /**
         * Writes the shard INTO the stream it is handed, a row at a time. Not a String
         * and not a ByteArray: either one meant the whole shard in memory, which is the
         * OutOfMemoryError this replaced — and it may be called more than once, since
         * the MediaStore paths below try up to three ways to reach the row.
         */
        remembered: String?,
        write: (OutputStream) -> Unit,
    ): WriteResult {
        val folder = PhotoStorage.folderBase

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                return writeViaMediaStoreAtomic(app, folder, fileName, write, remembered)
            } catch (e: Exception) {
                Log.w(TAG, "MediaStore write failed, trying the file API", e)
            }
        }
        try {
            val dir = File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
                folder,
            )
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, fileName)
            writeAtomicFile(file, write)
            return WriteResult(file.absolutePath, uri = null, durable = true)
        } catch (e: Exception) {
            Log.w(TAG, "public file write failed, falling back to app-private", e)
        }
        val dir = File(app.getExternalFilesDir(null), "PhotoTableDumps")
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, fileName)
        writeAtomicFile(file, write)
        return WriteResult(file.absolutePath, uri = null, durable = false)
    }

    internal fun writeAtomicFile(file: File, write: (OutputStream) -> Unit) {
        val atomic = AtomicFile(file)
        val stream = atomic.startWrite()
        try {
            write(stream)
            stream.flush()
            atomic.finishWrite(stream)
        } catch (e: Throwable) {
            atomic.failWrite(stream)
            throw e
        }
    }

    internal fun writeViaMediaStoreAtomic(
        app: Context,
        folder: String,
        fileName: String,
        write: (OutputStream) -> Unit,
        remembered: String?,
    ): WriteResult {
        val resolver = app.contentResolver
        val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val relativePath = "${Environment.DIRECTORY_DOCUMENTS}/$folder/"
        val old = remembered?.let { Uri.parse(it) }
            ?: findInMediaStore(app, relativePath, fileName)
        val stageName = ".$fileName.${UUID.randomUUID()}.pending"
        val inserted = resolver.insert(
            collection,
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, stageName)
                put(MediaStore.MediaColumns.MIME_TYPE, "text/csv")
                put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            },
        ) ?: throw IOException("MediaStore insert returned null")
        var publishedComplete = false
        try {
            resolver.openOutputStream(inserted, "wt")?.use(write)
                ?: throw IOException("openOutputStream returned null for staged CSV")

            // Keep the previous complete file until staging has closed cleanly.
            // The pending row is invisible to other apps while it is written.
            val backupName = "$fileName.previous-${UUID.randomUUID()}"
            if (old != null) {
                val moved = resolver.update(
                    old,
                    ContentValues().apply { put(MediaStore.MediaColumns.DISPLAY_NAME, backupName) },
                    null,
                    null,
                )
                if (moved == 0) throw IOException("could not stage previous CSV for replacement")
            }
            try {
                val published = resolver.update(
                    inserted,
                    ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                        put(MediaStore.MediaColumns.IS_PENDING, 0)
                    },
                    null,
                    null,
                )
                if (published == 0) throw IOException("could not publish staged CSV")
                publishedComplete = true
            } catch (e: Exception) {
                if (old != null) {
                    resolver.update(
                        old,
                        ContentValues().apply { put(MediaStore.MediaColumns.DISPLAY_NAME, fileName) },
                        null,
                        null,
                    )
                }
                throw e
            }
            if (old != null) {
                try {
                    resolver.delete(old, null, null)
                } catch (e: Exception) {
                    Log.w(TAG, "could not remove the replaced CSV backup", e)
                }
            }
            return WriteResult(locator(app, inserted, relativePath, fileName), inserted.toString(), true)
        } catch (e: Exception) {
            // A process death can leave only an IS_PENDING row; the last
            // published CSV remains complete throughout the write.
            if (!publishedComplete) resolver.delete(inserted, null, null)
            throw e
        }
    }

    /** What to tell the user, using the name the file REALLY has. */
    private fun locator(app: Context, uri: Uri, relativePath: String, fallback: String): String {
        val name = try {
            app.contentResolver.query(
                uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null,
            )?.use { if (it.moveToFirst()) it.getString(0) else null }
        } catch (e: Exception) {
            null
        }
        return "$relativePath${name ?: fallback}"
    }

    private fun findInMediaStore(app: Context, relativePath: String, fileName: String): Uri? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return null
        val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        return app.contentResolver.query(
            collection,
            arrayOf(MediaStore.MediaColumns._ID),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?",
            arrayOf(relativePath, fileName),
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                ContentUris.withAppendedId(collection, cursor.getLong(0))
            } else {
                null
            }
        }
    }

    /**
     * Remove a shard file this app wrote and no longer fills.
     *
     * Only reached for an index the previous dump recorded writing, and only
     * for a name this file generates — the alternative is leaving a file
     * behind whose rows also appear in the file before it, which is worse
     * than a gap: a reader has no way to tell which copy is current.
     * Failures are shrugged off; a stale file is a nuisance, not a loss.
     */
    private fun deleteCsv(app: Context, fileName: String) {
        val folder = PhotoStorage.folderBase
        val relativePath = "${Environment.DIRECTORY_DOCUMENTS}/$folder/"
        try {
            findInMediaStore(app, relativePath, fileName)?.let {
                app.contentResolver.delete(it, null, null)
            }
            File(
                File(
                    Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
                    folder,
                ),
                fileName,
            ).delete()
            File(File(app.getExternalFilesDir(null), "PhotoTableDumps"), fileName).delete()
        } catch (e: Exception) {
            Log.w(TAG, "could not remove the now-unused $fileName", e)
        }
    }
}

/**
 * Maximum number of change records in one segment (user-raised: "switch to a
 * new file after 10k rows perhaps?").
 *
 * A full segment is sealed. Later edits, including edits to rows in sealed
 * segments, become newer records in the active segment. Readers apply files
 * in numeric order and keep the latest state for each photo ID.
 */
internal const val PHOTO_DUMP_SHARD_ROWS = 10_000

internal fun shardCount(total: Int): Int =
    if (total <= 0) 1 else (total + PHOTO_DUMP_SHARD_ROWS - 1) / PHOTO_DUMP_SHARD_ROWS

/**
 * `photos.csv`, then `photos-2.csv`, `photos-3.csv`.
 *
 * The first file keeps the plain name because for almost everyone it is the
 * only one, and a lone `photos-001.csv` invites the question of where the
 * rest went.
 */
internal fun photoDumpFileName(shard: Int): String =
    if (shard <= 0) "photos.csv" else "photos-${shard + 1}.csv"

/**
 * How long the capture pulse waits, by table size (user-raised: "space the
 * dumps more once it's in thousands of rows").
 *
 * Capture pulses are spaced more widely for a large archive. A dump reads
 * only pending photo IDs and their current rows; app start and background
 * events still drain the queue immediately.
 */
internal fun photoDumpIntervalMs(photoCount: Int): Long = when {
    photoCount < 1_000 -> 2 * 60_000L
    photoCount < 10_000 -> 10 * 60_000L
    photoCount < 50_000 -> 30 * 60_000L
    else -> 60 * 60_000L
}

/**
 * Every column of the photos table, in the entity's own order, with the
 * capture time repeated as readable UTC.
 *
 * The whole table, not a useful subset: this file is read when the app is
 * gone and cannot be asked what it meant, so leaving a column out is a
 * decision made on someone else's behalf about data they can no longer
 * recover. The JSON columns travel as quoted cells for the same reason.
 *
 * Header prefixed with `#`, as the geo dumps do — one CSV dialect in this
 * app, not two.
 */
/**
 * NOT FOR THE DUMP PATH — see [photoTableHeader] and [appendPhotoTableRow], which the
 * dump streams through instead.
 *
 * This materialises the whole thing, and at ten thousand rows that was an
 * OutOfMemoryError: the builder held ~19 MB of chars, `toString` copied it to another
 * 19 MB, and `toByteArray` made a third copy — about 48 MB of peak for one shard, on a
 * 268 MB heap (crash 2026-10-14, the second of exactly this shape after the IMU CSV's in
 * `64313ec6`). The capacity hint below was also four times short at the real ~970 chars
 * per row, so the builder reached its size by doubling, with a transient copy each time.
 *
 * Kept because small, bounded lists — tests, a handful of rows — are clearer written this
 * way, and because deleting it would hide what the streaming version is for.
 */
internal fun photoTableCsv(rows: List<PhotoEntity>): String {
    val out = StringBuilder(64 + rows.size * 1_000)
    out.append(photoTableHeader())
    for (row in rows) appendPhotoTableRow(out, row)
    return out.toString()
}

/** One row as text, for the hashing pass — a single row, never the shard. */
internal fun photoTableRowText(row: PhotoEntity): String =
    StringBuilder(1_200).also { appendPhotoTableRow(it, row) }.toString()

/** The `#`-prefixed header line, newline included. */
internal fun photoTableHeader(): String =
    "#" + PHOTO_DUMP_COLUMNS.joinToString(",") + "\n"

private fun photoTableDeltaHeader(): String =
    photoTableHeader().removeSuffix("\n") + ",changeId,changeAction\n"

private fun deltaFilePrefix(checkpoint: Long, rowCount: Int): String =
    "#hillview_photo_delta=1,checkpoint=$checkpoint,rows=$rowCount\n"

/**
 * ONE ROW, appended — the unit the dump streams.
 *
 * Appends rather than returning a String, so a caller can reuse one small builder across
 * ten thousand rows and never hold more than a row at a time. The obvious spelling — a
 * list of cells per row, joined — allocates thirty-odd strings and a list per photo,
 * which at ten thousand rows is the bulk of the work this does.
 */
internal fun appendPhotoTableRow(out: StringBuilder, row: PhotoEntity) {
    run {
        out.cell(row.id)
        out.cell(row.filename)
        out.cell(row.path)
        // Nullable, and empty means it: a photo with no position (v22) must
        // not read as Null Island, and an unknown altitude must not read as
        // sea level. `?.toString()` and not `.toString()`, which on a null
        // Double cheerfully writes the word "null".
        out.cell(row.latitude?.toString())
        out.cell(row.longitude?.toString())
        out.cell(row.altitude?.toString())
        out.cell(row.bearing.toString())
        out.cell(row.pitch?.toString())
        out.cell(row.capturedAt.toString())
        out.cell(isoUtc(row.capturedAt))
        // Empty where the row records no accuracy, like its nullable
        // neighbours above — and for the same reason. It used to write the
        // table's absent sentinel through verbatim, so a reader saw an
        // accuracy of 0.0 m, which reads as a perfect fix rather than as no
        // fix quality at all. `accuracyMOrNull` is the same absent test the
        // upload metadata uses, so the file and the wire agree.
        out.cell(row.accuracyMOrNull?.toString())
        out.cell(row.width.toString())
        out.cell(row.height.toString())
        out.cell(row.fileSize.toString())
        out.cell(row.createdAt.toString())
        out.cell(row.uploadStatus)
        out.cell(row.uploadedAt.toString())
        out.cell(row.retryCount.toString())
        out.cell(row.lastUploadAttempt.toString())
        out.cell(row.uploadError)
        out.cell(row.fileHash)
        out.cell(row.serverPhotoId)
        out.cell(if (row.deleted) "1" else "0")
        out.cell(row.version.toString())
        out.cell(row.anonymizationOverride)
        out.cell(row.bearingSource)
        out.cell(row.locationSource)
        out.cell(row.locationAgeMs?.toString())
        out.cell(row.exposureJson)
        out.cell(row.stampRefinedAt?.toString())
        out.cell(row.license)
        out.cell(row.altLocationJson)
        out.cell(row.attitudeJson)
        out.cell(row.fixJson)
        out.cell(row.lensJson)
        out.cell(row.inertialJson)
        out.cell(row.captureTimingJson, last = true)
    }
}

private fun appendPhotoTableDeltaRow(out: StringBuilder, row: PhotoEntity, changeId: Long) {
    appendPhotoTableRow(out, row)
    out.setLength(out.length - 1) // Replace the row's final newline with two cells.
    out.cell(changeId.toString())
    out.cell("upsert", last = true)
}

private fun appendPhotoTableTombstone(out: StringBuilder, photoId: String, changeId: Long) {
    val row = PhotoEntity(
        id = photoId,
        filename = "",
        path = "",
        latitude = null,
        longitude = null,
        capturedAt = 0L,
        accuracy = 0.0,
        width = 0,
        height = 0,
        fileSize = 0L,
        createdAt = 0L,
        deleted = true,
    )
    appendPhotoTableRow(out, row)
    out.setLength(out.length - 1)
    out.cell(changeId.toString())
    out.cell("delete", last = true)
}

/**
 * Legacy concatenation hash helper retained for its focused host tests. The
 * export now uses SQLite's coalesced change ledger and does not hash table rows.
 */
internal class ConcatHash {
    private var value = 0

    fun append(part: CharSequence): ConcatHash {
        var pow = 1
        repeat(part.length) { pow *= 31 }
        value = value * pow + part.toString().hashCode()
        return this
    }

    fun value(): Int = value
}

/** One cell and its separator; [last] ends the row instead. */
private fun StringBuilder.cell(value: String?, last: Boolean = false) {
    append(escapeCsvCell(value))
    append(if (last) '\n' else ',')
}

/**
 * The column names, in the order [photoTableCsv] writes them. New columns go
 * on the END: a reader keys on the header name, so an appended column never
 * shifts an existing one out from under it — the same rule the geo dumps
 * follow.
 */
internal val PHOTO_DUMP_COLUMNS = listOf(
    "id", "filename", "path",
    "latitude", "longitude", "altitude", "bearing", "pitch",
    "capturedAt", "capturedAtUtc", "accuracy",
    "width", "height", "fileSize", "createdAt",
    "uploadStatus", "uploadedAt", "retryCount", "lastUploadAttempt", "uploadError",
    "fileHash", "serverPhotoId", "deleted", "version", "anonymizationOverride",
    "bearingSource", "locationSource", "locationAgeMs", "exposureJson",
    "stampRefinedAt", "license", "altLocationJson", "attitudeJson",
    "fixJson", "lensJson", "inertialJson", "captureTimingJson",
)

private fun isoUtc(epochMs: Long): String {
    val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
    format.timeZone = TimeZone.getTimeZone("UTC")
    return format.format(Date(epochMs))
}

/** RFC 4180: quote when the cell could otherwise break the row. */
internal fun escapeCsvCell(value: String?): String {
    val str = value ?: ""
    val needsQuotes = str.any { it == ',' || it == '"' || it == '\n' || it == '\r' }
    return if (needsQuotes) "\"${str.replace("\"", "\"\"")}\"" else str
}
