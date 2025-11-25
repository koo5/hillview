package cz.hillview.plugin

import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import androidx.work.Data
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File
import java.io.IOException
import java.security.MessageDigest

class PhotoUploadWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "🢄PhotoUploadWorker"
        const val WORK_NAME = "photo_upload_work"
        const val KEY_AUTO_UPLOAD_ENABLED = "auto_upload_enabled"

        // Shared mutex to prevent multiple workers from running simultaneously
        private val workerMutex = Mutex()
    }

    private val database = PhotoDatabase.getDatabase(applicationContext)
    private val photoDao = database.photoDao()
    private val authManager = AuthenticationManager(applicationContext)

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        workerMutex.withLock {
            val triggerSource = inputData.getString("trigger_source") ?: "unknown"

            // Start foreground service for persistent upload notifications
            try {
                val intent = Intent(applicationContext, SecureUploadService::class.java).apply {
                    action = SecureUploadService.ACTION_START_UPLOAD
                    putExtra("trigger_source", triggerSource)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    applicationContext.startForegroundService(intent)
                } else {
                    applicationContext.startService(intent)
                }
                Log.d(TAG, "Started foreground upload service with trigger: $triggerSource")
            } catch (e: Exception) {
                Log.w(TAG, "Failed to start foreground service: ${e.message}")
            }
		}
    }

}
