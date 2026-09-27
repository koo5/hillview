package cz.hillview.capture

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import androidx.camera.core.ImageCapture
import cz.hillview.settings.StorageMode
import java.io.File
import cz.hillview.plugin.hvTag

/**
 * Where a capture landed. [locator] is what goes into the DB and upload path:
 * an absolute file path, or a content:// URI for MediaStore saves — the
 * shared-kt upload logic accepts both (PhotoUtils.pathExists/readBytesFromPath
 * branch on it).
 */
data class SavedPhoto(
    val locator: String,
    val uri: Uri?,
    val file: File?,
    val mode: StorageMode,
)

/**
 * The Tauri app's three storage options (device_photos.rs), same folder
 * names and same fallback behavior: try the preferred target, then the others
 * in order, so a blocked target degrades instead of losing the photo.
 *
 * DCIM/Hillview via the File API is subject to scoped storage — on API 29+ a
 * direct write there can fail (no requestLegacyExternalStorage here, same as
 * the Tauri app), which is exactly what the fallback chain is for. MediaStore
 * reaches the same DCIM/Hillview folder without any permission.
 */
object PhotoStorage {
    private val TAG = hvTag("PhotoStorage")

    /**
     * The folder's base name. "Hillview2" in both build types — this app
     * generation keeps its own folder, deliberately never mixing with the
     * Tauri app's DCIM/Hillview on the same device (the HILLVIEW_FOLDER
     * env var at build time overrides it). Set once at app start from
     * BuildConfig (HillviewApplication); this in-code default only serves
     * hosts without that wiring (tests, previews).
     */
    var folderBase: String = "Hillview"

    fun folderName(hideFromGallery: Boolean) =
        if (hideFromGallery) ".$folderBase" else folderBase

    /**
     * Preferred target first, then the rest — mirrors device_photos.rs.
     *
     * With hiding on, the MediaStore target is left out: the media database
     * cannot hold a hidden folder — MediaProvider rewrites ".Hillview2" to
     * "_.Hillview2" on the way in (AOSP FileUtils.sanitizeDisplayName;
     * seen on API 36) — so a hidden photo is always a direct file write.
     * Decided 2026-09-03: no point trying hidden files with the media API.
     */
    fun chain(preferred: StorageMode, hideFromGallery: Boolean = false): List<StorageMode> =
        (listOf(preferred) + StorageMode.entries.filter { it != preferred })
            .filter { !(hideFromGallery && it == StorageMode.MediaStore) }

    fun publicDir(hideFromGallery: Boolean): File =
        File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM),
            folderName(hideFromGallery),
        )

    fun privateDir(context: Context, hideFromGallery: Boolean): File =
        File(
            context.getExternalFilesDir(Environment.DIRECTORY_PICTURES),
            folderName(hideFromGallery),
        )

    /**
     * CameraX output options for [mode]. Returns null when the target can't
     * be prepared (e.g. the public dir can't be created) so the caller moves
     * on to the next link in the chain.
     */
    fun outputOptions(
        context: Context,
        mode: StorageMode,
        filename: String,
        hideFromGallery: Boolean,
    ): Pair<ImageCapture.OutputFileOptions, File?>? = try {
        when (mode) {
            StorageMode.PublicFolder -> fileOptions(publicDir(hideFromGallery), filename)
            StorageMode.PrivateFolder -> fileOptions(privateDir(context, hideFromGallery), filename)
            // chain() already leaves this target out when hiding; this is
            // the safety net for any other caller.
            StorageMode.MediaStore -> if (hideFromGallery) {
                Log.w(TAG, "MediaStore cannot hold a hidden folder — skipped")
                null
            } else {
                val values = ContentValues().apply {
                    put(MediaStore.Images.Media.DISPLAY_NAME, filename)
                    put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                    put(
                        MediaStore.Images.Media.RELATIVE_PATH,
                        "${Environment.DIRECTORY_DCIM}/${folderName(hideFromGallery)}",
                    )
                }
                ImageCapture.OutputFileOptions.Builder(
                    context.contentResolver,
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    values,
                ).build() to null
            }
        }
    } catch (e: Exception) {
        Log.w(TAG, "cannot prepare $mode: ${e.message}")
        null
    }

    /**
     * A File-API write into DCIM is NOT in the media database — verified on
     * API 36: files written that way stayed unindexed while MediaStore-written
     * siblings in the same folder showed up. Gallery apps read the database,
     * so without this the photo is invisible to them (the Tauri app has the
     * same gap). Skipped for ".Hillview", where hiding is the point.
     */
    fun indexInGallery(context: Context, file: File) {
        try {
            MediaScannerConnection.scanFile(
                context, arrayOf(file.absolutePath), arrayOf("image/jpeg"), null,
            )
        } catch (e: Exception) {
            Log.w(TAG, "media scan failed for ${file.absolutePath}: ${e.message}")
        }
    }

    /**
     * Walk the chain writing BYTES we already hold, for the in-memory capture path
     * (UploadSettings.exactCaptureTime). Returns the first target that accepted them.
     *
     * The fallback is stronger here than in the CameraX path, and that is the one real
     * bonus of owning the write: a target that refuses the bytes costs a retry into the
     * next folder, not a lost frame, because the frame is in hand rather than in the
     * camera's pipeline.
     *
     * DELIBERATELY FILE-ONLY for now. MediaStore needs an insert, an
     * `openOutputStream`, and IS_PENDING cleared on API 29+; the caller checks for a
     * file target before choosing this path at all, so a MediaStore preference keeps
     * the ordinary CameraX save. Hidden folders are unaffected — `chain()` already
     * leaves MediaStore out when hiding, which makes hidden captures the case this
     * path serves best.
     */
    fun writeBytesToChain(
        context: Context,
        chain: List<StorageMode>,
        filename: String,
        hideFromGallery: Boolean,
        bytes: ByteArray,
    ): SavedPhoto? {
        for (mode in chain) {
            val dir = when (mode) {
                StorageMode.PublicFolder -> publicDir(hideFromGallery)
                StorageMode.PrivateFolder -> privateDir(context, hideFromGallery)
                StorageMode.MediaStore -> continue
            }
            try {
                if (!dir.exists() && !dir.mkdirs()) {
                    Log.w(TAG, "cannot create ${dir.absolutePath}")
                    continue
                }
                val file = File(dir, filename)
                file.outputStream().use { it.write(bytes) }
                return SavedPhoto(file.absolutePath, null, file, mode)
            } catch (e: Exception) {
                Log.w(TAG, "cannot write $mode: ${e.message}")
            }
        }
        return null
    }

    /** Whether [writeBytesToChain] can serve this chain at all — a file target exists. */
    fun chainHasFileTarget(chain: List<StorageMode>): Boolean =
        chain.any { it != StorageMode.MediaStore }

    private fun fileOptions(dir: File, filename: String): Pair<ImageCapture.OutputFileOptions, File>? {
        if (!dir.exists() && !dir.mkdirs()) {
            Log.w(TAG, "cannot create ${dir.absolutePath}")
            return null
        }
        val file = File(dir, filename)
        return ImageCapture.OutputFileOptions.Builder(file).build() to file
    }
}
