package cz.hillview.plugin

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import android.view.OrientationEventListener
import android.webkit.ConsoleMessage
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.core.app.ActivityCompat
import org.json.JSONObject
import androidx.core.content.ContextCompat
import androidx.work.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import app.tauri.annotation.ActivityCallback
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.annotation.Permission
import android.Manifest
import androidx.activity.result.ActivityResult
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import app.tauri.plugin.Invoke
import org.json.JSONArray
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.concurrent.ConcurrentLinkedQueue

import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

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
	var enabled: Boolean? = null
	var prompt_enabled: Boolean? = null
}

@InvokeArg
class UploadConfigArgs {
	var server_url: String? = null
}

@InvokeArg
class PhotoUploadArgs {
	var photo_id: String? = null
}

@InvokeArg
class StoreAuthTokenArgs {
	var token: String? = null
	var expires_at: String? = null
	var refresh_token: String? = null
	var refresh_expiry: String? = null

	override fun toString(): String {
		return "StoreAuthTokenArgs(token=${token?.let { "present" } ?: "null"}, expires_at=$expires_at, refresh_token=${refresh_token?.let { "present" } ?: "null"}, refresh_expiry=$refresh_expiry)"
	}
}

@InvokeArg
class TokenExpiryCheckArgs {
	var buffer_minutes: Int = 2
}

@InvokeArg
class GetAuthTokenArgs {
	var force: Boolean = false
}

@InvokeArg
class AddPhotoArgs {
	var id: String? = null
	var filename: String? = null
	var path: String? = null
	var latitude: Double = 0.0
	var longitude: Double = 0.0
	var altitude: Double? = null
	var bearing: Double? = null
	var captured_at: Long = 0L
	var accuracy: Double = 0.0
	var width: Int = 0
	var height: Int = 0
	var file_size: Long = 0L
	var file_hash: String? = null
}

@InvokeArg
class SharePhotoArgs {
	var title: String? = null
	var text: String? = null
	var url: String? = null
}

@InvokeArg
class GetDevicePhotosArgs {
	var page: Int = 1
	var page_size: Int = 50

	// Optional bounding box for spatial filtering
	var min_lat: Double? = null
	var max_lat: Double? = null
	var min_lng: Double? = null
	var max_lng: Double? = null
}

@InvokeArg
class PhotoWorkerProcessArgs {
	var message_json: String? = null

	override fun toString(): String {
		return "PhotoWorkerProcessArgs(message_json=${message_json?.let { "present(${it.length} chars)" } ?: "null"})"
	}
}

@InvokeArg
class GetBearingForTimestampArgs {
	var timestamp: Long? = null
}

@InvokeArg
class SelectDistributorArgs {
	var package_name: String? = null
}

@InvokeArg
class NotificationSettingsArgs {
	var enabled: Boolean? = null
}

@InvokeArg
class TestShowNotificationArgs {
	var title: String? = null
	var message: String? = null
}

@InvokeArg
class CmdArgs {
	var command: String? = null
	var params: Any? = null
}

@InvokeArg
class SavePhotoToMediaStoreArgs {
	var filename: String? = null
	var imageData: ByteArray = byteArrayOf()
	var hideFromGallery: Boolean? = null
}

@TauriPlugin(
	permissions = [
		Permission(
			strings = [Manifest.permission.POST_NOTIFICATIONS],
			alias = "post_notification"
		),
		Permission(
			strings = [Manifest.permission.WRITE_EXTERNAL_STORAGE],
			alias = "write_external_storage"
		),
		Permission(
			strings = [Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION],
			alias = "location"
		),
		Permission(
			strings = [Manifest.permission.CAMERA],
			alias = "camera"
		)
	]
)
class ExamplePlugin(private val activity: Activity) : Plugin(activity) {
	companion object {
		private const val TAG = "🢄HillviewPlugin"
		private var pluginInstance: ExamplePlugin? = null
		private var initializationCount = 0

		// Permission request codes
		private const val CAMERA_PERMISSION_REQUEST_CODE = 2001
		private const val STORAGE_PERMISSION_REQUEST_CODE = 2002

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
			// TEMP: Bypass lock system for testing - always return true
			Log.i(TAG, "🔒 Permission lock bypassed for: $requester")
			return true

			/* synchronized(permissionLock) {
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
			} */
		}

		fun releasePermissionLock(requester: String): Boolean {
			// TEMP: Bypass lock system for testing - always return true
			Log.i(TAG, "🔒 Permission lock release bypassed for: $requester")
			return true

			/* synchronized(permissionLock) {
				if (permissionLockHolder == requester || permissionLockHolder == null) {
					permissionLockHolder = null
					Log.i(TAG, "🔒 Permission lock released by: $requester")
					return true
				} else {
					permissionLockHolder = null
					Log.w(TAG, "🔒 Permission lock warning: held by $permissionLockHolder, not $requester")
					return true
				}
			} */
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
	private var deviceOrientationProvider: DeviceOrientationProvider? = null
	private val database: PhotoDatabase = PhotoDatabase.getDatabase(activity)
	private val authManager: AuthenticationManager = AuthenticationManager(activity)
	private val photoWorkerService: PhotoWorkerService = PhotoWorkerService(activity, this)
	private val photoUploadManager: PhotoUploadManager = PhotoUploadManager(activity)
	private val geoTrackingManager: GeoTrackingManager = GeoTrackingManager(activity)

	private val myDeviceOrientationSensor: MyDeviceOrientationSensor =
		MyDeviceOrientationSensor(activity, ::triggerOrientationEvent)

	// Screen orientation listener for activity orientation changes
	private var screenOrientationListener: OrientationEventListener? = null

	// Message queue system for reliable Kotlin-frontend communication
	private val messageQueue = ConcurrentLinkedQueue<QueuedMessage>()

	private var activityOrientationAngle: Int = 0
	private var lastNonFlatOrientation: DeviceOrientation = DeviceOrientation.PORTRAIT


	init {
		// Start screen orientation listener when plugin initializes
		startScreenOrientationListener()
	}

	data class QueuedMessage(
		val type: String,
		val payload: JSObject,
		val timestamp: Long = System.currentTimeMillis()
	)

	init {
		initializationCount++
		val processId = android.os.Process.myPid()

		// Clean up static state from any previous plugin instance
		cleanupStaticState()
		geoTrackingManager.dumpAndClear()

		pluginInstance = this
		Log.i(TAG, "🢄🎥 Plugin init #$initializationCount - Process ID: $processId")
	}

	/*override fun onCreate(savedInstanceState: Bundle?) {
		Log.i(TAG, "🢄🎥 onCreate called")
		super.onCreate(savedInstanceState)
		WindowCompat.setDecorFitsSystemWindows(window, true)
		setContentView(R.layout.activity_main)
	}*/


	override fun load(webView: WebView) {
		Log.i(TAG, "🢄🎥 Plugin load() called with WebView: $webView")
		Log.d(TAG, "📲 intent: ${activity.intent}")

		// Configure window to handle insets the old way (non-edge-to-edge)
		//WindowCompat.setDecorFitsSystemWindows(activity.window, true)
		/*// Tell Android we will handle insets ourselves (edge-to-edge).
		WindowCompat.setDecorFitsSystemWindows(activity.window, false)
		// Apply system bar insets as padding to the WebView.
		ViewCompat.setOnApplyWindowInsetsListener(webView) { v, insets ->
		  val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
		  v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
		  // Return insets as-is (don’t consume), so other views can also react if needed.
		  insets
		}*/

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

	private fun handleCameraPermissionRequest(
		request: PermissionRequest,
		needsCamera: Boolean,
		needsMicrophone: Boolean
	) {
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
			Log.i(
				TAG,
				"🢄🎥 Grant results: ${grantResults.joinToString(", ") { if (it == PackageManager.PERMISSION_GRANTED) "GRANTED" else "DENIED" }}"
			)

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

		Log.d(
			TAG, "🔄 Starting enhanced sensor service with mode: $mode (${
				when (mode) {
					EnhancedSensorService.MODE_ROTATION_VECTOR -> "ROTATION_VECTOR"
					EnhancedSensorService.MODE_GAME_ROTATION_VECTOR -> "GAME_ROTATION_VECTOR"
					EnhancedSensorService.MODE_MADGWICK_AHRS -> "MADGWICK_AHRS"
					EnhancedSensorService.MODE_COMPLEMENTARY_FILTER -> "COMPLEMENTARY_FILTER"
					EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR -> "UPRIGHT_ROTATION_VECTOR"
					else -> "UNKNOWN"
				}
			})"
		)

		if (sensorService == null) {
			Log.d(TAG, "🔍 Creating new EnhancedSensorService instance")
			sensorService = EnhancedSensorService(
				context = activity,
				onSensorUpdate = { sensorData ->
					// Emit sensor data event
					val data = JSObject()
					data.put("magnetic_heading", sensorData.magneticHeading)
					data.put("true_heading", sensorData.trueHeading)
					data.put("accuracy_level", sensorData.accuracyLevel)
					data.put("pitch", sensorData.pitch)
					data.put("roll", sensorData.roll)
					data.put("timestamp", sensorData.timestamp)
					data.put("source", sensorData.source)
					//Log.v(TAG, "🔍 Emitting sensor data event: magnetic=${sensorData.magneticHeading}, source=${sensorData.source}")
					trigger("sensor-data", data)

					geoTrackingManager.storeOrientationSensorData(sensorData)
				}
			)
		} else {
			Log.d(TAG, "🔍 SensorService already exists")
		}

		Log.d(TAG, "🔄 Calling sensorService.startSensor(mode=$mode)")
		sensorService?.startSensor(mode)

		// Also start precise location service for better GPS accuracy // magnetic declination // but approximate would probably be enough?
		/*if (preciseLocationService == null) {
			Log.d(TAG, "📍 Initializing PreciseLocationService alongside sensor")
			initializePreciseLocationService()
		}*/

		// Start Google Play Services device orientation provider // fixme - maybe has more accuracy, but has same gimbal lock problem and also cant seem to throttle it (although i guess that wouldnt be a problem)
		/*if (deviceOrientationProvider == null) {
			Log.d(TAG, "🔄 Initializing DeviceOrientationProvider alongside sensor")
			deviceOrientationProvider = DeviceOrientationProvider(activity)
		}
		deviceOrientationProvider?.startOrientationProvider()*/

		Log.d(TAG, "🔄 startSensor command completed")
		invoke.resolve()
	}

	@Command
	fun stopSensor(invoke: Invoke) {
		Log.d(TAG, "Stopping sensor service")
		sensorService?.stopSensor()

		// Also stop precise location service
		//Log.d(TAG, "📍 Stopping precise location service")
		//preciseLocationService?.stopLocationUpdates()

		// Stop device orientation provider
		Log.d(TAG, "🔄 Stopping device orientation provider")
		deviceOrientationProvider?.stopOrientationProvider()

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
/*
	@Command
	fun getSensorAccuracy(invoke: Invoke) {
		//Log.d(TAG, "🔍 get_sensor_accuracy command called")

		val accuracy = sensorService?.getSensorAccuracy() ?: mapOf(
			"magnetometer" to "UNKNOWN",
			"accelerometer" to "UNKNOWN",
			"gyroscope" to "UNKNOWN"
		)

		val result = JSObject()
		result.put("magnetometer", accuracy["magnetometer"])
		result.put("accelerometer", accuracy["accelerometer"])
		result.put("gyroscope", accuracy["gyroscope"])
		result.put("timestamp", System.currentTimeMillis())

		Log.d(TAG, "🔍 Returning sensor accuracy: $accuracy")
		invoke.resolve(result)
	}
*/
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
			coords.put("altitude_accuracy", locationData.altitudeAccuracy)
			coords.put("heading", locationData.bearing)
			coords.put("speed", locationData.speed)

			data.put("coords", coords)
			data.put("timestamp", locationData.timestamp)

			// Add extra precision data
			data.put("provider", locationData.provider)
			data.put("bearing_accuracy", locationData.bearingAccuracy)
			data.put("speed_accuracy", locationData.speedAccuracy)

			Log.v(
				TAG,
				"📍 lat=${locationData.latitude}, lng=${locationData.longitude}, accuracy=${locationData.accuracy}m"
			)

			geoTrackingManager.storeLocationPreciseLocationData(locationData)

			trigger("location-update", data)

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
			val enabled = args.enabled ?: false
			val promptEnabled = args.prompt_enabled ?: true

			Log.i(TAG, "📤 [setAutoUploadEnabled] CALLED with enabled: $enabled, promptEnabled: $promptEnabled")

			// Update shared preferences
			val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
			val previousEnabled = prefs.getBoolean("auto_upload_enabled", false)
			val previousPromptEnabled = prefs.getBoolean("auto_upload_prompt_enabled", true)

			Log.i(
				TAG,
				"📤 [setAutoUploadEnabled] Previous values - enabled: $previousEnabled, promptEnabled: $previousPromptEnabled"
			)
			Log.i(TAG, "📤 [setAutoUploadEnabled] New values - enabled: $enabled, promptEnabled: $promptEnabled")

			// Apply the new settings
			val editor = prefs.edit()
			editor.putBoolean("auto_upload_enabled", enabled)
			editor.putBoolean("auto_upload_prompt_enabled", promptEnabled)
			val commitSuccess = editor.commit()

			Log.i(TAG, "📤 [setAutoUploadEnabled] SharedPreferences commit result: $commitSuccess")

			// Verify the settings were persisted correctly
			val verifyEnabled = prefs.getBoolean("auto_upload_enabled", false)
			val verifyPromptEnabled = prefs.getBoolean("auto_upload_prompt_enabled", true)
			Log.i(
				TAG,
				"📤 [setAutoUploadEnabled] Verification - enabled: $verifyEnabled, promptEnabled: $verifyPromptEnabled"
			)

			// Schedule or cancel the upload worker based on enabled state
			val workManager = WorkManager.getInstance(activity)
			Log.i(TAG, "📤 [setAutoUploadEnabled] WorkManager instance obtained")

			if (enabled) {
				Log.i(TAG, "📤 [setAutoUploadEnabled] Scheduling upload worker...")
				photoUploadManager.scheduleUploadWorker(workManager, enabled)
				Log.i(TAG, "📤 [setAutoUploadEnabled] Auto upload worker scheduled successfully")
			} else {
				Log.i(TAG, "📤 [setAutoUploadEnabled] Cancelling upload worker...")
				workManager.cancelUniqueWork(PhotoUploadWorker.WORK_NAME)
				Log.i(TAG, "📤 [setAutoUploadEnabled] Auto upload worker cancelled successfully")
			}

			val result = JSObject()
			result.put("success", true)
			result.put("enabled", enabled as Boolean)
			result.put("prompt_enabled", promptEnabled as Boolean)

			Log.i(
				TAG,
				"📤 [setAutoUploadEnabled] SUCCESS - returning result: enabled=$enabled, promptEnabled=$promptEnabled"
			)
			invoke.resolve(result)

		} catch (e: Exception) {
			Log.e(TAG, "📤 [setAutoUploadEnabled] ERROR occurred", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}

	@Command
	fun getUploadStatus(invoke: Invoke) {
		//Log.i(TAG, "📤 [getUploadStatus] CALLED - retrieving current auto-upload status")

		CoroutineScope(Dispatchers.IO).launch {
			try {
				//Log.d(TAG, "📤 [getUploadStatus] Getting database counts...")
				val photoDao = database.photoDao()
				val pendingCount = photoDao.getPendingUploadCount()
				val failedCount = photoDao.getFailedUploadCount()

				//Log.d(TAG, "📤 [getUploadStatus] Database counts - pending: $pendingCount, failed: $failedCount")

				//Log.d(TAG, "📤 [getUploadStatus] Reading SharedPreferences...")
				val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
				val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)
				val autoUploadPromptEnabled = prefs.getBoolean("auto_upload_prompt_enabled", true)

				//Log.i(TAG, "📤 [getUploadStatus] Settings - enabled: $autoUploadEnabled, promptEnabled: $autoUploadPromptEnabled")

				val result = JSObject()
				result.put("auto_upload_enabled", autoUploadEnabled)
				result.put("auto_upload_prompt_enabled", autoUploadPromptEnabled)
				result.put("pending_uploads", pendingCount)
				result.put("failed_uploads", failedCount)

				Log.i(
					TAG,
					"📤 [getUploadStatus] enabled=$autoUploadEnabled, promptEnabled=$autoUploadPromptEnabled, pendingUploads=$pendingCount, failedUploads=$failedCount"
				)

				CoroutineScope(Dispatchers.Main).launch {
					invoke.resolve(result)
				}

			} catch (e: Exception) {
				Log.e(TAG, "📤 [getUploadStatus] ERROR occurred", e)
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

			args.server_url?.let { backendUrl ->
				if (backendUrl.isBlank()) {
					Log.e(TAG, "📤 Backend URL is required")
					val error = JSObject()
					error.put("success", false)
					error.put("error", "Backend URL is required")
					invoke.resolve(error)
					return
				}

				Log.d(TAG, "📤 Setting backend URL: $backendUrl")

				// Store in upload preferences for all managers to use
				val uploadPrefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
				val previousUrl = uploadPrefs.getString("server_url", null)

				uploadPrefs.edit()
					.putString("server_url", backendUrl)
					.apply()

				Log.d(TAG, "📤 Backend URL stored in preferences")

				// Trigger push registration (enhanced autoRegisterIfNeeded will handle retries)
				CoroutineScope(Dispatchers.IO).launch {
					try {
						val pushManager = PushDistributorManager(activity)
						pushManager.autoRegisterIfNeeded()
						Log.d(TAG, "📤 Push registration check completed")
					} catch (e: Exception) {
						Log.e(TAG, "📤 Error during push registration", e)
					}
				}
			}

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

	// startAutomaticUpload
	@Command
	fun tryUploads(invoke: Invoke) {
		try {

			photoUploadManager.startAutomaticUpload()

			val result = JSObject()
			result.put("success", true)
			invoke.resolve(result)

		} catch (e: Exception) {
			Log.e(TAG, "🢄📤 tryUploads error", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}

	@Command
	fun startManualUpload(invoke: Invoke) {
		try {
			/*val args = invoke.parseArgs(StartManualUploadArgs::class.java)
			Log.d(TAG, "🔐 Parsed args object: $args")
			val photoId = args.photo_id

			photoUploadManager.startManualUpload(photoId)

			 */
			val result = JSObject()
			result.put("success", true)
			invoke.resolve(result)

		} catch (e: Exception) {
			Log.e(TAG, "🢄📤 startManualUpload error", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}


	// Authentication Commands

	@Command
	fun storeAuthToken(invoke: Invoke) {
		Log.d(TAG, "🔐 storeAuthToken command called")
		try {
			Log.d(TAG, "🔐 Parsing arguments...")
			val args = invoke.parseArgs(StoreAuthTokenArgs::class.java)
			Log.d(TAG, "🔐 Parsed args object: $args")
			val token = args.token
			val expiresAt = args.expires_at
			val refreshToken = args.refresh_token
			val refreshExpiresAt = args.refresh_expiry
			Log.d(TAG, "🔐 Individual field values - refreshExpiry field: $refreshExpiresAt")

			Log.d(
				TAG,
				"🔐 Arguments parsed - token: ${if (token?.isNotEmpty() == true) "present" else "missing"}, expiresAt: $expiresAt"
			)
			Log.d(
				TAG,
				"🔐 Refresh token: ${if (refreshToken?.isNotEmpty() == true) "present" else "missing"}, refreshExpiresAt: $refreshExpiresAt"
			)

			if (token.isNullOrEmpty() || expiresAt.isNullOrEmpty()) {
				Log.e(TAG, "🔐 Validation failed: token or expiresAt is null/empty")
				val error = JSObject()
				error.put("success", false)
				error.put("error", "Token and expiration date are required")
				invoke.resolve(error)
				return
			}

			if (refreshToken != null && refreshExpiresAt.isNullOrEmpty()) {
				Log.e(TAG, "🔐 Validation failed: refresh token without expiry")
				val error = JSObject()
				error.put("success", false)
				error.put("error", "Refresh token provided without expiry date")
				invoke.resolve(error)
				return
			}

			Log.d(TAG, "🔐 Validation passed, proceeding with storage...")

			CoroutineScope(Dispatchers.IO).launch {
				try {
					Log.d(TAG, "🔐 Calling authManager.storeAuthToken...")
					val success = authManager.storeAuthToken(token, expiresAt, refreshToken, refreshExpiresAt)
					Log.d(TAG, "🔐 authManager.storeAuthToken returned: $success")

					CoroutineScope(Dispatchers.Main).launch {
						val result = JSObject()
						result.put("success", success)
						if (!success) {
							result.put("error", "Failed to store auth token")
						}
						Log.d(TAG, "🔐 Resolving with success: $success")
						invoke.resolve(result)
					}

				} catch (e: Exception) {
					Log.e(TAG, "🔐 Exception in storeAuthToken coroutine", e)
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
			val force = try {
				val args = invoke.parseArgs(GetAuthTokenArgs::class.java)
				args?.force ?: false
			} catch (e: Exception) {
				Log.d(TAG, "🔐 No args provided or parsing failed, defaulting to force = false")
				false
			}

			Log.d(TAG, "🔐 Getting auth token (force: $force)")

			// Always use async version that can refresh - both force and normal requests should refresh if needed
			CoroutineScope(Dispatchers.IO).launch {
				try {
					val validToken = if (force) {
						Log.d(TAG, "🔐 Force refresh requested, performing explicit refresh first")
						// Force refresh: explicitly refresh first, then get token
						authManager.refreshTokenIfNeeded()
						authManager.getValidToken()
					} else {
						Log.d(TAG, "🔐 Normal token request with refresh capability")
						// Normal request: get valid token (will refresh if needed)
						authManager.getValidToken()
					}

					val (_, expiresAt) = authManager.getTokenInfo()

					CoroutineScope(Dispatchers.Main).launch {
						val result = JSObject()
						result.put("success", true)
						result.put("token", validToken)
						result.put("expires_at", expiresAt)
						invoke.resolve(result)
					}
				} catch (e: Exception) {
					Log.e(TAG, "🔐 Error getting auth token", e)
					CoroutineScope(Dispatchers.Main).launch {
						val error = JSObject()
						error.put("success", false)
						error.put("error", e.message)
						invoke.resolve(error)
					}
				}
			}

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
			val bufferMinutes = args.buffer_minutes

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
	private var pendingStoragePermissionInvoke: Invoke? = null

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


	// Notification settings management (fixme: stored in hillview_upload_prefs)
	@Command
	fun getNotificationSettings(invoke: Invoke) {
		try {
			val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
			val notificationsEnabled = prefs.getBoolean("notifications_enabled", true) // Default to true

			val result = JSObject()
			result.put("enabled", notificationsEnabled)
			result.put("success", true)

			Log.i(TAG, "🔔 Retrieved notification settings: enabled=$notificationsEnabled")
			invoke.resolve(result)

		} catch (e: Exception) {
			Log.e(TAG, "🔔 Error getting notification settings", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}

	@Command
	fun setNotificationSettings(invoke: Invoke) {
		try {
			val args = invoke.parseArgs(NotificationSettingsArgs::class.java)
			val enabled = args.enabled ?: true // Default to true

			val prefs = activity.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
			val success = prefs.edit()
				.putBoolean("notifications_enabled", enabled)
				.commit()

			val result = JSObject()
			result.put("success", success)

			if (success) {
				Log.i(TAG, "🔔 Notification settings saved: enabled=$enabled")
				result.put("message", "Notification settings saved")
			} else {
				Log.e(TAG, "🔔 Failed to save notification settings")
				result.put("error", "Failed to save settings")
			}

			invoke.resolve(result)

		} catch (e: Exception) {
			Log.e(TAG, "🔔 Error setting notification settings", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}


	@Command
	fun registerClientPublicKey(invoke: Invoke) {
		try {
			Log.d(TAG, "🔐 Registering client public key")

			CoroutineScope(Dispatchers.IO).launch {
				try {
					// Get current valid token for the registration request
					val token = authManager.getValidToken()

					if (token == null) {
						CoroutineScope(Dispatchers.Main).launch {
							val error = JSObject()
							error.put("success", false)
							error.put("error", "No valid auth token available for client key registration")
							invoke.resolve(error)
						}
						return@launch
					}

					// Use the existing registerClientPublicKey method from AuthenticationManager
					val success = authManager.registerClientPublicKey(token)

					CoroutineScope(Dispatchers.Main).launch {
						val result = JSObject()
						result.put("success", success)
						if (!success) {
							result.put("error", "Client public key registration failed")
						}
						invoke.resolve(result)
					}

				} catch (e: Exception) {
					Log.e(TAG, "🔐 Error during client key registration", e)
					CoroutineScope(Dispatchers.Main).launch {
						val error = JSObject()
						error.put("success", false)
						error.put("error", e.message)
						invoke.resolve(error)
					}
				}
			}

		} catch (e: Exception) {
			Log.e(TAG, "🔐 Error starting client key registration", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}

	@Command
	fun getDevicePhotos(invoke: Invoke) {
		Log.d(TAG, "📸 Starting device photos retrieval")

		val args = try {
			val parsedArgs = invoke.parseArgs(GetDevicePhotosArgs::class.java)
			Log.d(
				TAG,
				"📸 Successfully parsed args: page=${parsedArgs?.page}, page_size=${parsedArgs?.page_size}, bounds=[${parsedArgs?.min_lat},${parsedArgs?.min_lng}] to [${parsedArgs?.max_lat},${parsedArgs?.max_lng}]"
			)
			parsedArgs ?: GetDevicePhotosArgs() // Use defaults if null
		} catch (e: Exception) {
			Log.d(TAG, "📸 Failed to parse args (${e.message}), using defaults")
			GetDevicePhotosArgs() // Use default values
		}

		// Args is never null from parseArgs(), proceed with parsed values
		Log.d(TAG, "📸 Using parsed args: page=${args.page}, page_size=${args.page_size}")

		// Process the request with validated args
		processDevicePhotosRequest(invoke, args)
	}

	private fun processDevicePhotosRequest(invoke: Invoke, args: GetDevicePhotosArgs) {
		// Check if spatial filtering is requested
		val hasBounds = args.min_lat != null && args.max_lat != null && args.min_lng != null && args.max_lng != null
		val pageSize = args.page_size.coerceIn(1, 1000) // Allow larger limits for spatial queries

		CoroutineScope(Dispatchers.IO).launch {
			val page = if (hasBounds) 1 else args.page.coerceAtLeast(1)

			val photoDao = database.photoDao()

			val photos: List<PhotoEntity>
			val totalCount: Int
			val totalPages: Int
			val hasMore: Boolean

			if (hasBounds) {
				Log.d(
					TAG,
					"📸 Getting device photos in bounds: [${args.min_lat}, ${args.min_lng}] to [${args.max_lat}, ${args.max_lng}] limit: $pageSize (bearing order)"
				)

				photos = photoDao.getPhotosInBounds(
					args.min_lat!!, args.max_lat!!, args.min_lng!!, args.max_lng!!, pageSize
				)

				// For spatial queries, return simple response without pagination metadata
				totalCount = photos.size
				totalPages = 1
				hasMore = false
			} else {
				Log.d(TAG, "📸 Getting all device photos - page: $page, pageSize: $pageSize")
				val offset = (page - 1) * pageSize

				photos = photoDao.getPhotosPaginated(pageSize, offset)
				totalCount = photoDao.getTotalPhotoCount()
				totalPages = (totalCount + pageSize - 1) / pageSize
				hasMore = page < totalPages
			}

			// Convert PhotoEntity list to JSON array for response
			val photoList = JSONArray()
			for (photo in photos) {
				val photoJson = JSObject()
				photoJson.put("id", photo.id)
				photoJson.put("file_path", photo.path)
				photoJson.put("file_name", photo.filename)
				photoJson.put("file_hash", photo.fileHash)
				photoJson.put("file_size", photo.fileSize)
				photoJson.put("captured_at", photo.capturedAt)
				photoJson.put("created_at", photo.createdAt)
				photoJson.put("latitude", photo.latitude)
				photoJson.put("longitude", photo.longitude)
				photoJson.put("altitude", photo.altitude)
				photoJson.put("bearing", photo.bearing)
				photoJson.put("accuracy", photo.accuracy)
				photoJson.put("width", photo.width)
				photoJson.put("height", photo.height)
				photoJson.put("upload_status", photo.uploadStatus)
				photoJson.put("uploaded_at", photo.uploadedAt)
				photoJson.put("retry_count", photo.retryCount)
				photoJson.put("last_upload_attempt", photo.lastUploadAttempt)
				photoList.put(photoJson)
			}

			val response = JSObject()
			response.put("photos", photoList)
			response.put("last_updated", System.currentTimeMillis())
			// Pagination metadata
			response.put("page", page)
			response.put("page_size", pageSize)
			response.put("total_count", totalCount)
			response.put("total_pages", totalPages)
			response.put("has_more", hasMore)

			Log.d(TAG, "📸 Retrieved ${photos.size} photos (page $page/$totalPages, total: $totalCount)")

			CoroutineScope(Dispatchers.Main).launch {
				invoke.resolve(response)
			}

		}
	}

	@Command
	fun refreshPhotoScan(invoke: Invoke) {
//		try {
//			Log.d(TAG, "🔄 Starting photo scan refresh")
//
//			CoroutineScope(Dispatchers.IO).launch {
//				try {
//					// This would scan configured directories or mediastore api for new photos
//					// For now, return a simple success response
//					val response = JSObject()
//					response.put("photos_added", 0)
//					response.put("scan_errors", 0)
//					response.put("success", true)
//
//					Log.d(TAG, "🔄 Photo scan refresh completed")
//
//					CoroutineScope(Dispatchers.Main).launch {
//						invoke.resolve(response)
//					}
//
//				} catch (e: Exception) {
//					Log.e(TAG, "🔄 Error during photo scan refresh", e)
//					CoroutineScope(Dispatchers.Main).launch {
//						val error = JSObject()
//						error.put("photos_added", 0)
//						error.put("scan_errors", 1)
//						error.put("success", false)
//						error.put("error", e.message)
//						invoke.resolve(error)
//					}
//				}
//			}
//
//		} catch (e: Exception) {
//			Log.e(TAG, "🔄 Error starting photo scan refresh", e)
//			val error = JSObject()
//			error.put("photos_added", 0)
//			error.put("scan_errors", 1)
//			error.put("success", false)
//			error.put("error", e.message)
//			invoke.resolve(error)
//		}
	}

	@Command
	fun importPhotos(invoke: Invoke) {
		try {
			Log.d(TAG, "📂 Starting photo import with file picker")

			// Create file picker intent
			val filePickerIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
				type = "image/*"
				addCategory(Intent.CATEGORY_OPENABLE)
				putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
				putExtra(Intent.EXTRA_LOCAL_ONLY, true)
			}

			Log.i(TAG, "📂 Launching file picker with callback")
			startActivityForResult(invoke, filePickerIntent, "filePickerResult")

		} catch (e: Exception) {
			Log.e(TAG, "❌ Failed to start file picker", e)
			invoke.reject("Failed to start file picker: ${e.message}")
		}
	}

	@Command
	fun addPhotoToDatabase(invoke: Invoke) {
		try {
			Log.d(TAG, "addPhotoToDatabase")

			// Parse the photo data using typed args
			val args = invoke.parseArgs(AddPhotoArgs::class.java)

			// Args is never null from parseArgs(), proceed directly

			Log.d(TAG, "📸 Parsed photo args: id=${args.id}, filename=${args.filename}, path=${args.path}")

			if (args.filename.isNullOrEmpty() || args.path.isNullOrEmpty()) {
				Log.e(TAG, "📸 Invalid photo data - filename: ${args.filename}, path: ${args.path}")
				val error = JSObject()
				error.put("success", false)
				error.put("error", "Invalid photo data - missing filename or path")
				invoke.resolve(error)
				return
			}

			CoroutineScope(Dispatchers.IO).launch {
				try {
					// Hash is always provided by Rust (calculated from bytes in memory)
					val fileHash = args.file_hash ?: throw Exception("File hash is required")

					// Generate ID if not provided (using the hash from Rust)
					val photoId = if (args.id.isNullOrEmpty()) {
						PhotoUtils.generatePhotoId(fileHash)
					} else {
						args.id!!
					}

					Log.d(TAG, "📸 Creating PhotoEntity: id=$photoId, hash=$fileHash")

					// Create PhotoEntity from args
					val photoEntity = PhotoEntity(
						id = photoId,
						filename = args.filename!!,
						path = args.path!!,
						latitude = args.latitude,
						longitude = args.longitude,
						altitude = args.altitude ?: 0.0,
						bearing = args.bearing ?: 0.0,
						capturedAt = args.captured_at,
						accuracy = args.accuracy,
						width = args.width,
						height = args.height,
						fileSize = args.file_size,
						createdAt = System.currentTimeMillis(),
						uploadStatus = "pending",
						fileHash = fileHash  // Always use the calculated/provided hash
					)

					// Insert into database (will replace if exists due to OnConflictStrategy.REPLACE)
					database.photoDao().insertPhoto(photoEntity)

					Log.d(TAG, "📸 Photo added to photoDao: ${photoId}")

					val result = JSObject()
					result.put("success", true)
					result.put("photo_id", photoId)
					invoke.resolve(result)

				} catch (e: Exception) {
					Log.e(TAG, "📸 Error adding photo to database", e)
					val error = JSObject()
					error.put("success", false)
					error.put("error", e.message)
					invoke.resolve(error)
				}
			}

		} catch (e: Exception) {
			Log.e(TAG, "📸 Error parsing photo data", e)
			val error = JSObject()
			error.put("success", false)
			error.put("error", e.message)
			invoke.resolve(error)
		}
	}

	private fun copyUriToPermanentLocation(uri: Uri): File? {
		return try {
			Log.d(TAG, "📂 Copying URI to permanent location: $uri")

			// Get the original filename from URI
			val originalName = getFileNameFromUri(uri)

			// Create destination directory
			val externalStorage = "/storage/emulated/0"
			val hillviewDir = File(externalStorage, "Pictures/Hillview")
			if (!hillviewDir.exists()) {
				hillviewDir.mkdirs()
			}

			// Use original filename if available, otherwise generate one
			val destinationFile = if (originalName != null) {
				File(hillviewDir, originalName)
			} else {
				File(hillviewDir, "imported_${System.currentTimeMillis()}.jpg")
			}

			// Skip if file already exists with same name
			if (destinationFile.exists()) {
				Log.d(TAG, "📂 File already exists, skipping: ${destinationFile.path}")
				return destinationFile // Return the existing file
			}

			Log.d(TAG, "📂 Copying to: ${destinationFile.path}")

			// Copy the file
			activity.contentResolver.openInputStream(uri)?.use { inputStream ->
				destinationFile.outputStream().use { outputStream ->
					inputStream.copyTo(outputStream)
				}
			}

			if (destinationFile.exists() && destinationFile.length() > 0) {
				Log.d(TAG, "📂 Successfully copied file: ${destinationFile.path} (${destinationFile.length()} bytes)")
				destinationFile
			} else {
				Log.e(TAG, "📂 Failed to copy file - destination doesn't exist or is empty")
				null
			}

		} catch (e: Exception) {
			Log.e(TAG, "📂 Error copying URI to permanent location: $uri", e)
			null
		}
	}

	private fun getFileNameFromUri(uri: Uri): String? {
		return try {
			activity.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
				if (cursor.moveToFirst()) {
					val nameIndex = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
					if (nameIndex != -1) {
						cursor.getString(nameIndex)
					} else {
						null
					}
				} else {
					null
				}
			}
		} catch (e: Exception) {
			Log.w(TAG, "📂 Failed to get filename from URI: $uri", e)
			null
		}
	}

	// Handle permission request results (camera only - location now handled via Tauri permission system)
	fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
		Log.d(TAG, "🔒 Permission result received: requestCode=$requestCode")

		when (requestCode) {
			CAMERA_PERMISSION_REQUEST_CODE -> {
				Log.d(TAG, "🔒 Routing to camera permission handler")
				handleCameraPermissionResult(requestCode, permissions, grantResults)
			}
			else -> {
				Log.d(TAG, "🔒 Unknown permission request code: $requestCode (may be handled by Tauri)")
			}
		}
	}


	@ActivityCallback
	private fun filePickerResult(invoke: Invoke, result: ActivityResult) {
		Log.i(TAG, "📂 File picker activity result received: ${result.resultCode}")

		if (result.resultCode == Activity.RESULT_OK && result.data != null) {
			Log.i(TAG, "📂 File picker result: User selected files")

			val selectedUris = mutableListOf<Uri>()

			// Handle multiple files selection
			result.data!!.clipData?.let { clipData ->
				for (i in 0 until clipData.itemCount) {
					selectedUris.add(clipData.getItemAt(i).uri)
				}
			} ?: result.data!!.data?.let { singleUri: Uri ->
				// Handle single file selection
				selectedUris.add(singleUri)
			}

			if (selectedUris.isNotEmpty()) {
				Log.i(TAG, "📂 Processing ${selectedUris.size} selected files")

				// Use coroutine to handle async import - reuse existing photo processing logic
				CoroutineScope(Dispatchers.IO).launch {
					try {
						val importedFiles = mutableListOf<String>()
						val failedFiles = mutableListOf<String>()
						val errors = mutableListOf<String>()

						for (uri in selectedUris) {
							try {
								// Copy the URI content to a permanent location in Hillview folder
								val copiedFile = copyUriToPermanentLocation(uri)
								if (copiedFile != null) {
									// Calculate hash and check for existing photo
									val fileHash = PhotoUtils.calculateFileHash(copiedFile)
									if (fileHash != null) {
										val existingPhoto = database.photoDao().getPhotoByHash(fileHash)

										if (existingPhoto == null) {
											// Create new PhotoEntity using the permanent file path
											val photoEntity =
												PhotoUtils.createPhotoEntityFromFile(copiedFile, fileHash, "imported")
											database.photoDao().insertPhoto(photoEntity)
											importedFiles.add(copiedFile.path)
											Log.d(TAG, "📂 Successfully imported: ${copiedFile.name}")
										} else {
											Log.d(TAG, "📂 Photo already exists: ${copiedFile.name}")
											// Remove the copied file since we already have it
											copiedFile.delete()
											importedFiles.add(copiedFile.path)  // Count as imported since it's in our database
										}
									} else {
										failedFiles.add(uri.toString())
										errors.add("Failed to calculate file hash for copied file")
										// Clean up copied file on hash failure
										copiedFile.delete()
									}
								} else {
									failedFiles.add(uri.toString())
									errors.add("Failed to copy file from URI: $uri")
								}
							} catch (e: IOException) {
								failedFiles.add(uri.toString())
								errors.add("I/O error importing ${uri}: ${e.message}")
								Log.e(TAG, "📂 I/O error importing $uri", e)
							} catch (e: SecurityException) {
								failedFiles.add(uri.toString())
								errors.add("Permission denied accessing ${uri}: ${e.message}")
								Log.e(TAG, "📂 Permission error importing $uri", e)
							}
						}

						// Return result matching FileImportResponse structure (camelCase for serde)
						val response = JSObject()
						response.put("success", importedFiles.isNotEmpty())
						response.put("selected_files", JSONArray(selectedUris.map { it.toString() }))
						response.put("imported_count", importedFiles.size)
						response.put("failed_count", failedFiles.size)
						response.put("failed_files", JSONArray(failedFiles))
						response.put("import_errors", JSONArray(errors))

						Log.i(TAG, "📂 Import complete: ${importedFiles.size} successful, ${failedFiles.size} failed")
						invoke.resolve(response)

					} catch (e: Exception) {
						Log.e(TAG, "📂 Import failed with error: ${e.message}", e)
						invoke.reject("Import failed: ${e.message}")
					}
				}
			} else {
				Log.w(TAG, "📂 No files selected")
				val response = JSObject()
				response.put("success", false)
				response.put("selected_files", JSONArray())
				response.put("imported_count", 0)
				response.put("failed_count", 0)
				response.put("error", "No files selected")
				invoke.resolve(response)
			}
		} else {
			Log.i(TAG, "📂 File picker cancelled by user")
			val response = JSObject()
			response.put("success", false)
			response.put("selected_files", JSONArray())
			response.put("imported_count", 0)
			response.put("failed_count", 0)
			response.put("error", "File selection cancelled")
			invoke.resolve(response)
		}
	}

	@Command
	fun photoWorkerProcess(invoke: Invoke) {
		try {
			//Log.d(TAG, "🢄📸 photoWorkerProcess command called")
			//Log.d(TAG, "🢄📸 invoke object: $invoke")

			val args = invoke.parseArgs(PhotoWorkerProcessArgs::class.java)
			val messageJson = args.message_json ?: args.message_json

			//Log.d(TAG, "🢄📸 messageJson extracted: '${messageJson}' (length: ${messageJson?.length ?: 0})")
			//Log.d(TAG, "🢄📸 field values - messageJson: ${args.message_json}, message_json: ${args.message_json}")

			if (messageJson.isNullOrEmpty()) {
				resolveWithError(invoke, "🢄📸 photoWorkerProcess failed: messageJson is required")
				return
			}

			CoroutineScope(Dispatchers.IO).launch {
				try {
					// Create auth token provider that uses our existing AuthenticationManager
					val authTokenProvider: suspend () -> String? = {
						try {
							val token = authManager.getValidToken()
							Log.d(TAG, "🢄📸 Auth token provided: ${if (token != null) "present" else "null"}")
							token
						} catch (e: Exception) {
							Log.e(TAG, "🢄📸 Error getting auth token", e)
							null
						}
					}

					// Process the photos using PhotoWorkerService (fire and forget like web worker)
					photoWorkerService.processPhotos(messageJson, authTokenProvider)

					//Log.d(TAG, "🢄📸 PhotoWorkerService message processed")

					CoroutineScope(Dispatchers.Main).launch {
						val result = JSObject()
						result.put("success", true)
						invoke.resolve(result)
					}

				} catch (e: Exception) {
					CoroutineScope(Dispatchers.Main).launch {
						resolveWithError(invoke, "🢄📸 Error in photoWorkerProcess coroutine", e)
					}
				}
			}

		} catch (e: Exception) {
			resolveWithError(invoke, "🢄📸 Error parsing photoWorkerProcess args", e)
		}
	}

	@Command
	fun sharePhoto(invoke: Invoke) {
		try {
			Log.d(TAG, "📤 Share photo command called")
			val args = invoke.parseArgs(SharePhotoArgs::class.java)

			val title = args.title ?: "Share Photo"
			val text = args.text ?: "Check out this photo"
			val url = args.url

			Log.d(TAG, "📤 Share args - title: $title, text: $text, url: $url")

			if (url.isNullOrEmpty()) {
				resolveWithError(invoke, "📤 Share failed: URL is required")
				return
			}

			// Create Android share intent
			val shareIntent = Intent().apply {
				action = Intent.ACTION_SEND
				type = "text/plain"
				putExtra(Intent.EXTRA_SUBJECT, title)
				putExtra(Intent.EXTRA_TEXT, "$text\n$url")
			}

			// Create chooser to let user pick share destination
			val chooserIntent = Intent.createChooser(shareIntent, title)

			// Check if there are apps available to handle the share intent
			if (shareIntent.resolveActivity(activity.packageManager) != null) {
				Log.d(TAG, "📤 Launching share intent")
				activity.startActivity(chooserIntent)

				val result = JSObject()
				result.put("success", true)
				result.put("message", "Share intent launched successfully")
				invoke.resolve(result)
			} else {
				resolveWithError(invoke, "📤 No apps available to handle share intent")
			}

		} catch (e: Exception) {
			resolveWithError(invoke, "📤 Error sharing photo", e)
		}
	}


	@Command
	fun getBearingForTimestamp(invoke: Invoke) {
		try {
			val args = invoke.parseArgs(GetBearingForTimestampArgs::class.java)

			if (args.timestamp == null) {
				throw Exception("Timestamp argument is required")
			}

			val timestamp = args.timestamp!! / 1000  // Convert to milliseconds
			Log.d(TAG, "📡 getBearingForTimestamp: Looking up bearing for timestamp $timestamp")

			CoroutineScope(Dispatchers.IO).launch {
				try {
					val bearingEntity = database.bearingDao().getBearingNearTimestamp(timestamp)
					var sourceName = "unknown"
					if (bearingEntity != null) {
						sourceName = database.sourceDao().getSourceNameById(bearingEntity.sourceId) ?: "unknown"
					}

					CoroutineScope(Dispatchers.Main).launch {
						val result = JSObject()
						if (bearingEntity != null) {
							result.put("success", true)
							result.put("found", true)

							result.put("source", sourceName)
							result.put("timestamp", bearingEntity.timestamp)
							result.put("true_heading", bearingEntity.trueHeading.toDouble())

							bearingEntity.magneticHeading?.let { result.put("magnetic_heading", it.toDouble()) }
							bearingEntity.accuracyLevel?.let { result.put("accuracy", it) }
							bearingEntity.pitch?.let { result.put("pitch", it.toDouble()) }
							bearingEntity.roll?.let { result.put("roll", it.toDouble()) }

							Log.d(
								TAG,
								"📡 getBearingForTimestamp: Found bearing ${bearingEntity.trueHeading}° from ${sourceName} at ${bearingEntity.timestamp}"
							)
						} else {
							result.put("success", true)
							result.put("found", false)
							Log.d(TAG, "📡 getBearingForTimestamp: No bearing found for timestamp $timestamp")
						}
						invoke.resolve(result)
					}

				} catch (e: Exception) {
					CoroutineScope(Dispatchers.Main).launch {
						resolveWithError(invoke,"📡 getBearingForTimestamp: Database error", e)
					}
				}
			}

		} catch (e: Exception) {
			resolveWithError(invoke, "📡 getBearingForTimestamp: Error", e)
		}
	}

	// Message Queue System for reliable Kotlin-frontend communication. Messages are queued until frontend is loaded.
	// ================================================================

	/**
	 * Add a message to the queue for frontend polling
	 */
	fun queueMessage(type: String, payload: JSObject) {
		val message = QueuedMessage(type, payload)
		messageQueue.offer(message)
		//Log.d(TAG, "🔔 Queued message: $type")
	}

	@Command
	fun pollMessages(invoke: Invoke) {
		try {
			val messages = mutableListOf<JSObject>()

			// Drain ALL messages to avoid lag
			while (true) {
				val message = messageQueue.poll() ?: break
				val messageObj = JSObject()
				messageObj.put("type", message.type)
				messageObj.put("payload", message.payload)
				messageObj.put("timestamp", message.timestamp)
				messages.add(messageObj)
			}

			val result = JSObject()
			result.put("messages", JSONArray(messages))
			result.put("count", messages.size)

			if (messages.isNotEmpty()) {
				Log.d(TAG, "📨 Polled ${messages.size} messages")
			}

			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "📨 Error polling messages: ${e.message}", e)
		}
	}


	// Push Notification Commands

	@Command
	fun getPushDistributors(invoke: Invoke) {
		try {
			Log.d(TAG, "📨 getPushDistributors called")
			val manager = PushDistributorManager(activity)
			val distributors = manager.getAvailableDistributors()

			Log.d(TAG, "📨 Found ${distributors.size} distributors:")
			distributors.forEach { distributor ->
				Log.d(
					TAG,
					"📨   - ${distributor.displayName} (${distributor.packageName}): available=${distributor.isAvailable}"
				)
			}

			val result = JSObject()
			val distributorsArray = JSONArray()

			distributors.forEach { distributor ->
				val distObj = JSObject()
				distObj.put("package_name", distributor.packageName)
				distObj.put("display_name", distributor.displayName)
				distObj.put("is_available", distributor.isAvailable)
				// Note: Use getPushRegistrationStatus to get selected distributor
				distributorsArray.put(distObj)
			}

			result.put("distributors", distributorsArray)
			result.put("success", true)

			Log.d(TAG, "📨 Returning distributors result: $result")
			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "Error getting push distributors", e)
		}
	}

	@Command
	fun getPushRegistrationStatus(invoke: Invoke) {
		try {
			Log.d(TAG, "📨 getPushRegistrationStatus called")
			val manager = PushDistributorManager(activity)
			val status = manager.getRegistrationStatus()
			val statusMessage = manager.getStatusMessage()
			val selectedDistributor = manager.getSelectedDistributor()
			val pushEndpoint = manager.getPushEndpoint()
			val lastError = manager.getLastError()
			val pushEnabled = manager.isPushEnabled()

			Log.d(TAG, "📨 Push status details:")
			Log.d(TAG, "📨   status: ${status.name.lowercase()}")
			Log.d(TAG, "📨   statusMessage: $statusMessage")
			Log.d(TAG, "📨   selectedDistributor: $selectedDistributor")
			Log.d(TAG, "📨   pushEndpoint: $pushEndpoint")
			Log.d(TAG, "📨   lastError: $lastError")
			Log.d(TAG, "📨   pushEnabled: $pushEnabled")

			val result = JSObject()
			result.put("status", status.name.lowercase())
			result.put("status_message", statusMessage)
			result.put("selected_distributor", selectedDistributor)
			result.put("push_endpoint", pushEndpoint)
			result.put("last_error", lastError)
			result.put("push_enabled", pushEnabled)
			result.put("success", true)

			Log.d(TAG, "📨 Returning result: $result")
			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "Error getting push registration status", e)
		}
	}

	@Command
	fun selectPushDistributor(invoke: Invoke) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val args = invoke.parseArgs(SelectDistributorArgs::class.java)
				val packageName = args.package_name ?: ""

				val manager = PushDistributorManager(activity)
				val success = if (packageName.isEmpty()) {
					manager.unregister()
				} else {
					manager.selectDistributor(packageName)
				}

				val result = JSObject()
				result.put("success", success)
				if (!success) {
					result.put("error", manager.getLastError() ?: "Unknown error")
				}
				invoke.resolve(result)

			} catch (e: Exception) {
				resolveWithError(invoke, "Error selecting push distributor", e)
			}
		}
	}

	@Command
	fun testShowNotification(invoke: Invoke) {
		try {
			Log.d(TAG, "🔔 testShowNotification called")
			val args = invoke.parseArgs(TestShowNotificationArgs::class.java)
			val title = args.title ?: "Test Notification"
			val message = args.message ?: "This is a test notification from Hillview"

			Log.d(TAG, "🔔 Showing test notification: $title - $message")

			val notificationHelper = NotificationHelper(activity)

			// Use a unique notification ID for test notifications
			val testNotificationId = 9999
			notificationHelper.showNotification(
				notificationId = testNotificationId,
				title = title,
				message = message,
				autoCancel = true
			)

			val result = JSObject()
			result.put("success", true)
			result.put("message", "Test notification sent")

			Log.d(TAG, "🔔 Test notification result: $result")
			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "🔔 Error showing test notification", e)
		}
	}

	override fun onNewIntent(intent: Intent) {
		Log.d(TAG, "📲 onNewIntent called with intent: $intent")

		// Update activity intent so getIntentData reads the new intent
		activity.intent = intent

		// Check for notification click action and queue message for frontend
		val clickAction = intent.getStringExtra("click_action")
		if (clickAction != null) {
			Log.d(TAG, "📲 Notification click detected, route: $clickAction")
			val eventData = JSObject()
			eventData.put("route", clickAction)
			queueMessage("notification-click", eventData)
		}
	}

	@Command
	fun getIntentData(invoke: Invoke) {
		val result = JSObject()
		try {
			val intent = activity.intent
			Log.d(TAG, "📲 getIntentData called, intent: $intent")

			if (intent != null) {
				result.put("action", intent.action)
				result.put("dataString", intent.dataString)

				val urlFromIntent = intent.getStringExtra("click_action")
				if (urlFromIntent != null) {
					result.put("click_action", urlFromIntent)
				}

				Log.d(TAG, "📲 Intent data extracted: $result")
			} else {
				Log.d(TAG, "📲 No intent available")
			}

			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "📲 Error getting intent data", e)
		}
	}

	@Command
	fun cmd(invoke: Invoke) {
		try {
			val args = invoke.parseArgs(CmdArgs::class.java)
			val command = args.command
			val params = if (args.params != null) {
				@Suppress("UNCHECKED_CAST")
				JSObject.fromJSONObject(JSONObject(args.params as Map<String, Any?>))
			} else {
				JSObject()
			}

			//Log.d(TAG, "🔧cmd called: command=$command, params=$params")

			when (command) {
				"start_device_orientation_sensor" -> {
					myDeviceOrientationSensor?.setRunning(true)
				}

				"stop_device_orientation_sensor" -> {
					myDeviceOrientationSensor?.setRunning(false)
				}

				"trigger_device_orientation_event" -> {
					myDeviceOrientationSensor?.triggerDeviceOrientationEvent()
				}

				"update_orientation" -> {
					try {
						geoTrackingManager.storeOrientationManual(params)
						//Log.d(TAG, "🔧 Stored manual orientation data")
					} catch (e: Exception) {
						resolveWithError(invoke, "🔧 Failed to store orientation data: ${e.message}", e)
						return
					}
				}

				"update_location" -> {
					try {
						geoTrackingManager.storeLocationManual(params)
						//Log.d(TAG, "🔧 Stored manual location data")
					} catch (e: Exception) {
						resolveWithError(invoke, "🔧 Failed to store location data: ${e.message}", e)
						return
					}
				}

				"geo_tracking_export" -> {
					geoTrackingManager.dumpAndClear(forceDump = true)
					Log.i(TAG, "🔧 Manual geo tracking export triggered")
				}

				"geo_tracking_set_auto_export" -> {
					val enabled = params.getBoolean("enabled") ?: false
					val prefs = activity.getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)
					prefs.edit().putBoolean("auto_export", enabled).apply()
					Log.i(TAG, "🔧 Set geo tracking auto_export: $enabled")
				}

				"geo_tracking_get_auto_export" -> {
					val prefs = activity.getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)
					val enabled = prefs.getBoolean("auto_export", false)
					val result = JSObject()
					result.put("enabled", enabled)
					invoke.resolve(result)
					return
				}

				"get_landscape_compass_armor22_workaround" -> {
					val prefs = activity.getSharedPreferences("landscape_compass_armor22_workaround", Context.MODE_PRIVATE)
					val enabled = prefs.getBoolean("enabled", false)
					val result = JSObject()
					result.put("enabled", enabled)
					invoke.resolve(result)
					return
				}

				"set_landscape_compass_armor22_workaround" -> {
					val enabled = params.getBoolean("enabled") ?: false
					val prefs = activity.getSharedPreferences("landscape_compass_armor22_workaround", Context.MODE_PRIVATE)
					prefs.edit().putBoolean("enabled", enabled).apply()
					Log.i(TAG, "🔧 Set landscape compass Armor 22 workaround: $enabled")
				}

				"device_photos_stats" -> {
					CoroutineScope(Dispatchers.IO).launch {
						try {
							val dao = database.photoDao()
							val result = JSObject()
							result.put("total", dao.getTotalPhotoCount())
							result.put("pending", dao.getPendingUploadCount())
							result.put("uploading", dao.getUploadingCount())
							result.put("completed", dao.getCompletedUploadCount())
							result.put("failed", dao.getFailedUploadCount())
							invoke.resolve(result)
						} catch (e: Exception) {
							resolveWithError(invoke, "Failed to get device photo stats: ${e.message}", e)
						}
					}
					return
				}

				else -> {
					resolveWithError(invoke, "🔧 Unknown command: $command")
					return
				}
			}
			val result = JSObject()
			result.put("success", true)
			invoke.resolve(result)

		} catch (e: Exception) {
			resolveWithError(invoke, "🔧 Error in generic cmd", e)
		}
	}

	@Command
	fun savePhotoToMediaStore(invoke: Invoke) {
		try {
			val args = invoke.parseArgs(SavePhotoToMediaStoreArgs::class.java)
			Log.d(TAG, "📷 savePhotoToMediaStore called: filename=${args.filename}, dataLength=${args.imageData.size}")

			val contentResolver = activity.contentResolver
			val folderName = if (args.hideFromGallery == true) ".Hillview" else "Hillview"

			// Prepare ContentValues for MediaStore
			val contentValues = ContentValues().apply {
				put(MediaStore.Images.Media.DISPLAY_NAME, args.filename)
				put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
				put(MediaStore.Images.Media.RELATIVE_PATH, "${Environment.DIRECTORY_DCIM}/$folderName")
			}

			Log.d(TAG, "📷 Inserting into MediaStore: ${args.filename} in $folderName")

			// Insert into MediaStore and get URI
			val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, contentValues)

			if (uri != null) {
				// Write image data to the URI
				contentResolver.openOutputStream(uri)?.use { outputStream ->
					outputStream.write(args.imageData)
					outputStream.flush()
				}

				val result = JSObject()
				result.put("success", true)
				result.put("path", uri.toString())  // Return content:// URI as path

				Log.d(TAG, "📷✅ Photo saved to MediaStore: ${uri}")
				invoke.resolve(result)

			} else {
				resolveWithError(invoke, "Failed to create MediaStore entry")
			}

		} catch (e: Exception) {
			resolveWithError(invoke, "📷❌ MediaStore save failed", e)
		}
	}


	private fun resolveWithError(invoke: Invoke, message: String, exception: Exception? = null) {
		Log.e(TAG, "📱 $message", exception)
		val error = JSObject()
		error.put("error", message + (exception?.message?.let { ": $it" } ?: ""))
		invoke.resolve(error)
	}


	private fun triggerOrientationEvent(currentDeviceOrientation: DeviceOrientation) {
		val event = JSObject()
		event.put("orientation", currentDeviceOrientation.toString())
		event.put("exif_code", DeviceOrientation.toExifCode(currentDeviceOrientation))
		Log.d(TAG, "📱 device-orientation event trigger: $event")
		trigger("device-orientation", event)
	}

	// Activity lifecycle methods to manage sensor suspension/resumption
	override fun onPause() {
		super.onPause()
		Log.d(TAG, "🔄 Activity onPause - suspending MyDeviceOrientationSensor and stopping screen orientation listener")
		myDeviceOrientationSensor.setSuspended(true)
		stopScreenOrientationListener()
	}

	override fun onResume() {
		super.onResume()
		Log.d(TAG, "🔄 Activity onResume - resuming MyDeviceOrientationSensor and starting screen orientation listener")
		myDeviceOrientationSensor.setSuspended(false)
		startScreenOrientationListener()
	}

	override fun onStop() {
		super.onStop()
		Log.d(TAG, "🔄 Activity onStop - exporting geo tracking data if enabled")
		geoTrackingManager.dumpAndClear()
	}


	private fun startScreenOrientationListener() {
		if (screenOrientationListener == null) {
			screenOrientationListener = object : OrientationEventListener(activity) {
				override fun onOrientationChanged(orientation: Int) {
					//Log.d(TAG, "📱 device-orientation Screen orientation changed...")
					val rotation = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
						activity.display?.rotation ?: android.view.Surface.ROTATION_0
					} else {
						@Suppress("DEPRECATION")
						val windowManager = activity.getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager
						windowManager.defaultDisplay.rotation
					}

					val orientationAngle = when (rotation) {
						android.view.Surface.ROTATION_0 -> 0      // Portrait
						android.view.Surface.ROTATION_90 -> 90    // Landscape (rotated left)
						android.view.Surface.ROTATION_180 -> 180  // Portrait upside down
						android.view.Surface.ROTATION_270 -> 270  // Landscape (rotated right)
						else -> 0 // fallback
					}

					if (orientationAngle != activityOrientationAngle) {
						activityOrientationAngle = orientationAngle
					} else {
						// No change in orientation angle
						return
					}

					Log.d(
						TAG,
						"📱 device-orientation Activity orientation changed - rotation: $rotation, angle: $orientationAngle°"
					)

					// Emit screen-angle event to match Main.svelte listener
					val event = JSObject()
					event.put("angle", orientationAngle)
					event.put("timestamp", System.currentTimeMillis())
					try {
						trigger("screen-angle", event)
						Log.d(TAG, "📱 Emitted device-orientation screen-angle event: angle=$orientationAngle°")
					} catch (e: Exception) {
						Log.e(TAG, "📱 Error emitting device-orientation screen-angle event: ${e.message}", e)
					}
				}
			}
		}
		screenOrientationListener?.enable()
		Log.d(TAG, "📱 device-orientation Screen orientation listener enabled")
	}

	private fun stopScreenOrientationListener() {
		screenOrientationListener?.disable()
		Log.d(TAG, "📱 Screen orientation listener disabled")
	}

}
