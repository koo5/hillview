package cz.hillview.capture

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Environment
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.UseCaseGroup
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.compose.LocalLifecycleOwner
import cz.hillview.core.permissions.PermissionGatePane
import cz.hillview.core.permissions.rememberPermissionsState
import cz.hillview.plugin.EnhancedSensorService
import cz.hillview.plugin.OrientationSensorData
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import kotlin.coroutines.resume

private const val TAG = "PhotoCapture"

@Composable
actual fun rememberPhotoCapture(): PhotoCapture {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val capture = remember(lifecycleOwner) {
        AndroidPhotoCapture(context.applicationContext, lifecycleOwner)
    }
    DisposableEffect(capture) {
        onDispose { capture.release() }
    }
    return capture
}

/**
 * CameraX ImageCapture + a sensor snapshot (GPS via LocationManager, heading
 * via the shared-kt EnhancedSensorService — declination-corrected true north)
 * written into the JPEG's EXIF. Battery discipline: camera and sensors run
 * only while the capture screen is open — release() tears everything down.
 */
private class AndroidPhotoCapture(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
) : PhotoCapture {

    override var state by mutableStateOf(CaptureState())
        private set

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    var previewView: PreviewView? = null

    private var cameraProvider: ProcessCameraProvider? = null
    private var imageCapture: ImageCapture? = null
    private var cameraBound = false

    private val locationManager =
        context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    @Volatile private var lastLocation: Location? = null
    @Volatile private var lastOrientation: OrientationSensorData? = null
    private var lastAzimuthPush = 0L

    private val locationListener = LocationListener { location ->
        lastLocation = location
        // Declination (magnetic → true) needs coordinates.
        sensorService.updateLocation(location.latitude, location.longitude)
        val age = SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos
        state = state.copy(hasFix = age < 15_000_000_000L)
    }

    // The shared-kt heading engine — the same fusion/declination pipeline the
    // Tauri app runs (upright-rotation-vector default mode, EMA smoothing,
    // GeomagneticField declination). Replaces the earlier ad-hoc
    // rotation-vector listener, which produced MAGNETIC azimuth only.
    private val sensorService = EnhancedSensorService(context) { data ->
        lastOrientation = data
        // Throttle state (and recomposition) to ~4 Hz; display true heading.
        val now = SystemClock.elapsedRealtime()
        if (now - lastAzimuthPush > 250) {
            lastAzimuthPush = now
            state = state.copy(bearingDeg = data.trueHeading)
        }
    }

    // Camera is the hard requirement; location soft-degrades (captures still
    // work, just not geotagged — the pane shows a banner).
    fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun openCamera() {
        scope.launch {
            try {
                ensureCameraBound()
                startSensors()
                state = state.copy(ready = true)
            } catch (e: Exception) {
                Log.e(TAG, "failed to open camera", e)
                state = state.copy(errorMessage = "camera failed to open: ${e.message ?: e}")
            }
        }
    }

    private suspend fun ensureCameraBound() {
        if (cameraBound) return
        if (!hasCameraPermission()) throw IllegalStateException("camera permission not granted")

        val provider = suspendCancellableCoroutine<ProcessCameraProvider> { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener({ cont.resume(future.get()) }, ContextCompat.getMainExecutor(context))
        }
        cameraProvider = provider

        val capture = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
            .build()
        imageCapture = capture

        val preview = Preview.Builder().build()
        previewView?.let { preview.surfaceProvider = it.surfaceProvider }

        val group = UseCaseGroup.Builder()
            .addUseCase(preview)
            .addUseCase(capture)
            .build()

        provider.unbindAll()
        provider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, group)
        cameraBound = true
    }

    private var gpsStarted = false
    private var orientationStarted = false

    /**
     * Idempotent; called again when location gets granted after the pane is
     * already up (the soft-degrade path), so GPS joins late.
     */
    @SuppressLint("MissingPermission")
    fun startSensors() {
        if (hasLocationPermission() && !gpsStarted) {
            try {
                locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER, 1_000L, 0f, locationListener,
                )
                locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let {
                    lastLocation = it
                    sensorService.updateLocation(it.latitude, it.longitude)
                }
                gpsStarted = true
            } catch (e: Exception) {
                Log.w(TAG, "GPS updates unavailable", e)
            }
        }
        if (!orientationStarted) {
            sensorService.startSensor()
            orientationStarted = true
        }
    }

    override fun capture() {
        val capture = imageCapture ?: return
        if (state.capturing) return
        state = state.copy(capturing = true, errorMessage = null)

        // A wedged camera pipeline can swallow a still capture without
        // delivering EITHER callback (seen with camera-pipe on the API-31
        // emulator) — never leave the shutter dead forever.
        val watchdog = scope.launch {
            kotlinx.coroutines.delay(15_000)
            if (state.capturing) {
                Log.e(TAG, "capture timed out — no callback from takePicture")
                state = state.copy(capturing = false, errorMessage = "capture timed out")
            }
        }

        val dir = File(
            context.getExternalFilesDir(Environment.DIRECTORY_PICTURES),
            "hillview_photos",
        ).also { it.mkdirs() }
        val capturedAtMs = System.currentTimeMillis()
        val file = File(dir, "hillview_photo_$capturedAtMs.jpg")
        val snapshot = snapshotSensors(capturedAtMs)

        val options = ImageCapture.OutputFileOptions.Builder(file).build()
        capture.takePicture(
            options,
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(results: ImageCapture.OutputFileResults) {
                    watchdog.cancel()
                    try {
                        PhotoExifWriter.write(file, snapshot)
                        state = state.copy(
                            capturing = false,
                            lastPhoto = CapturedPhoto(file.absolutePath, snapshot),
                        )
                        Log.i(TAG, "captured ${file.name} (${file.length()} bytes)")
                    } catch (e: Exception) {
                        Log.e(TAG, "EXIF write failed", e)
                        state = state.copy(capturing = false, errorMessage = "EXIF write failed: ${e.message}")
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    watchdog.cancel()
                    Log.e(TAG, "capture failed", exception)
                    state = state.copy(capturing = false, errorMessage = "capture failed: ${exception.message}")
                }
            },
        )
    }

    private fun snapshotSensors(capturedAtMs: Long): SensorSnapshot {
        val location = lastLocation
        val orientation = lastOrientation
        val ageMs = location?.let {
            (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000
        }
        return SensorSnapshot(
            latitude = location?.latitude,
            longitude = location?.longitude,
            altitude = location?.takeIf { it.hasAltitude() }?.altitude,
            accuracyM = location?.takeIf { it.hasAccuracy() }?.accuracy,
            bearingDeg = orientation?.magneticHeading,
            trueBearingDeg = orientation?.trueHeading,
            bearingSource = orientation?.source,
            capturedAtMs = capturedAtMs,
            locationAgeMs = ageMs,
        )
    }

    fun release() {
        try {
            locationManager.removeUpdates(locationListener)
        } catch (e: Exception) {
            // ignore
        }
        sensorService.stopSensor()
        cameraProvider?.unbindAll()
        cameraProvider = null
        imageCapture = null
        cameraBound = false
        gpsStarted = false
        orientationStarted = false
        scope.cancel()
    }

    @Composable
    override fun CameraPane(modifier: Modifier) {
        // Camera gates the pane; location rides along in the same first
        // request flow but only degrades the experience when denied.
        val camera = rememberPermissionsState(
            permissions = listOf(Manifest.permission.CAMERA),
            alsoRequest = listOf(Manifest.permission.ACCESS_FINE_LOCATION),
        )
        val location = rememberPermissionsState(
            permissions = listOf(Manifest.permission.ACCESS_FINE_LOCATION),
        )

        if (camera.granted) {
            Box(modifier = modifier.background(Color(0xFF111111))) {
                AndroidView(
                    factory = { c ->
                        PreviewView(c).apply {
                            scaleType = PreviewView.ScaleType.FIT_CENTER
                            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                        }.also { previewView = it }
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .clipToBounds(),
                )
                if (!location.granted) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .align(Alignment.TopCenter)
                            .padding(8.dp)
                            .background(Color.Black.copy(alpha = 0.6f))
                            .padding(horizontal = 8.dp)
                            .testTag("capture-location-banner"),
                    ) {
                        Text(
                            text = "No location — photos won't be geotagged",
                            color = Color.White,
                        )
                        TextButton(
                            onClick = {
                                if (location.permanentlyDenied) location.openAppSettings()
                                else location.request()
                            },
                            modifier = Modifier.testTag("capture-location-grant"),
                        ) {
                            Text(if (location.permanentlyDenied) "Settings" else "Enable")
                        }
                    }
                }
            }
        } else {
            PermissionGatePane(
                state = camera,
                explanation = "Camera access is needed to capture photos" +
                    " (location too, so they are geotagged).",
                testTagPrefix = "capture-camera",
                modifier = modifier,
            )
        }

        LaunchedEffect(camera.granted) {
            if (camera.granted) openCamera()
        }
        // GPS joins late when location is granted after the camera was already
        // up (startSensors is idempotent).
        LaunchedEffect(location.granted) {
            if (location.granted && camera.granted) startSensors()
        }
    }
}
