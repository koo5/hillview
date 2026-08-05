package cz.hillview.capture

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Environment
import android.os.SystemClock
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.compose.LocalLifecycleOwner
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
 * P1 capture slice: CameraX ImageCapture + a sensor snapshot (GPS via
 * LocationManager, azimuth via the rotation-vector sensor) written into the
 * JPEG's EXIF. Battery discipline: camera and sensors run only while the
 * capture screen is open — release() tears everything down.
 *
 * Known simplification, tracked for P4: bearing is relative to magnetic
 * north (ref "M" in EXIF); declination correction joins when the tracking
 * code is ported.
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
    private val sensorManager =
        context.getSystemService(Context.SENSOR_SERVICE) as SensorManager

    @Volatile private var lastLocation: Location? = null
    @Volatile private var azimuthDeg: Float? = null
    private var lastAzimuthPush = 0L

    private val locationListener = LocationListener { location ->
        lastLocation = location
        val age = SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos
        state = state.copy(hasFix = age < 15_000_000_000L)
    }

    private val rotationListener = object : SensorEventListener {
        private val rotationMatrix = FloatArray(9)
        private val orientation = FloatArray(3)

        override fun onSensorChanged(event: SensorEvent) {
            SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)
            SensorManager.getOrientation(rotationMatrix, orientation)
            val deg = Math.toDegrees(orientation[0].toDouble()).toFloat()
            val normalized = ((deg % 360f) + 360f) % 360f
            azimuthDeg = normalized
            // Throttle state (and recomposition) to ~4 Hz.
            val now = SystemClock.elapsedRealtime()
            if (now - lastAzimuthPush > 250) {
                lastAzimuthPush = now
                state = state.copy(bearingDeg = normalized)
            }
        }

        override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
    }

    fun hasPermissions(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED &&
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
        if (!hasPermissions()) throw IllegalStateException("permissions not granted")

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

    @SuppressLint("MissingPermission")
    private fun startSensors() {
        if (!hasPermissions()) return
        try {
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, 1_000L, 0f, locationListener,
            )
            locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let {
                lastLocation = it
            }
        } catch (e: Exception) {
            Log.w(TAG, "GPS updates unavailable", e)
        }
        sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)?.let { sensor ->
            sensorManager.registerListener(
                rotationListener, sensor, SensorManager.SENSOR_DELAY_UI,
            )
        }
    }

    override fun capture() {
        val capture = imageCapture ?: return
        if (state.capturing) return
        state = state.copy(capturing = true, errorMessage = null)

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
                    Log.e(TAG, "capture failed", exception)
                    state = state.copy(capturing = false, errorMessage = "capture failed: ${exception.message}")
                }
            },
        )
    }

    private fun snapshotSensors(capturedAtMs: Long): SensorSnapshot {
        val location = lastLocation
        val ageMs = location?.let {
            (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000
        }
        return SensorSnapshot(
            latitude = location?.latitude,
            longitude = location?.longitude,
            altitude = location?.takeIf { it.hasAltitude() }?.altitude,
            accuracyM = location?.takeIf { it.hasAccuracy() }?.accuracy,
            bearingDeg = azimuthDeg,
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
        sensorManager.unregisterListener(rotationListener)
        cameraProvider?.unbindAll()
        cameraProvider = null
        imageCapture = null
        cameraBound = false
        scope.cancel()
    }

    @Composable
    override fun CameraPane(modifier: Modifier) {
        var granted by remember { mutableStateOf(hasPermissions()) }
        val launcher = rememberLauncherForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions()
        ) { results -> granted = results.values.all { it } }

        if (granted) {
            AndroidView(
                factory = { c ->
                    PreviewView(c).apply {
                        scaleType = PreviewView.ScaleType.FIT_CENTER
                        implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    }.also { previewView = it }
                },
                modifier = modifier
                    .fillMaxSize()
                    .background(Color(0xFF111111))
                    .clipToBounds(),
            )
        } else {
            Box(
                modifier = modifier.background(Color(0xFF111111)),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "Camera and location access are needed to capture geotagged photos.",
                        color = Color.White,
                        modifier = Modifier.padding(bottom = 12.dp),
                    )
                    Button(onClick = {
                        launcher.launch(
                            arrayOf(
                                Manifest.permission.CAMERA,
                                Manifest.permission.ACCESS_FINE_LOCATION,
                            )
                        )
                    }) {
                        Text("Grant access")
                    }
                }
            }
        }

        LaunchedEffect(granted) {
            if (granted) openCamera()
        }
    }
}
