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
    private const val TAG = "PhotoStorage"

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

    /** Preferred target first, then the rest — mirrors device_photos.rs. */
    fun chain(preferred: StorageMode): List<StorageMode> =
        listOf(preferred) + StorageMode.entries.filter { it != preferred }

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
            StorageMode.MediaStore -> {
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

    private fun fileOptions(dir: File, filename: String): Pair<ImageCapture.OutputFileOptions, File>? {
        if (!dir.exists() && !dir.mkdirs()) {
            Log.w(TAG, "cannot create ${dir.absolutePath}")
            return null
        }
        val file = File(dir, filename)
        return ImageCapture.OutputFileOptions.Builder(file).build() to file
    }
}
