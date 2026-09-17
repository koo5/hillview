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
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

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

    private const val TAG = "hv-PhotoTableDump"
    private const val PREFS = "hillview_photo_dump"
    private const val PREF_HASHES = "last_shard_hashes"
    private const val PREF_SHARDS = "last_shard_count"
    private const val PREF_FINGERPRINT = "last_table_fingerprint"
    private const val PREF_AT = "last_dump_at"
    private const val PREF_WHERE = "last_dump_where"
    private const val PREF_COUNT = "last_dump_count"

    /**
     * The media rows this app wrote, one per shard.
     *
     * Remembered by URI rather than looked up by name each time, because the
     * lookup can come back empty for a file that is plainly there: the media
     * database hides a non-media row from every app but its owner, and an
     * uninstall ORPHANS ownership. Asking by name then found nothing, so the
     * dump inserted — and MediaProvider, which never overwrites, handed back
     * "photos (1).csv". Then "(2)", and so on to "(31)", at which point it
     * gave up entirely ("Failed to build unique file") and the index fell
     * back to app-private storage, which is the one place it is useless.
     * Emulator-caught 2026-09-17, on a device carrying exactly that history.
     *
     * Keeping the URI turns MediaProvider's own de-duplication into a CLAIM:
     * whatever name it gives us the first time is the name we keep writing,
     * so there is one file per install and the previous install's index —
     * which describes photos that are still on the phone — is left alone
     * rather than overwritten by a fresh install's empty table.
     */
    private const val PREF_URIS = "last_shard_uris"

    /** Whether the last write landed somewhere that survives an uninstall. */
    private const val PREF_DURABLE = "last_dump_durable"

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val writing = Mutex()

    /**
     * Wire the triggers. Called once from the Application.
     *
     * Three of them, and the same reasoning as the geo dump's: leaving the
     * app is when the file most needs to be current; app start catches up
     * after a crash or a swipe-away that skipped that; and the capture pulse
     * bounds the loss inside a shoot that does neither.
     *
     * Only the capture pulse is SPACED. Leaving the app and starting it are
     * rare and important, and both are already gated by the table
     * fingerprint, so they cost a single aggregate query when nothing has
     * happened. Captures arrive by the thousand, so they are the trigger that
     * has to yield as the table grows.
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
            captureEvents.captured.collect { requestDump(app, "capture", spaced = true) }
        }
    }

    /**
     * Write the table out, unless nothing has changed since last time.
     *
     * Two gates, cheap one first. The FINGERPRINT is a single aggregate row
     * (SimplePhotoDao.getPhotoTableFingerprint) that answers "did anything
     * happen" without materializing a row — the difference between a
     * millisecond and a full table read every time the app is backgrounded.
     * The CONTENT HASH, per shard, then decides what is actually written; it
     * is on the bytes rather than on a dirty flag, so nothing has to remember
     * to announce itself.
     *
     * [spaced] adds the size-scaled interval on top (see
     * [photoDumpIntervalMs]) — the capture pulse's answer to a table with
     * tens of thousands of rows in it. [force] is the manual button, which
     * must write even when nothing changed, because the reason to press it is
     * usually that the file is not there.
     */
    fun requestDump(
        context: Context,
        reason: String,
        spaced: Boolean = false,
        force: Boolean = false,
    ) {
        val app = context.applicationContext
        scope.launch {
            writing.withLock {
                try {
                    dumpNow(app, reason, spaced, force)
                } catch (e: Exception) {
                    Log.w(TAG, "dump ($reason) failed", e)
                    EventLog.record("export", "photo table dump FAILED: ${e.message}")
                }
            }
        }
    }

    private fun dumpNow(app: Context, reason: String, spaced: Boolean, force: Boolean) {
        val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val dao = PhotoDatabase.getDatabase(app).photoDao()

        val fingerprint = dao.getPhotoTableFingerprint()
        if (!force && fingerprint == prefs.getString(PREF_FINGERPRINT, null)) return
        val total = dao.getTotalPhotoCount()
        if (!force && spaced && now - prefs.getLong(PREF_AT, 0L) < photoDumpIntervalMs(total)) return

        val previousHashes = prefs.getString(PREF_HASHES, "").orEmpty()
            .split(",").filter { it.isNotEmpty() }
        val previousUris = prefs.getString(PREF_URIS, "").orEmpty().split(",")
        val previousShards = prefs.getInt(PREF_SHARDS, 0)
        val shards = shardCount(total)
        val hashes = mutableListOf<String>()
        val uris = mutableListOf<String>()
        var written = 0
        var where: String? = prefs.getString(PREF_WHERE, null)
        var durable = prefs.getBoolean(PREF_DURABLE, false)

        for (shard in 0 until shards) {
            // One shard in memory at a time. The whole table would be the
            // same total work but a far worse peak, and the peak is what
            // shows up as a stutter on a phone with the camera running.
            val rows = dao.getPhotosOldestFirst(
                limit = PHOTO_DUMP_SHARD_ROWS,
                offset = shard * PHOTO_DUMP_SHARD_ROWS,
            )
            val csv = photoTableCsv(rows)
            val hash = csv.hashCode().toString()
            hashes += hash
            // A closed shard's bytes do not change when a photo is taken, so
            // the usual dump writes exactly one file however large the table
            // is. Deleting an OLD photo shifts everything after it, and those
            // shards get rewritten — correct, and rare.
            if (force || previousHashes.getOrNull(shard) != hash) {
                val result = writeCsv(
                    app,
                    photoDumpFileName(shard),
                    csv,
                    previousUris.getOrNull(shard)?.takeIf { it.isNotEmpty() },
                )
                where = result.where
                durable = result.durable
                uris += result.uri.orEmpty()
                written++
            } else {
                // Carry the claim forward: a shard we did not rewrite still
                // has the row we wrote it to, and forgetting it here would
                // make the next write to it start claiming all over again.
                uris += previousUris.getOrNull(shard).orEmpty()
            }
        }
        // The table shrank past a boundary: the tail files now hold rows that
        // are also in the files before them. Only ones this app recorded
        // writing are removed.
        for (shard in shards until previousShards) {
            deleteCsv(app, photoDumpFileName(shard))
        }

        val previousWhere = prefs.getString(PREF_WHERE, null)
        prefs.edit()
            .putString(PREF_FINGERPRINT, fingerprint)
            .putString(PREF_HASHES, hashes.joinToString(","))
            .putString(PREF_URIS, uris.joinToString(","))
            .putBoolean(PREF_DURABLE, durable)
            .putInt(PREF_SHARDS, shards)
            .putLong(PREF_AT, now)
            .putString(PREF_WHERE, where)
            .putInt(PREF_COUNT, total)
            .apply()
        Log.i(TAG, "dumped $total photos in $shards file(s), $written written ($reason) -> $where")
        // Only when the ANSWER changes. A routine dump every few minutes of a
        // shoot would bury the event log in lines that say the same thing; a
        // dump that suddenly lands somewhere else — the public folder
        // refused, so it went app-private — is exactly what the log is for.
        if (where != null && where != previousWhere) {
            // Landing app-private is not a detail: it is the one destination
            // that does NOT outlive the app, which is the whole reason this
            // file exists. Say so rather than reporting a path and letting
            // the reader work out what it means.
            EventLog.record(
                "export",
                if (durable) {
                    "photo index → $where"
                } else {
                    "photo index → $where — app-private, will NOT survive an uninstall"
                },
            )
        }
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
    private data class WriteResult(
        val where: String,
        val uri: String?,
        val durable: Boolean,
    )

    private fun writeCsv(
        app: Context,
        fileName: String,
        csv: String,
        remembered: String?,
    ): WriteResult {
        val bytes = csv.toByteArray(Charsets.UTF_8)
        val folder = PhotoStorage.folderBase

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                return writeViaMediaStore(app, folder, fileName, bytes, remembered)
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
            file.writeBytes(bytes)
            return WriteResult(file.absolutePath, uri = null, durable = true)
        } catch (e: Exception) {
            Log.w(TAG, "public file write failed, falling back to app-private", e)
        }
        val dir = File(app.getExternalFilesDir(null), "PhotoTableDumps")
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, fileName)
        file.writeBytes(bytes)
        return WriteResult(file.absolutePath, uri = null, durable = false)
    }

    private fun writeViaMediaStore(
        app: Context,
        folder: String,
        fileName: String,
        bytes: ByteArray,
        remembered: String?,
    ): WriteResult {
        val resolver = app.contentResolver
        val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val relativePath = "${Environment.DIRECTORY_DOCUMENTS}/$folder/"

        // Three ways to reach the row, in order of certainty. The remembered
        // URI is the only one that is reliable: a name lookup cannot see a
        // non-media row this app does not own, and an insert never overwrites.
        val claimed = remembered?.let { saved ->
            try {
                val uri = Uri.parse(saved)
                writeTo(resolver, uri, bytes)
                uri
            } catch (e: Exception) {
                Log.w(TAG, "the remembered index row is gone — claiming another", e)
                null
            }
        }
        if (claimed != null) {
            return WriteResult(locator(app, claimed, relativePath, fileName), claimed.toString(), true)
        }

        val found = findInMediaStore(app, relativePath, fileName)
        if (found != null) {
            writeTo(resolver, found, bytes)
            return WriteResult(locator(app, found, relativePath, fileName), found.toString(), true)
        }

        // Nothing of ours is there. Insert, and take whatever name comes
        // back: if the preferred one is occupied by a file this app can no
        // longer see (the previous install's index, which describes photos
        // that are still on the phone), MediaProvider hands over a numbered
        // sibling instead of clobbering it. That is the right outcome and
        // this remembers it, so the numbering happens ONCE.
        val inserted = resolver.insert(
            collection,
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, "text/csv")
                put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            },
        ) ?: throw IOException("MediaStore insert returned null")
        writeTo(resolver, inserted, bytes)
        return WriteResult(locator(app, inserted, relativePath, fileName), inserted.toString(), true)
    }

    /**
     * "wt" truncates: without it a shorter table would leave the tail of the
     * previous dump behind, and a CSV with a stale tail is worse than none.
     */
    private fun writeTo(resolver: android.content.ContentResolver, uri: Uri, bytes: ByteArray) {
        resolver.openOutputStream(uri, "wt")?.use { it.write(bytes) }
            ?: throw IOException("openOutputStream returned null")
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
 * How many rows go in one file, and therefore how much work the usual dump
 * does however big the table gets (user-raised: "switch to a new file after
 * 10k rows perhaps?").
 *
 * Sharding is what keeps the file count PROPORTIONAL — one more file per ten
 * thousand photos — rather than a per-day pile that grows forever whether or
 * not anything was shot. And because the rows are ordered oldest-first, a new
 * capture only ever touches the last shard, so the write stays the same size
 * at ten thousand photos as at a hundred thousand.
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
 * The dump costs a table read and a shard write, and both scale with the
 * table — so the frequency has to come down as the size goes up, or a long
 * shoot on a well-used phone spends its battery re-describing photos taken
 * years ago. What is traded away is how much of a shoot could be lost if the
 * phone dies mid-run without ever being backgrounded; at the sizes where the
 * interval grows, an hour of captures is a small fraction of what the file
 * already holds.
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
internal fun photoTableCsv(rows: List<PhotoEntity>): String {
    // Straight into one builder. The obvious spelling — a list of cells per
    // row, joined — allocates thirty-odd strings and a list for every photo,
    // which at ten thousand rows is the bulk of the work this does.
    val out = StringBuilder(64 + rows.size * 220)
    out.append('#')
    PHOTO_DUMP_COLUMNS.joinTo(out, ",")
    out.append('\n')
    for (row in rows) {
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
        out.cell(row.altLocationJson, last = true)
    }
    return out.toString()
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
    "stampRefinedAt", "license", "altLocationJson",
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
