package cz.hillview.plugin

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Log
import app.tauri.plugin.JSObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

class PhotoImportManager(
    private val activity: Activity,
    private val photoScanManager: PhotoScanManager
) {
    companion object {
        private const val TAG = "PhotoImportManager"
    }

    data class ImportResult(
        val successfulFiles: List<String>,
        val failedFiles: List<String>,
        val errors: List<String>,
        val successCount: Int,
        val failedCount: Int
    )

    suspend fun importSelectedFiles(selectedUris: List<Uri>): ImportResult {
        val successfulFiles = mutableListOf<String>()
        val failedFiles = mutableListOf<String>()
        val errors = mutableListOf<String>()
        val hillviewDir = File("/storage/emulated/0/Pictures/Hillview")
        
        // Create timestamped import directory
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val importDir = File(hillviewDir, "Import$timestamp")
        
        // Ensure the import directory exists
        if (!importDir.mkdirs() && !importDir.exists()) {
            val errorMsg = "Failed to create import directory: ${importDir.path}"
            Log.e(TAG, "❌ $errorMsg")
            errors.add(errorMsg)
            throw Exception("Unable to create import directory")
        }
        
        Log.i(TAG, "📁 Created import directory: ${importDir.path}")
        
        for (uri in selectedUris) {
            val originalName = getFileNameFromUri(uri) ?: "imported_${System.currentTimeMillis()}.jpg"
            
            try {
                // Validate that this is actually an image file
                if (!isImageFile(originalName)) {
                    val errorMsg = "Skipped non-image file: $originalName"
                    Log.w(TAG, "⚠️ $errorMsg")
                    failedFiles.add(originalName)
                    errors.add(errorMsg)
                    continue
                }
                
                val targetFile = File(importDir, originalName)
                
                // Handle duplicate filenames by adding counter
                var finalFile = targetFile
                var counter = 1
                while (finalFile.exists()) {
                    val nameWithoutExt = originalName.substringBeforeLast('.', originalName)
                    val extension = originalName.substringAfterLast('.', "")
                    val newName = if (extension.isNotEmpty()) {
                        "${nameWithoutExt}_${counter}.${extension}"
                    } else {
                        "${nameWithoutExt}_${counter}"
                    }
                    finalFile = File(importDir, newName)
                    counter++
                }
                
                // Validate file size before copying
                val fileSize = try {
                    activity.contentResolver.openAssetFileDescriptor(uri, "r")?.use { 
                        it.length 
                    } ?: 0L
                } catch (e: Exception) {
                    0L
                }
                
                if (fileSize > 100 * 1024 * 1024) { // 100MB limit
                    val errorMsg = "File too large (${fileSize / (1024*1024)}MB): $originalName"
                    Log.w(TAG, "⚠️ $errorMsg")
                    failedFiles.add(originalName)
                    errors.add(errorMsg)
                    continue
                }
                
                // Copy the file to import directory
                var copySuccessful = false
                activity.contentResolver.openInputStream(uri)?.use { inputStream ->
                    finalFile.outputStream().use { outputStream ->
                        val bytesWritten = inputStream.copyTo(outputStream)
                        copySuccessful = bytesWritten > 0
                    }
                }
                
                if (!copySuccessful) {
                    val errorMsg = "Failed to copy file data: $originalName"
                    Log.e(TAG, "❌ $errorMsg")
                    failedFiles.add(originalName)
                    errors.add(errorMsg)
                    // Clean up partial file
                    if (finalFile.exists()) {
                        finalFile.delete()
                    }
                    continue
                }
                
                // Verify the copied file exists and has content
                if (!finalFile.exists() || finalFile.length() == 0L) {
                    val errorMsg = "Copied file is empty or missing: $originalName"
                    Log.e(TAG, "❌ $errorMsg")
                    failedFiles.add(originalName)
                    errors.add(errorMsg)
                    // Clean up empty file
                    if (finalFile.exists()) {
                        finalFile.delete()
                    }
                    continue
                }
                
                Log.i(TAG, "📄 Successfully imported: ${finalFile.name} (${finalFile.length()} bytes)")
                successfulFiles.add(finalFile.absolutePath)
                
            } catch (e: Exception) {
                val errorMsg = "Failed to import '$originalName': ${e.message}"
                Log.e(TAG, "❌ $errorMsg", e)
                failedFiles.add(originalName)
                errors.add(errorMsg)
            }
        }
        
        val result = ImportResult(
            successfulFiles = successfulFiles,
            failedFiles = failedFiles,
            errors = errors,
            successCount = successfulFiles.size,
            failedCount = failedFiles.size
        )
        
        Log.i(TAG, "📊 Import complete: ${result.successCount} successful, ${result.failedCount} failed")
        if (result.errors.isNotEmpty()) {
            Log.w(TAG, "📋 Import errors: ${result.errors.joinToString("; ")}")
        }
        
        return result
    }

    private fun isImageFile(filename: String): Boolean {
        val imageExtensions = setOf("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "heif")
        val extension = filename.substringAfterLast('.', "").lowercase()
        return extension in imageExtensions
    }
    
    private fun getFileNameFromUri(uri: Uri): String? {
        return try {
            activity.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (nameIndex >= 0) cursor.getString(nameIndex) else null
                } else null
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to get filename from URI: $uri", e)
            null
        }
    }

    fun createFilePickerIntent(): Intent {
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            addCategory(Intent.CATEGORY_OPENABLE)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        
        return Intent.createChooser(intent, "Select Photos to Import")
    }
}