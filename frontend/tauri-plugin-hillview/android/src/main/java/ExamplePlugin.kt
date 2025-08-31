package io.github.koo5.hillview.plugin

import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import app.tauri.plugin.Invoke
import java.util.concurrent.TimeUnit

@InvokeArg
class PingArgs {
  var value: String? = null
}

@InvokeArg
class LocationUpdateArgs {
  var latitude: Double = 0.0
  var longitude: Double = 0.0
}

@InvokeArg
class SensorModeArgs {
  var mode: Int? = null
}

@InvokeArg
class AutoUploadArgs {
  var enabled: Boolean = false
}

@InvokeArg
class UploadConfigArgs {
  var serverUrl: String? = null
  // authToken removed - now managed by AuthenticationManager
}

@InvokeArg
class PhotoUploadArgs {
  var photoId: String? = null
}

@InvokeArg
class StoreAuthTokenArgs {
  var token: String? = null
  var expiresAt: String? = null
  var refreshToken: String? = null
}

@InvokeArg
class TokenExpiryCheckArgs {
  var bufferMinutes: Int = 2
}

@TauriPlugin
class ExamplePlugin(private val activity: Activity): Plugin(activity) {
    companion object {
        private const val TAG = "🢄HillviewPlugin"
        private var pluginInstance: ExamplePlugin? = null
        private var initializationCount = 0
        
        // Permission request codes
        private const val CAMERA_PERMISSION_REQUEST_CODE = 2001
        
        // Storage for pending WebView permission requests
        private var pendingWebViewPermissionRequest: PermissionRequest? = null
        
        fun getPluginInstance(): ExamplePlugin? {
            return pluginInstance
        }
        
        // Centralized permission lock management with camera overrides
        @Volatile
        private var permissionLockHolder: String? = null
        private val permissionLock = Any()
        
        fun acquirePermissionLock(requester: String): Boolean {
            synchronized(permissionLock) {
                if (permissionLockHolder == null) {
                    permissionLockHolder = requester
                    Log.i(TAG, "🔒 Permission lock acquired by: $requester")
                    return true
                } else {
                    val holder = permissionLockHolder!!
                    if (holder == requester) {
                        Log.i(TAG, "🔒 Permission lock already held by requester: $requester")
                        return true
                    }
                    // Special overrides: allow camera requests to proceed (matching Rust logic)
                    else if (requester == "camera") {
                        Log.i(TAG, "🔒 Permission lock granted to camera (override)")
                        return true
                    }
                    else if (requester == "camera-native") {
                        Log.i(TAG, "🔒 Permission lock granted to camera-native (override)")
                        return true
                    }
                    else {
                        Log.i(TAG, "🔒 Permission lock denied to $requester, currently held by: $holder")
                        return false
                    }
                }
            }
        }
        
        fun releasePermissionLock(requester: String): Boolean {
            synchronized(permissionLock) {
                if (permissionLockHolder == requester || permissionLockHolder == null) {
                    permissionLockHolder = null
                    Log.i(TAG, "🔒 Permission lock released by: $requester")
                    return true
                } else {
                    Log.w(TAG, "🔒 Permission lock release failed: held by $permissionLockHolder, not $requester")
                    return false
                }
            }
        }
        
        fun getPermissionLockHolder(): String? {
            synchronized(permissionLock) {
                return permissionLockHolder
            }
        }
        
        private fun cleanupStaticState() {
            // Clear any pending WebView permission requests from previous instance
            pendingWebViewPermissionRequest = null
            Log.i(TAG, "🢄🎥 Static state cleaned up for new plugin instance")
        }
    }
    
    private var sensorService: EnhancedSensorService? = null
    private var preciseLocationService: PreciseLocationService? = null
    private val secureUploadManager: SecureUploadManager = SecureUploadManager(activity)
    private val database: PhotoDatabase = PhotoDatabase.getDatabase(activity)
    private val authManager: AuthenticationManager = AuthenticationManager(activity)
    
    init {
        initializationCount++
        val processId = android.os.Process.myPid()
        
        // Clean up static state from any previous plugin instance
        cleanupStaticState()
        
        pluginInstance = this
        Log.i(TAG, "🢄🎥 Plugin init #$initializationCount - Process ID: $processId")
    }
    
    override fun load(webView: WebView) {
        Log.i(TAG, "🢄🎥 Plugin load() called with WebView: $webView")
        super.load(webView)
        setupWebViewCameraPermissions(webView)
    }
    
    private fun setupWebViewCameraPermissions(webView: WebView) {
        Log.i(TAG, "🢄🎥 Setting up WebView camera permission handling")
        
        // Store the existing WebChromeClient to preserve other functionality
        val existingClient = webView.webChromeClient
        Log.i(TAG, "🢄🎥 Existing WebChromeClient: ${existingClient?.javaClass?.simpleName}")
        
        webView.webChromeClient = object : WebChromeClient() {
            // Prevent duplicate console logging by not forwarding to Android logs
            override fun onConsoleMessage(consoleMessage: ConsoleMessage): Boolean {
                // Don't forward console messages to prevent duplication
                // Let WebView handle them naturally in DevTools/Inspector
                return false
            }
            
            override fun onPermissionRequest(request: PermissionRequest) {
                Log.i(TAG, "🢄🎥 WebView permission request received")
                Log.i(TAG, "🢄🎥 Origin: ${request.origin}")
                Log.i(TAG, "🢄🎥 Resources: ${request.resources?.joinToString(", ")}")
                
                // Check if this is a camera/microphone permission request
                val requestedResources = request.resources ?: emptyArray()
                val needsCamera = requestedResources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE)
                val needsMicrophone = requestedResources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
                
                if (needsCamera || needsMicrophone) {
                    handleCameraPermissionRequest(request, needsCamera, needsMicrophone)
                } else {
                    Log.i(TAG, "🢄🎥 Non-camera permission request, granting automatically")
                    activity.runOnUiThread { request.grant(request.resources) }
                }
            }
        }
    }
    
    private fun handleCameraPermissionRequest(request: PermissionRequest, needsCamera: Boolean, needsMicrophone: Boolean) {
        Log.i(TAG, "🢄🎥 Handling camera permission request (camera: $needsCamera, microphone: $needsMicrophone)")
        
        // Try to acquire permission lock to serialize with location permissions
        val lockAcquired = acquirePermissionLock("camera")
        if (!lockAcquired) {
            Log.w(TAG, "🢄🎥 Permission system busy, denying WebView camera permission")
            activity.runOnUiThread { request.deny() }
            return
        }
        
        // Build list of required Android permissions
        val requiredPermissions = mutableListOf<String>()
        if (needsCamera) requiredPermissions.add(android.Manifest.permission.CAMERA)
        if (needsMicrophone) requiredPermissions.add(android.Manifest.permission.RECORD_AUDIO)
        
        // Check if we already have the required permissions
        val hasAllPermissions = requiredPermissions.all { permission ->
            ContextCompat.checkSelfPermission(activity, permission) == PackageManager.PERMISSION_GRANTED
        }
        
        if (hasAllPermissions) {
            Log.i(TAG, "🢄🎥 Android permissions already granted, granting WebView permission")
            releasePermissionLock("camera")
            activity.runOnUiThread { request.grant(request.resources) }
        } else {
            Log.i(TAG, "🢄🎥 Android permissions needed, requesting from user")
            pendingWebViewPermissionRequest = request
            
            // Request permissions using modern API
            ActivityCompat.requestPermissions(
                activity,
                requiredPermissions.toTypedArray(),
                CAMERA_PERMISSION_REQUEST_CODE
            )
        }
    }
    
    // Handle camera permission results (to be called from MainActivity)
    fun handleCameraPermissionResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        if (requestCode == CAMERA_PERMISSION_REQUEST_CODE) {
            Log.i(TAG, "🢄🎥 Camera permission result received")
            Log.i(TAG, "🢄🎥 Permissions requested: ${permissions.joinToString(", ")}")
            Log.i(TAG, "🢄🎥 Grant results: ${grantResults.joinToString(", ") { if (it == PackageManager.PERMISSION_GRANTED) "GRANTED" else "DENIED" }}")
            
            // Check if all requested permissions were granted
            val allGranted = grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }
            
            // Handle WebView permission request if present
            val pendingWebViewRequest = pendingWebViewPermissionRequest
            if (pendingWebViewRequest != null) {
                Log.i(TAG, "🢄🎥 Handling WebView permission result")
                
                if (allGranted) {
                    Log.i(TAG, "🢄🎥 Camera permissions granted by user, granting WebView permission")
                    activity.runOnUiThread { 
                        pendingWebViewRequest.grant(pendingWebViewRequest.resources)
                    }
                } else {
                    Log.i(TAG, "🢄🎥 Camera permissions denied by user, denying WebView permission")
                    activity.runOnUiThread { 
                        pendingWebViewRequest.deny()
                    }
                }
                
                // Release permission lock and clear pending request
                releasePermissionLock("camera")
                pendingWebViewPermissionRequest = null
            }
            
            // Handle native permission request if present
            val pendingNativeRequest = pendingNativePermissionInvoke
            if (pendingNativeRequest != null) {
                Log.i(TAG, "🢄🎥 Handling native permission result")
                
                val result = JSObject()
                result.put("granted", allGranted)
                
                if (allGranted) {
                    Log.i(TAG, "🢄🎥 Native camera permission granted")
                    
                    // Emit event to frontend to retry camera
                    try {
                        val eventData = JSObject()
                        eventData.put("granted", true)
                        eventData.put("timestamp", System.currentTimeMillis())
                        Log.i(TAG, "🢄🎥 About to emit camera-permission-granted event with data: $eventData")
                        trigger("camera-permission-granted", eventData)
                        Log.i(TAG, "🢄🎥 Successfully emitted camera-permission-granted event")
                    } catch (e: Exception) {
                        Log.e(TAG, "🢄🎥 Failed to emit camera permission event: ${e.message}", e)
                    }
                } else {
                    Log.i(TAG, "🢄🎥 Native camera permission denied")
                    result.put("error", "Camera permission denied by user")
                }
                
                pendingNativeRequest.resolve(result)
                
                // Release permission lock and clear pending request
                releasePermissionLock("camera-native")
                pendingNativePermissionInvoke = null
            }
            
            // If neither pending request exists, log warning
            if (pendingWebViewRequest == null && pendingNativeRequest == null) {
                Log.w(TAG, "🢄🎥 Camera permission result received but no pending requests found")
            }
        }
    }
    
    @Command
    fun startSensor(invoke: Invoke) {
        val mode = try {
            val args = invoke.parseArgs(SensorModeArgs::class.java)
            if (args.mode != null) {
                Log.d(TAG, "🔄 Successfully parsed args with mode=${args.mode}")
                args.mode ?: EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
            } else {
                Log.d(TAG, "🔄 Args parsed as null, using default mode")
                EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
            }
        } catch (e: Exception) {
            Log.e(TAG, "🔄 Failed to parse args, using default mode. Error: ${e.message}")
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
        }
        
        Log.d(TAG, "🔄 Starting enhanced sensor service with mode: $mode (${when(mode) {
            EnhancedSensorService.MODE_ROTATION_VECTOR -> "ROTATION_VECTOR"
            EnhancedSensorService.MODE_GAME_ROTATION_VECTOR -> "GAME_ROTATION_VECTOR"
            EnhancedSensorService.MODE_MADGWICK_AHRS -> "MADGWICK_AHRS"
            EnhancedSensorService.MODE_COMPLEMENTARY_FILTER -> "COMPLEMENTARY_FILTER"
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR -> "UPRIGHT_ROTATION_VECTOR"
            else -> "UNKNOWN"
        }})")
        
        if (sensorService == null) {
            Log.d(TAG, "🔍 Creating new EnhancedSensorService instance")
            sensorService = EnhancedSensorService(activity) { sensorData ->
                // Emit sensor data event
                val data = JSObject()
                data.put("magneticHeading", sensorData.magneticHeading)
                data.put("trueHeading", sensorData.trueHeading)
                data.put("headingAccuracy", sensorData.headingAccuracy)
                data.put("pitch", sensorData.pitch)
                data.put("roll", sensorData.roll)
                data.put("timestamp", sensorData.timestamp)
                data.put("source", sensorData.source)
                
                //Log.v(TAG, "🔍 Emitting sensor data event: magnetic=${sensorData.magneticHeading}, source=${sensorData.source}")
                
                // Trigger the sensor-data event as per Tauri plugin documentation
                try {
                    // Use just the event name (without plugin: prefix) for plugin events
                    trigger("sensor-data", data)
                    //Log.v(TAG, "🔍 Emitted sensor data event: source=${sensorData.source}, magnetic=${sensorData.magneticHeading}")

                } catch (e: Exception) {
                    Log.e(TAG, "🔍 Error triggering event: ${e.message}", e)
                }
            }
        } else {
            Log.d(TAG, "🔍 SensorService already exists")
        }
        
        Log.d(TAG, "🔄 Calling sensorService.startSensor(mode=$mode)")
        sensorService?.startSensor(mode)
        
        // Also start precise location service for better GPS accuracy
        if (preciseLocationService == null) {
            Log.d(TAG, "📍 Initializing PreciseLocationService alongside sensor")
            initializePreciseLocationService()
        }
        
        Log.d(TAG, "🔄 startSensor command completed")
        invoke.resolve()
    }
    
    @Command
    fun stopSensor(invoke: Invoke) {
        Log.d(TAG, "Stopping sensor service")
        sensorService?.stopSensor()
        
        // Also stop precise location service
        Log.d(TAG, "📍 Stopping precise location service")
        preciseLocationService?.stopLocationUpdates()
        
        invoke.resolve()
    }
    
    @Command
    fun startPreciseLocationListener(invoke: Invoke) {
        Log.i(TAG, "📍 Starting precise location listener")
        if (preciseLocationService == null) {
            initializePreciseLocationService()
        }
        preciseLocationService?.startLocationUpdates()
        invoke.resolve()
    }
    
    @Command
    fun stopPreciseLocationListener(invoke: Invoke) {
        Log.i(TAG, "📍 Stopping precise location listener")
        preciseLocationService?.stopLocationUpdates()
        invoke.resolve()
    }
    
    @Command
    fun updateSensorLocation(invoke: Invoke) {
        // Update sensor service for magnetic declination
        // If we're not using Fused Location, this might be called from JS geolocation

        val args = invoke.parseArgs(LocationUpdateArgs::class.java)
        Log.d(TAG, "📍 Updating sensor location: ${args.latitude}, ${args.longitude}")
        
        sensorService?.updateLocation(args.latitude, args.longitude)
        invoke.resolve()
    }
    
    private fun initializePreciseLocationService() {
        preciseLocationService = PreciseLocationService(activity, { locationData ->
            // Update sensor service with precise location for magnetic declination
            sensorService?.updateLocation(locationData.latitude, locationData.longitude)
            
            // Emit location update event that matches the existing GeolocationPosition interface
            val data = JSObject()
            
            // Create coords object to match GeolocationPosition interface
            val coords = JSObject()
            coords.put("latitude", locationData.latitude)
            coords.put("longitude", locationData.longitude)
            coords.put("accuracy", locationData.accuracy)
            coords.put("altitude", locationData.altitude)
            coords.put("altitudeAccuracy", locationData.altitudeAccuracy)
            coords.put("heading", locationData.bearing)
            coords.put("speed", locationData.speed)
            
            data.put("coords", coords)
            data.put("timestamp", locationData.timestamp)
            
            // Add extra precision data
            data.put("provider", locationData.provider)
            data.put("bearingAccuracy", locationData.bearingAccuracy)
            data.put("speedAccuracy", locationData.speedAccuracy)
            
            Log.v(TAG, "📍 ExamplePlugin.kt relaying location update: lat=${locationData.latitude}, lng=${locationData.longitude}, accuracy=${locationData.accuracy}m")

            try {
                // Use the same event name as the geolocation plugin would use
                trigger("location-update", data)
            } catch (e: Exception) {
                Log.e(TAG, "📍 Error triggering location event: ${e.message}", e)
            }
        }, {
            // Location stopped callback
            try {
                Log.i(TAG, "📍 Emitting location-stopped event to frontend")
                trigger("location-stopped", JSObject())
            } catch (e: Exception) {
                Log.e(TAG, "📍 Error triggering location-stopped event: ${e.message}", e)
            }
        })
        
        // Start location updates automatically
        preciseLocationService?.startLocationUpdates()
    }
    
    @Command
    fun setAutoUploadEnabled(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(AutoUploadArgs::class.java)
            val enabled = args.enabled
            
            Log.d(TAG, "📤 Setting auto upload enabled: $enabled")
            
            // Update shared preferences
            val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            prefs.edit().putBoolean("auto_upload_enabled", enabled).apply()
            
            // Schedule or cancel the upload worker
            val workManager = WorkManager.getInstance(activity)
            
            if (enabled) {
                scheduleUploadWorker(workManager, enabled)
                Log.d(TAG, "📤 Auto upload worker scheduled")
            } else {
                workManager.cancelUniqueWork(PhotoUploadWorker.WORK_NAME)
                Log.d(TAG, "📤 Auto upload worker cancelled")
            }
            
            val result = JSObject()
            result.put("success", true)
            result.put("enabled", enabled)
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "📤 Error setting auto upload enabled", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun getUploadStatus(invoke: Invoke) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoDao = database.photoDao()
                val pendingCount = photoDao.getPendingUploadCount()
                val failedCount = photoDao.getFailedUploadCount()
                
                val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
                val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)
                
                val result = JSObject()
                result.put("autoUploadEnabled", autoUploadEnabled)
                result.put("pendingUploads", pendingCount)
                result.put("failedUploads", failedCount)
                
                CoroutineScope(Dispatchers.Main).launch {
                    invoke.resolve(result)
                }
                
            } catch (e: Exception) {
                Log.e(TAG, "📤 Error getting upload status", e)
                CoroutineScope(Dispatchers.Main).launch {
                    val error = JSObject()
                    error.put("error", e.message)
                    invoke.resolve(error)
                }
            }
        }
    }
    
    @Command
    fun setUploadConfig(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(UploadConfigArgs::class.java)
            
            args.serverUrl?.let { secureUploadManager.setServerUrl(it) }
            Log.d(TAG, "📤 Upload config updated")
            
            val result = JSObject()
            result.put("success", true)
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "📤 Error setting upload config", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun uploadPhoto(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(PhotoUploadArgs::class.java)
            val photoId = args.photoId
            
            if (photoId.isNullOrEmpty()) {
                val error = JSObject()
                error.put("success", false)
                error.put("error", "Photo ID is required")
                invoke.resolve(error)
                return
            }
            
            Log.d(TAG, "📤 Manual upload requested for photo: $photoId")
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val photoDao = database.photoDao()
                    val photo = photoDao.getPhotoById(photoId)
                    
                    if (photo == null) {
                        CoroutineScope(Dispatchers.Main).launch {
                            val error = JSObject()
                            error.put("success", false)
                            error.put("error", "Photo not found")
                            invoke.resolve(error)
                        }
                        return@launch
                    }
                    
                    // Update status to uploading
                    photoDao.updateUploadStatus(photoId, "uploading", 0L)
                    
                    // Attempt upload
                    val success = secureUploadManager.secureUploadPhoto(photo)
                    
                    if (success) {
                        photoDao.updateUploadStatus(photoId, "completed", System.currentTimeMillis())
                        Log.d(TAG, "📤 Manual upload successful for photo: $photoId")
                    } else {
                        photoDao.updateUploadFailure(
                            photoId,
                            "failed",
                            photo.retryCount + 1,
                            System.currentTimeMillis(),
                            "Manual upload failed"
                        )
                        Log.e(TAG, "📤 Manual upload failed for photo: $photoId")
                    }
                    
                    CoroutineScope(Dispatchers.Main).launch {
                        val result = JSObject()
                        result.put("success", success)
                        result.put("photoId", photoId)
                        invoke.resolve(result)
                    }
                    
                } catch (e: Exception) {
                    Log.e(TAG, "📤 Error during manual upload", e)
                    CoroutineScope(Dispatchers.Main).launch {
                        val error = JSObject()
                        error.put("success", false)
                        error.put("error", e.message)
                        invoke.resolve(error)
                    }
                }
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "📤 Error parsing upload photo args", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun retryFailedUploads(invoke: Invoke) {
        try {
            Log.d(TAG, "📤 Retrying failed uploads")
            
            // Trigger the upload worker immediately
            val workManager = WorkManager.getInstance(activity)
            val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
            val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)
            
            val workRequest = OneTimeWorkRequestBuilder<PhotoUploadWorker>()
                .setInputData(
                    Data.Builder()
                        .putBoolean(PhotoUploadWorker.KEY_AUTO_UPLOAD_ENABLED, autoUploadEnabled)
                        .build()
                )
                .build()
            
            workManager.enqueue(workRequest)
            
            val result = JSObject()
            result.put("success", true)
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "📤 Error retrying failed uploads", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    private fun scheduleUploadWorker(workManager: WorkManager, autoUploadEnabled: Boolean) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .setRequiresBatteryNotLow(true)
            .build()
        
        val uploadWorkRequest = PeriodicWorkRequestBuilder<PhotoUploadWorker>(
            15, TimeUnit.MINUTES // Run every 15 minutes
        )
            .setConstraints(constraints)
            .setInputData(
                Data.Builder()
                    .putBoolean(PhotoUploadWorker.KEY_AUTO_UPLOAD_ENABLED, autoUploadEnabled)
                    .build()
            )
            .build()
        
        workManager.enqueueUniquePeriodicWork(
            PhotoUploadWorker.WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            uploadWorkRequest
        )
    }
    
    // Authentication Commands
    
    @Command
    fun storeAuthToken(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(StoreAuthTokenArgs::class.java)
            val token = args.token
            val expiresAt = args.expiresAt
            val refreshToken = args.refreshToken
            
            if (token.isNullOrEmpty() || expiresAt.isNullOrEmpty()) {
                val error = JSObject()
                error.put("success", false)
                error.put("error", "Token and expiration date are required")
                invoke.resolve(error)
                return
            }
            
            Log.d(TAG, "🔐 Storing auth token with refresh token: ${refreshToken != null}")
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val success = authManager.storeAuthToken(token, expiresAt, refreshToken)
                    
                    CoroutineScope(Dispatchers.Main).launch {
                        val result = JSObject()
                        result.put("success", success)
                        if (!success) {
                            result.put("error", "Failed to store auth token")
                        }
                        invoke.resolve(result)
                    }
                    
                } catch (e: Exception) {
                    Log.e(TAG, "🔐 Error storing auth token", e)
                    CoroutineScope(Dispatchers.Main).launch {
                        val error = JSObject()
                        error.put("success", false)
                        error.put("error", e.message)
                        invoke.resolve(error)
                    }
                }
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "🔐 Error parsing store auth token args", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun getAuthToken(invoke: Invoke) {
        try {
            //Log.d(TAG, "🔐 Getting auth token (sync version - no refresh)")
            val (_, expiresAt) = authManager.getTokenInfo()
            val validToken = authManager.getValidTokenSync()  // Use sync version for Tauri commands
            
            val result = JSObject()
            result.put("success", true)
            result.put("token", validToken)
            result.put("expiresAt", expiresAt)
            
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "🔐 Error getting auth token", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun clearAuthToken(invoke: Invoke) {
        try {
            Log.d(TAG, "🔐 Clearing auth token")
            val success = authManager.clearAuthToken()
            
            val result = JSObject()
            result.put("success", success)
            if (!success) {
                result.put("error", "Failed to clear auth token")
            }
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "🔐 Error clearing auth token", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun refreshAuthToken(invoke: Invoke) {
        try {
            Log.d(TAG, "🔐 Refreshing auth token")
            
            CoroutineScope(Dispatchers.IO).launch {
                try {
                    val success = authManager.refreshTokenIfNeeded()
                    
                    CoroutineScope(Dispatchers.Main).launch {
                        val result = JSObject()
                        result.put("success", success)
                        if (!success) {
                            result.put("error", "Token refresh failed")
                        }
                        invoke.resolve(result)
                    }
                    
                } catch (e: Exception) {
                    Log.e(TAG, "🔐 Error during token refresh", e)
                    CoroutineScope(Dispatchers.Main).launch {
                        val error = JSObject()
                        error.put("success", false)
                        error.put("error", e.message)
                        invoke.resolve(error)
                    }
                }
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "🔐 Error starting token refresh", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    @Command
    fun isTokenExpired(invoke: Invoke) {
        try {
            val args = invoke.parseArgs(TokenExpiryCheckArgs::class.java)
            val bufferMinutes = args.bufferMinutes
            
            Log.d(TAG, "🔐 Checking if token is expired (buffer: $bufferMinutes minutes)")
            val expired = authManager.isTokenExpired(bufferMinutes)
            
            val result = JSObject()
            result.put("expired", expired)
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "🔐 Error checking token expiry", e)
            val error = JSObject()
            error.put("expired", true) // Assume expired on error for safety
            invoke.resolve(error)
        }
    }
    
    // Command to check if camera permissions can be requested (for WebView coordination)
    @Command
    fun canRequestCameraPermission(invoke: Invoke) {
        val lockAcquired = acquirePermissionLock("camera")
        val result = JSObject()
        result.put("canRequest", lockAcquired)
        result.put("currentHolder", getPermissionLockHolder())
        
        if (!lockAcquired) {
            Log.w(TAG, "🎥 Camera permission request denied - lock held by: ${getPermissionLockHolder()}")
        } else {
            Log.i(TAG, "🎥 Camera permission request approved")
            // Note: We keep the lock - WebView will need to release it after permission handling
        }
        
        invoke.resolve(result)
    }
    
    @Command
    fun releaseCameraPermissionLock(invoke: Invoke) {
        val released = releasePermissionLock("camera")
        val result = JSObject()
        result.put("success", released)
        invoke.resolve(result)
    }
    
    @Command
    fun checkCameraPermission(invoke: Invoke) {
        val hasCameraPermission = ContextCompat.checkSelfPermission(
            activity, 
            android.Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        
        val result = JSObject()
        result.put("granted", hasCameraPermission)
        
        //Log.i(TAG, "🎥 Camera permission check: $hasCameraPermission")
        invoke.resolve(result)
    }
    
    // Store pending native permission request
    private var pendingNativePermissionInvoke: Invoke? = null
    
    @Command
    fun requestCameraPermission(invoke: Invoke) {
        Log.i(TAG, "🎥 Native camera permission request")
        
        val hasCameraPermission = ContextCompat.checkSelfPermission(
            activity, 
            android.Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        
        if (hasCameraPermission) {
            Log.i(TAG, "🎥 Camera permission already granted")
            val result = JSObject()
            result.put("granted", true)
            invoke.resolve(result)
            return
        }
        
        // Check if we can request permission (not permanently denied)
        if (ActivityCompat.shouldShowRequestPermissionRationale(activity, android.Manifest.permission.CAMERA)) {
            Log.i(TAG, "🎥 Should show rationale - permission can be requested")
        } else {
            Log.i(TAG, "🎥 No rationale needed - first time or permanently denied")
        }
        
        // Try to acquire permission lock
        val lockAcquired = acquirePermissionLock("camera-native")
        if (!lockAcquired) {
            Log.w(TAG, "🎥 Permission system busy, cannot request camera permission right now")
            val result = JSObject()
            result.put("granted", false)
            result.put("error", "Permission system busy")
            invoke.resolve(result)
            return
        }
        
        // Store the invoke for the callback
        pendingNativePermissionInvoke = invoke
        
        // Request camera permission directly via Android system
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(android.Manifest.permission.CAMERA),
            CAMERA_PERMISSION_REQUEST_CODE
        )
        
        Log.i(TAG, "🎥 Camera permission request sent to Android system")
    }
    
    @Command
    fun testAuthExpiredNotification(invoke: Invoke) {
        try {
            Log.d(TAG, "🔔 Testing auth expired notification")
            val notificationHelper = NotificationHelper(activity)
            notificationHelper.showAuthExpiredNotification()
            
            val result = JSObject()
            result.put("success", true)
            result.put("message", "Test notification sent")
            invoke.resolve(result)
            
        } catch (e: Exception) {
            Log.e(TAG, "🔔 Error sending test notification", e)
            val error = JSObject()
            error.put("success", false)
            error.put("error", e.message)
            invoke.resolve(error)
        }
    }
    
    // Handle permission request results and forward to PreciseLocationService
    fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        Log.e(TAG, "🔒🔒🔒 PERMISSION RESULT CALLBACK RECEIVED 🔒🔒🔒")
        Log.e(TAG, "🔒 requestCode: $requestCode")
        Log.e(TAG, "🔒 permissions: ${permissions.joinToString(", ")}")
        Log.e(TAG, "🔒 grantResults: ${grantResults.joinToString(", ") { if (it == PackageManager.PERMISSION_GRANTED) "GRANTED" else "DENIED" }}")
        Log.e(TAG, "🔒 CAMERA_PERMISSION_REQUEST_CODE: $CAMERA_PERMISSION_REQUEST_CODE")
        
        // Handle camera permission results
        handleCameraPermissionResult(requestCode, permissions, grantResults)
        
        // Handle location permission results  
        preciseLocationService?.onRequestPermissionsResult(requestCode, permissions, grantResults)
        
        Log.e(TAG, "🔒 Permission result processing complete")
    }
}