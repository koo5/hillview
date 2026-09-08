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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
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
    private const val PREF_HASH = "last_content_hash"
    private const val PREF_AT = "last_dump_at"
    private const val PREF_WHERE = "last_dump_where"
    private const val PREF_COUNT = "last_dump_count"

    /** Stable name, rewritten in place: one file to find, not a pile. */
    const val FILE_NAME = "photos.csv"

    /**
     * The pulse during a long shoot. An interval run in a pocket never
     * backgrounds the app, so the capture trigger is the only one that fires
     * for hours — often enough to bound the loss, rare enough that a run at
     * 0.2 s does not rewrite the file every shot.
     */
    private const val CAPTURE_MIN_INTERVAL_MS = 5 * 60 * 1000L

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val writing = Mutex()

    /**
     * Wire the triggers. Called once from the Application.
     *
     * Three of them, and the same reasoning as the geo dump's: leaving the
     * app is when the file most needs to be current; app start catches up
     * after a crash or a swipe-away that skipped that; and the capture pulse
     * bounds the loss inside a shoot that does neither.
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
            captureEvents.captured.collect {
                requestDump(app, "capture", minIntervalMs = CAPTURE_MIN_INTERVAL_MS)
            }
        }
    }

    /**
     * Write the table out, unless nothing has changed since last time.
     *
     * The skip is on the CONTENT, not on a dirty flag: every mutation of the
     * table — a capture, a deletion, an upload landing a server id — changes
     * the bytes, and nothing has to remember to say so. [force] is the manual
     * button, which must write even when the content is identical, because
     * the reason to press it is usually that the file is not there.
     */
    fun requestDump(
        context: Context,
        reason: String,
        minIntervalMs: Long = 0L,
        force: Boolean = false,
    ) {
        val app = context.applicationContext
        scope.launch {
            writing.withLock {
                try {
                    dumpNow(app, reason, minIntervalMs, force)
                } catch (e: Exception) {
                    Log.w(TAG, "dump ($reason) failed", e)
                    EventLog.record("export", "photo table dump FAILED: ${e.message}")
                }
            }
        }
    }

    private fun dumpNow(app: Context, reason: String, minIntervalMs: Long, force: Boolean) {
        val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (!force && minIntervalMs > 0 && now - prefs.getLong(PREF_AT, 0L) < minIntervalMs) return

        val rows = PhotoDatabase.getDatabase(app).photoDao().getAllPhotos()
        val csv = photoTableCsv(rows)
        val hash = csv.hashCode().toString()
        if (!force && hash == prefs.getString(PREF_HASH, null)) return

        val previousWhere = prefs.getString(PREF_WHERE, null)
        val where = writeCsv(app, csv)
        prefs.edit()
            .putString(PREF_HASH, hash)
            .putLong(PREF_AT, now)
            .putString(PREF_WHERE, where)
            .putInt(PREF_COUNT, rows.size)
            .apply()
        Log.i(TAG, "dumped ${rows.size} photos ($reason) -> $where")
        // Only when the ANSWER changes. A routine dump every five minutes of
        // a shoot would bury the event log in lines that say the same thing;
        // a dump that suddenly lands somewhere else — the public folder
        // refused, so it went app-private — is exactly what the log is for.
        if (where != previousWhere) {
            EventLog.record("export", "photo index → $where")
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
        return writing.withLock {
            try {
                dumpNow(app, "manual", minIntervalMs = 0L, force = true)
                lastDumpLabel(app) ?: "nothing to write"
            } catch (e: Exception) {
                Log.w(TAG, "manual dump failed", e)
                EventLog.record("export", "photo table dump FAILED: ${e.message}")
                "failed: ${e.message ?: e::class.simpleName}"
            }
        }
    }

    /** "1234 photos → Documents/Hillview2/photos.csv" — for the settings row. */
    fun lastDumpLabel(context: Context): String? {
        val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val where = prefs.getString(PREF_WHERE, null) ?: return null
        return "${prefs.getInt(PREF_COUNT, 0)} photos → $where"
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
    private fun writeCsv(app: Context, csv: String): String {
        val bytes = csv.toByteArray(Charsets.UTF_8)
        val folder = PhotoStorage.folderBase

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                return writeViaMediaStore(app, folder, bytes)
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
            val file = File(dir, FILE_NAME)
            file.writeBytes(bytes)
            return file.absolutePath
        } catch (e: Exception) {
            Log.w(TAG, "public file write failed, falling back to app-private", e)
        }
        val dir = File(app.getExternalFilesDir(null), "PhotoTableDumps")
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, FILE_NAME)
        file.writeBytes(bytes)
        return file.absolutePath
    }

    private fun writeViaMediaStore(app: Context, folder: String, bytes: ByteArray): String {
        val resolver = app.contentResolver
        val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val relativePath = "${Environment.DIRECTORY_DOCUMENTS}/$folder/"
        // Find the row we wrote last time rather than inserting again — a
        // second insert of the same name yields "photos (1).csv", and the
        // point of a stable name is that there is one file to find.
        val existing = resolver.query(
            collection,
            arrayOf(MediaStore.MediaColumns._ID),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=? AND ${MediaStore.MediaColumns.DISPLAY_NAME}=?",
            arrayOf(relativePath, FILE_NAME),
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) ContentUris.withAppendedId(collection, cursor.getLong(0)) else null
        }
        val uri: Uri = existing ?: resolver.insert(
            collection,
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, FILE_NAME)
                put(MediaStore.MediaColumns.MIME_TYPE, "text/csv")
                put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath)
            },
        ) ?: throw IOException("MediaStore insert returned null")
        // "wt" truncates: without it a shorter table would leave the tail of
        // the previous dump behind, and a CSV with a stale tail is worse than
        // no CSV at all.
        resolver.openOutputStream(uri, "wt")?.use { it.write(bytes) }
            ?: throw IOException("openOutputStream returned null")
        return "$relativePath$FILE_NAME"
    }
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
    val header = "#" + PHOTO_DUMP_COLUMNS.joinToString(",") + "\n"
    return header + rows.joinToString("") { row ->
        listOf(
            row.id,
            row.filename,
            row.path,
            row.latitude.toString(),
            row.longitude.toString(),
            row.altitude.toString(),
            row.bearing.toString(),
            row.pitch?.toString(),
            row.capturedAt.toString(),
            isoUtc(row.capturedAt),
            row.accuracy.toString(),
            row.width.toString(),
            row.height.toString(),
            row.fileSize.toString(),
            row.createdAt.toString(),
            row.uploadStatus,
            row.uploadedAt.toString(),
            row.retryCount.toString(),
            row.lastUploadAttempt.toString(),
            row.uploadError,
            row.fileHash,
            row.serverPhotoId,
            if (row.deleted) "1" else "0",
            row.version.toString(),
            row.anonymizationOverride,
            row.bearingSource,
            row.locationSource,
            row.locationAgeMs?.toString(),
            row.exposureJson,
            row.stampRefinedAt?.toString(),
            row.license,
            row.altLocationJson,
        ).joinToString(",") { escapeCsvCell(it) } + "\n"
    }
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
