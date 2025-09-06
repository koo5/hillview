package cz.hillview.plugin

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit
import app.tauri.plugin.Invoke
import app.tauri.annotation.Command
import app.tauri.annotation.ActivityCallback
import app.tauri.annotation.InvokeArg

class ExamplePlugin(private val activity: Activity): Plugin(activity) {
    companion object {
        private const val TAG = "ExamplePlugin"
        private const val CAMERA_PERMISSION_REQUEST_CODE = 1001
    }

    // Manager instances
    private lateinit var permissionManager: PermissionManager
    private lateinit var photoImportManager: PhotoImportManager
    private lateinit var photoScanManager: PhotoScanManager
    private lateinit var sensorManager: SensorManager
    private lateinit var database: PhotoDatabase
    private lateinit var authManager: AuthenticationManager
    private lateinit var secureUploadManager: SecureUploadManager

    // State variables
    private var pendingWebViewPermissionRequest: PermissionRequest? = null
    private var pendingNativePermissionInvoke: Invoke? = null

    init {
        initializeManagers()
    }

    private fun initializeManagers() {
        Log.d(TAG, "🔧 Initializing managers...")
        
        database = PhotoDatabase.getDatabase(activity)
        permissionManager = PermissionManager(activity)
        authManager = AuthenticationManager(activity)
        secureUploadManager = SecureUploadManager(activity)
        sensorManager = SensorManager(activity, permissionManager)
        photoScanManager = PhotoScanManager(activity, database)
        photoImportManager = PhotoImportManager(activity, photoScanManager)
        
        Log.d(TAG, "✅ All managers initialized")
    }

    override fun load(webView: android.webkit.WebView) {
        Log.i(TAG, "🢄🎥 Plugin load() called with WebView: $webView")
        super.load(webView)
        permissionManager.setupWebViewCameraPermissions(webView) { request ->
            handleWebViewPermissionRequest(request)
        }
    }

    // WebView Permission Handling
    fun handleWebViewPermissionRequest(request: PermissionRequest) {
        Log.i(TAG, "🢄🎥 WebView permission request: ${request.resources.joinToString(", ")}")
        
        val requestedResources = request.resources
        val needsCamera = requestedResources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE)
        val needsMicrophone = requestedResources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)

        if (needsCamera || needsMicrophone) {
            handleCameraPermissionRequest(request, needsCamera, needsMicrophone)
        } else {
            Log.i(TAG, "🢄🎥 Non-camera permission request, granting automatically")
            activity.runOnUiThread { request.grant(request.resources) }
        }
    }

    private fun handleCameraPermissionRequest(request: PermissionRequest, needsCamera: Boolean, needsMicrophone: Boolean) {
        Log.i(TAG, "🢄🎥 Handling camera permission request (camera: $needsCamera, microphone: $needsMicrophone)")

        val lockAcquired = permissionManager.acquirePermissionLock("camera")
        if (!lockAcquired) {
            Log.w(TAG, "🢄🎥 Permission system busy, denying WebView camera permission")
            activity.runOnUiThread { request.deny() }
            return
        }

        val requiredPermissions = mutableListOf<String>()
        if (needsCamera) requiredPermissions.add(android.Manifest.permission.CAMERA)
        if (needsMicrophone) requiredPermissions.add(android.Manifest.permission.RECORD_AUDIO)

        val hasAllPermissions = requiredPermissions.all { permission ->
            ContextCompat.checkSelfPermission(activity, permission) == PackageManager.PERMISSION_GRANTED
        }

        if (hasAllPermissions) {
            Log.i(TAG, "🢄🎥 Android permissions already granted, granting WebView permission")
            permissionManager.releasePermissionLock("camera")
            activity.runOnUiThread { request.grant(request.resources) }
        } else {
            Log.i(TAG, "🢄🎥 Android permissions needed, requesting from user")
            pendingWebViewPermissionRequest = request

            ActivityCompat.requestPermissions(
                activity,
                requiredPermissions.toTypedArray(),
                CAMERA_PERMISSION_REQUEST_CODE
            )
        }
    }

    // Handle permission results
    fun handlePermissionResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        if (requestCode == CAMERA_PERMISSION_REQUEST_CODE) {
            Log.i(TAG, "🢄🎥 Camera permission result received")
            
            val allGranted = grantResults.all { it == PackageManager.PERMISSION_GRANTED }

            // Handle WebView permission request if present
            pendingWebViewPermissionRequest?.let { request ->
                Log.i(TAG, "🢄🎥 Handling WebView permission result")
                
                if (allGranted) {
                    Log.i(TAG, "🢄🎥 Camera permissions granted by user, granting WebView permission")
                    activity.runOnUiThread { request.grant(request.resources) }
                } else {
                    Log.i(TAG, "🢄🎥 Camera permissions denied by user, denying WebView permission")
                    activity.runOnUiThread { request.deny() }
                }
                
                pendingWebViewPermissionRequest = null
                permissionManager.releasePermissionLock("camera")
            }

            // Handle native permission request if present
            pendingNativePermissionInvoke?.let { invoke ->
                Log.i(TAG, "🢄🎥 Handling native permission result")
                
                val result = JSObject()
                result.put("granted", allGranted)
                
                if (allGranted) {
                    Log.i(TAG, "🢄🎥 Native camera permission granted")
                } else {
                    Log.w(TAG, "🢄🎥 Native camera permission denied")
                }
                
                invoke.resolve(result)
                pendingNativePermissionInvoke = null
                permissionManager.releasePermissionLock("camera-native")
            }
        }
    }

    // Tauri Commands
    @Command
    fun startSensor(invoke: Invoke) {
        val mode = try {
            val args = invoke.parseArgs(SensorModeArgs::class.java)
            args.mode ?: EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
        } catch (e: Exception) {
            Log.d(TAG, "🔄 Args parsed as null, using default mode")
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
        }

        sensorManager.startSensor(mode)
        invoke.resolve()
    }

    @Command
    fun stopSensor(invoke: Invoke) {
        sensorManager.stopSensor()
        invoke.resolve()
    }

    @Command
    fun startPreciseLocationListener(invoke: Invoke) {
        sensorManager.startPreciseLocationListener()
        invoke.resolve()
    }

    @Command
    fun stopPreciseLocationListener(invoke: Invoke) {
        sensorManager.stopPreciseLocationListener()
        invoke.resolve()
    }

    @Command
    fun getDevicePhotos(invoke: Invoke) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoDao = database.photoDao()
                val photos = photoDao.getAllPhotos()
                
                val response = JSObject()
                response.put("photos", photos.map { it.toJson() })
                response.put("lastUpdated", System.currentTimeMillis() / 1000)
                
                CoroutineScope(Dispatchers.Main).launch {
                    invoke.resolve(response)
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Failed to get device photos", e)
                CoroutineScope(Dispatchers.Main).launch {
                    val error = JSObject()
                    error.put("photos", emptyArray<String>())
                    error.put("lastUpdated", 0)
                    invoke.resolve(error)
                }
            }
        }
    }

    @Command
    fun refreshPhotoScan(invoke: Invoke) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val scanResult = photoScanManager.refreshPhotoScan()
                CoroutineScope(Dispatchers.Main).launch {
                    invoke.resolve(scanResult)
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Photo scan failed", e)
                CoroutineScope(Dispatchers.Main).launch {
                    val error = JSObject()
                    error.put("photosAdded", 0)
                    error.put("scanErrors", 1)
                    error.put("success", false)
                    error.put("error", e.message)
                    invoke.resolve(error)
                }
            }
        }
    }

    @Command
    fun importPhotos(invoke: Invoke) {
        try {
            Log.d(TAG, "📂 Starting photo import via file picker")
            
            val chooserIntent = photoImportManager.createFilePickerIntent()
            startActivityForResult(invoke, chooserIntent, "handleFileImportResult")
            
            Log.d(TAG, "📂 File picker launched using Tauri plugin system")
            
        } catch (e: Exception) {
            Log.e(TAG, "📂 Error launching file picker", e)
            val error = JSObject().apply {
                put("success", false)
                put("selected_files", emptyArray<String>())
                put("imported_count", 0)
                put("error", e.message)
            }
            invoke.resolve(error)
        }
    }
    
    @ActivityCallback
    fun handleFileImportResult(invoke: Invoke, result: ActivityResult) {
        Log.d(TAG, "📂 File import activity result received: ${result.resultCode}")
        
        if (result.resultCode != Activity.RESULT_OK || result.data == null) {
            Log.i(TAG, "📂 File import cancelled by user or no data")
            val response = JSObject().apply {
                put("success", false)
                put("selected_files", emptyArray<String>())
                put("imported_count", 0)
                put("error", "User cancelled or no files selected")
            }
            invoke.resolve(response)
            return
        }
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val data = result.data!!
                val selectedUris = mutableListOf<Uri>()
                
                // Handle multiple selection
                data.clipData?.let { clipData ->
                    for (i in 0 until clipData.itemCount) {
                        selectedUris.add(clipData.getItemAt(i).uri)
                    }
                } ?: data.data?.let { uri ->
                    selectedUris.add(uri)
                }
                
                if (selectedUris.isEmpty()) {
                    Log.w(TAG, "📂 No valid URIs found in selection")
                    val response = JSObject().apply {
                        put("success", false)
                        put("selected_files", emptyArray<String>())
                        put("imported_count", 0)
                        put("error", "No valid files selected")
                    }
                    CoroutineScope(Dispatchers.Main).launch {
                        invoke.resolve(response)
                    }
                    return@launch
                }
                
                Log.d(TAG, "📂 Processing ${selectedUris.size} selected files")
                
                // Process the selected files with detailed error tracking
                val importResult = photoImportManager.importSelectedFiles(selectedUris)
                
                // Trigger a photo scan to update the database
                val scanResult = photoScanManager.refreshPhotoScan()
                
                val overallSuccess = importResult.successCount > 0 || importResult.failedCount == 0
                
                val response = JSObject().apply {
                    put("success", overallSuccess)
                    put("selected_files", importResult.successfulFiles.toTypedArray())
                    put("imported_count", importResult.successCount)
                    put("failed_count", importResult.failedCount)
                    put("failed_files", importResult.failedFiles.toTypedArray())
                    if (importResult.errors.isNotEmpty()) {
                        put("import_errors", importResult.errors.toTypedArray())
                    }
                    put("scan_result", scanResult)
                }
                
                CoroutineScope(Dispatchers.Main).launch {
                    if (overallSuccess) {
                        Log.i(TAG, "✅ Import completed: ${importResult.successCount} successful, ${importResult.failedCount} failed")
                    } else {
                        Log.w(TAG, "⚠️ Import had issues: ${importResult.successCount} successful, ${importResult.failedCount} failed")
                    }
                    invoke.resolve(response)
                }
                
            } catch (e: Exception) {
                Log.e(TAG, "❌ Error processing file import", e)
                CoroutineScope(Dispatchers.Main).launch {
                    val response = JSObject().apply {
                        put("success", false)
                        put("selected_files", emptyArray<String>())
                        put("imported_count", 0)
                        put("failed_count", 0)
                        put("error", "Import process failed: ${e.message}")
                    }
                    invoke.resolve(response)
                }
            }
        }
    }

    @Command
    fun checkCameraPermission(invoke: Invoke) {
        Log.i(TAG, "🎥 Camera permission check from frontend")
        
        val hasPermission = permissionManager.hasCameraPermission()
        val result = JSObject().apply {
            put("granted", hasPermission)
        }
        
        invoke.resolve(result)
    }

    @Command
    fun requestCameraPermission(invoke: Invoke) {
        Log.i(TAG, "🎥 Camera permission request from frontend")

        val result = permissionManager.requestCameraPermission()
        
        if (result.optBoolean("pending", false)) {
            pendingNativePermissionInvoke = invoke
        } else {
            invoke.resolve(result)
        }
    }

    // Cleanup
    fun onDestroy() {
        Log.d(TAG, "🧹 Plugin cleanup")
        sensorManager.cleanup()
        permissionManager.releasePermissionLock("camera")
        permissionManager.releasePermissionLock("camera-native")
    }

    // Authentication Commands
    @Command
    fun getAuthToken(invoke: Invoke) {
        // Use coroutine for async operation
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val token = authManager.getValidToken()
                val (_, expiresAt) = authManager.getTokenInfo()
                val success = token != null
                
                val response = JSObject().apply {
                    put("success", success)
                    put("token", token)
                    put("expires_at", expiresAt)
                }
                
                Log.d(TAG, "🔐 getAuthToken: success=$success, has_token=${token != null}")
                invoke.resolve(response)
            } catch (e: Exception) {
                Log.e(TAG, "🔐 getAuthToken error: ${e.message}", e)
                val response = JSObject().apply {
                    put("success", false)
                    put("error", e.message ?: "Unknown error")
                }
                invoke.resolve(response)
            }
        }
    }

    @Command
    fun storeAuthToken(invoke: Invoke) {
        val args = invoke.parseArgs(StoreAuthTokenArgs::class.java)
        
        // Use coroutine for async operation
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val success = authManager.storeAuthToken(
                    args.token,
                    args.expiresAt,
                    args.refreshToken
                )
                
                val response = JSObject().apply {
                    put("success", success)
                }
                
                Log.d(TAG, "🔐 storeAuthToken: success=$success")
                invoke.resolve(response)
            } catch (e: Exception) {
                Log.e(TAG, "🔐 storeAuthToken error: ${e.message}", e)
                val response = JSObject().apply {
                    put("success", false)
                    put("error", e.message ?: "Unknown error")
                }
                invoke.resolve(response)
            }
        }
    }

    @Command
    fun clearAuthToken(invoke: Invoke) {
        try {
            val success = authManager.clearAuthToken()
            
            val response = JSObject().apply {
                put("success", success)
            }
            
            Log.d(TAG, "🔐 clearAuthToken: success=$success")
            invoke.resolve(response)
        } catch (e: Exception) {
            Log.e(TAG, "🔐 clearAuthToken error: ${e.message}", e)
            val response = JSObject().apply {
                put("success", false)
                put("error", e.message ?: "Unknown error")
            }
            invoke.resolve(response)
        }
    }

    @Command 
    fun refreshAuthToken(invoke: Invoke) {
        // Use coroutine for async operation
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val success = authManager.refreshTokenIfNeeded()
                
                val response = JSObject().apply {
                    put("success", success)
                }
                
                Log.d(TAG, "🔐 refreshAuthToken: success=$success")
                invoke.resolve(response)
            } catch (e: Exception) {
                Log.e(TAG, "🔐 refreshAuthToken error: ${e.message}", e)
                val response = JSObject().apply {
                    put("success", false)
                    put("error", e.message ?: "Unknown error")
                }
                invoke.resolve(response)
            }
        }
    }

    @Command
    fun isTokenExpired(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(IsTokenExpiredArgs::class.java)
            val bufferMinutes = args.bufferMinutes ?: 2
            
            val expired = authManager.isTokenExpired(bufferMinutes)
            
            val response = JSObject().apply {
                put("expired", expired)
            }
            
            Log.d(TAG, "🔐 isTokenExpired: expired=$expired (buffer: $bufferMinutes min)")
            invoke.resolve(response)
        } catch (e: Exception) {
            Log.e(TAG, "🔐 isTokenExpired error: ${e.message}", e)
            val response = JSObject().apply {
                put("expired", true) // Default to expired on error
                put("error", e.message ?: "Unknown error")
            }
            invoke.resolve(response)
        }
    }

    @Command
    fun setUploadConfig(invoke: Invoke) {
        val args = invoke.parseArgs(UploadConfigArgs::class.java)
        
        args.serverUrl?.let { secureUploadManager.setServerUrl(it) }
        Log.d(TAG, "📤 Upload config updated")
        
        val result = JSObject().apply {
            put("success", true)
        }
        invoke.resolve(result)
    }
}

// Helper classes for data transfer
data class ActivityResult(
    val resultCode: Int,
    val data: Intent?
)

data class SensorModeArgs(
    val mode: Int?
)

@InvokeArg
class StoreAuthTokenArgs {
    lateinit var token: String
    lateinit var expiresAt: String
    var refreshToken: String? = null
}

@InvokeArg
class IsTokenExpiredArgs {
    var bufferMinutes: Int? = null
}

@InvokeArg
class UploadConfigArgs {
    var serverUrl: String? = null
}

// Extension function for PhotoEntity
private fun PhotoEntity.toJson(): Map<String, Any?> {
    return mapOf(
        "id" to id,
        "filename" to filename,
        "path" to path,
        "latitude" to latitude,
        "longitude" to longitude,
        "altitude" to altitude,
        "bearing" to bearing,
        "timestamp" to timestamp,
        "accuracy" to accuracy,
        "fileHash" to fileHash,
        "fileSize" to fileSize,
        "uploadStatus" to uploadStatus,
        "createdAt" to createdAt
    )
}