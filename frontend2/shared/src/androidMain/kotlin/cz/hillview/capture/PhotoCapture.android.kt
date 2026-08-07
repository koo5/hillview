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
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.UseCaseGroup
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.offset
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
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.semantics
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
import cz.hillview.settings.StorageMode
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.File
import java.io.IOException
import kotlin.coroutines.resume

private const val TAG = "PhotoCapture"

@Composable
actual fun rememberPhotoCapture(): PhotoCapture {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val uploadSettings: UploadSettingsRepository = org.koin.compose.koinInject()
    val capture = remember(lifecycleOwner) {
        AndroidPhotoCapture(context.applicationContext, lifecycleOwner, uploadSettings)
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
@OptIn(ExperimentalCamera2Interop::class)
private class AndroidPhotoCapture(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val uploadSettings: UploadSettingsRepository,
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

    /** How old a fix may be and still count as "has a fix" (and beat manual). */
    private val FIX_FRESH_MS = 15_000L

    // The shutter's voice: the stock click for a healthy capture, a double
    // beep when the position is degraded — audible from a pocket.
    private val shutterSound by lazy {
        android.media.MediaActionSound().apply {
            load(android.media.MediaActionSound.SHUTTER_CLICK)
        }
    }
    private val warnTone by lazy {
        android.media.ToneGenerator(android.media.AudioManager.STREAM_NOTIFICATION, 90)
    }

    private fun playCaptureTone(snapshot: SensorSnapshot) {
        val tone = captureTone(snapshot.locationSource, snapshot.locationAgeMs)
        Log.d(TAG, "capture tone: $tone (source=${snapshot.locationSource} age=${snapshot.locationAgeMs})")
        try {
            when (tone) {
                CaptureTone.Normal ->
                    shutterSound.play(android.media.MediaActionSound.SHUTTER_CLICK)
                CaptureTone.Degraded -> {
                    warnTone.startTone(android.media.ToneGenerator.TONE_PROP_BEEP2, 250)
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "capture tone failed", e)
        }
    }

    private var camera: Camera? = null
    private var isoRange: android.util.Range<Int>? = null
    private var exposureRange: android.util.Range<Long>? = null

    /** The tap-to-focus ring: where, and how the attempt is going. */
    private data class FocusRing(val xPx: Float, val yPx: Float, val phase: FocusPhase)
    private enum class FocusPhase { Focusing, Success, Failed }
    private var focusRing by mutableStateOf<FocusRing?>(null)
    private var focusRingClear: Job? = null

    /**
     * Tap to focus/expose, the native-camera expectation: AF+AE metering at
     * the tapped point, auto-cancelling back to continuous after CameraX's
     * default 5 s. The PreviewView's meteringPointFactory does the
     * view-to-sensor transform, which is the whole reason to tap on the
     * PreviewView rather than a Compose layer above it.
     */
    private fun focusAt(view: PreviewView, x: Float, y: Float) {
        val cam = camera ?: return
        val point = view.meteringPointFactory.createPoint(x, y)
        focusRingClear?.cancel()
        focusRing = FocusRing(x, y, FocusPhase.Focusing)
        val future = cam.cameraControl.startFocusAndMetering(
            androidx.camera.core.FocusMeteringAction.Builder(point).build(),
        )
        future.addListener({
            val outcome = try {
                if (future.get().isFocusSuccessful) FocusPhase.Success else FocusPhase.Failed
            } catch (e: Exception) {
                // Cancelled by a newer tap, or the camera declined — either
                // way the ring should not claim success.
                FocusPhase.Failed
            }
            focusRing = focusRing?.takeIf { it.xPx == x && it.yPx == y }?.copy(phase = outcome)
            focusRingClear = scope.launch {
                kotlinx.coroutines.delay(900)
                focusRing = focusRing?.takeIf { it.xPx == x && it.yPx == y }?.let { null }
            }
        }, ContextCompat.getMainExecutor(context))
    }

    /**
     * What auto-exposure last chose, harvested from preview capture
     * results while AE runs. This is the metering a shutter pin scales
     * from — see [shutterPriorityIso]. Not updated while pinned (the
     * results would only echo our own values back).
     */
    @Volatile private var meteredExposureNs: Long? = null
    @Volatile private var meteredIso: Int? = null
    @Volatile private var lastFrameLog = 0L

    @Volatile private var lastLocation: Location? = null
    @Volatile override var manualLocation: ManualLocation? = null
    @Volatile private var lastOrientation: OrientationSensorData? = null
    private var lastAzimuthPush = 0L

    private val locationListener = LocationListener { location ->
        lastLocation = location
        // Declination (magnetic → true) needs coordinates.
        sensorService.updateLocation(location.latitude, location.longitude)
        val age = SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos
        state = state.copy(
            hasFix = age < FIX_FRESH_MS * 1_000_000,
            fixLatitude = location.latitude,
            fixLongitude = location.longitude,
        )
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

        val previewBuilder = Preview.Builder()
        // Harvest AE's choices from every preview frame — the metering a
        // shutter pin scales its ISO from (see the frame-metadata research:
        // this is the sanctioned per-frame window CameraX offers).
        Camera2Interop.Extender(previewBuilder).setSessionCaptureCallback(
            object : android.hardware.camera2.CameraCaptureSession.CaptureCallback() {
                override fun onCaptureCompleted(
                    session: android.hardware.camera2.CameraCaptureSession,
                    request: CaptureRequest,
                    result: TotalCaptureResult,
                ) {
                    val exp = result.get(CaptureResult.SENSOR_EXPOSURE_TIME)
                    val iso = result.get(CaptureResult.SENSOR_SENSITIVITY)
                    // Ground truth for the pin (the emulator's JPEG EXIF is
                    // canned, so this log is the only honest witness there).
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastFrameLog > 2_000) {
                        lastFrameLog = now
                        Log.d(TAG, "frame exposureNs=$exp iso=$iso pinned=$shutterNs")
                    }
                    if (shutterNs != null) return
                    exp?.let { meteredExposureNs = it }
                    iso?.let { meteredIso = it }
                }
            },
        )
        val preview = previewBuilder.build()
        previewView?.let { preview.surfaceProvider = it.surfaceProvider }

        val group = UseCaseGroup.Builder()
            .addUseCase(preview)
            .addUseCase(capture)
            .build()

        provider.unbindAll()
        val cam = provider.bindToLifecycle(
            lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, group,
        )
        camera = cam

        val info = Camera2CameraInfo.from(cam.cameraInfo)
        val capabilities = info.getCameraCharacteristic(
            CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES,
        )
        val manualSensor = capabilities?.contains(
            CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR,
        ) == true
        isoRange = info.getCameraCharacteristic(
            CameraCharacteristics.SENSOR_INFO_SENSITIVITY_RANGE,
        )
        exposureRange = info.getCameraCharacteristic(
            CameraCharacteristics.SENSOR_INFO_EXPOSURE_TIME_RANGE,
        )
        Log.d(
            TAG,
            "camera caps: manualSensor=$manualSensor iso=$isoRange exposure=$exposureRange " +
                "capabilities=${capabilities?.joinToString()}",
        )
        state = state.copy(manualShutterSupported = manualSensor)

        // Options chosen before (re)binding still apply.
        if (shutterNs != null || ecoPreviewFps) applyRequestOptions()
        cameraBound = true
    }

    override var shutterNs: Long? = null
        set(value) {
            Log.d(TAG, "shutterNs <- $value")
            field = value
            applyRequestOptions()
        }

    override var ecoPreviewFps: Boolean = false
        set(value) {
            if (field == value) return
            field = value
            applyRequestOptions()
        }

    /**
     * ONE application point for every Camera2 request option — the
     * interop's setCaptureRequestOptions REPLACES the whole set, so
     * independent features writing it separately would silently erase each
     * other.
     */
    private fun applyRequestOptions() {
        val cam = camera ?: return
        val builder = CaptureRequestOptions.Builder()
        var applied = "none"

        val pinnedNs = shutterNs
        if (pinnedNs != null && state.manualShutterSupported) {
            val exposure = exposureRange
                ?.let { pinnedNs.coerceIn(it.lower, it.upper) }
                ?: pinnedNs
            val iso = shutterPriorityIso(
                // No metering yet (pin applied before the first preview
                // frame): scale from a plausible daylight midpoint rather
                // than refuse.
                meteredExposureNs = meteredExposureNs ?: 10_000_000L,
                meteredIso = meteredIso ?: 100,
                pinnedExposureNs = exposure,
                minIso = isoRange?.lower ?: 50,
                maxIso = isoRange?.upper ?: 3200,
            )
            builder
                .setCaptureRequestOption(
                    CaptureRequest.CONTROL_AE_MODE,
                    CameraMetadata.CONTROL_AE_MODE_OFF,
                )
                .setCaptureRequestOption(CaptureRequest.SENSOR_EXPOSURE_TIME, exposure)
                .setCaptureRequestOption(CaptureRequest.SENSOR_SENSITIVITY, iso)
            applied = "shutter=$exposure iso=$iso"
            state = state.copy(shutterNs = exposure)
        } else {
            state = state.copy(shutterNs = null)
        }

        if (ecoPreviewFps) {
            // Half the usual 30: visibly alive, meaningfully cheaper.
            builder.setCaptureRequestOption(
                CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
                android.util.Range(15, 15),
            )
            applied += " +eco15fps"
        }

        Camera2CameraControl.from(cam.cameraControl).setCaptureRequestOptions(
            builder.build(),
        ).addListener(
            { Log.d(TAG, "request options applied: $applied") },
            ContextCompat.getMainExecutor(context),
        )
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

        val capturedAtMs = System.currentTimeMillis()
        val filename = "hillview_photo_$capturedAtMs.jpg"
        val snapshot = snapshotSensors(capturedAtMs)
        val settings = uploadSettings.settings.value
        takePictureWithFallback(
            capture = capture,
            chain = PhotoStorage.chain(settings.storage),
            filename = filename,
            hideFromGallery = settings.hideFromGallery,
            snapshot = snapshot,
            watchdog = watchdog,
        )
    }

    /**
     * Walk the storage chain: the first target that both prepares and saves
     * wins. Mirrors device_photos.rs — a target blocked by scoped storage (a
     * direct DCIM write on API 29+) degrades to the next instead of losing
     * the photo.
     */
    private fun takePictureWithFallback(
        capture: ImageCapture,
        chain: List<StorageMode>,
        filename: String,
        hideFromGallery: Boolean,
        snapshot: SensorSnapshot,
        watchdog: Job,
    ) {
        val mode = chain.firstOrNull()
        if (mode == null) {
            watchdog.cancel()
            Log.e(TAG, "every storage target failed")
            state = state.copy(capturing = false, errorMessage = "could not save photo anywhere")
            return
        }
        val prepared = PhotoStorage.outputOptions(context, mode, filename, hideFromGallery)
        if (prepared == null) {
            takePictureWithFallback(
                capture, chain.drop(1), filename, hideFromGallery, snapshot, watchdog,
            )
            return
        }
        val (options, file) = prepared

        capture.takePicture(
            options,
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(results: ImageCapture.OutputFileResults) {
                    watchdog.cancel()
                    try {
                        // MediaStore saves report a content:// URI; file saves
                        // report none, and the path is the locator.
                        val uri = results.savedUri
                        val locator = when {
                            file != null -> file.absolutePath
                            uri != null -> uri.toString()
                            else -> throw IOException("save reported neither file nor uri")
                        }
                        if (file != null) {
                            PhotoExifWriter.write(file, snapshot)
                            // After the EXIF rewrite, so the indexed entry has
                            // the final bytes.
                            if (!hideFromGallery) PhotoStorage.indexInGallery(context, file)
                        } else {
                            PhotoExifWriter.write(context, uri!!, snapshot)
                        }
                        state = state.copy(
                            capturing = false,
                            lastPhoto = CapturedPhoto(locator, filename, snapshot),
                        )
                        playCaptureTone(snapshot)
                        Log.i(TAG, "captured $filename via ${mode.key} -> $locator")
                    } catch (e: Exception) {
                        Log.e(TAG, "post-save handling failed", e)
                        state = state.copy(
                            capturing = false,
                            errorMessage = "EXIF write failed: ${e.message}",
                        )
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    val rest = chain.drop(1)
                    Log.w(TAG, "save via ${mode.key} failed: ${exception.message}")
                    if (rest.isNotEmpty()) {
                        takePictureWithFallback(
                            capture, rest, filename, hideFromGallery, snapshot, watchdog,
                        )
                        return
                    }
                    watchdog.cancel()
                    Log.e(TAG, "capture failed", exception)
                    state = state.copy(
                        capturing = false,
                        errorMessage = "capture failed: ${exception.message}",
                    )
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
        // A fresh fix always beats the manual position (see the interface
        // doc); the manual position only fills a hole, it never overrides.
        val manual = manualLocation.takeIf {
            location == null || (ageMs != null && ageMs > FIX_FRESH_MS)
        }
        return if (manual != null) {
            SensorSnapshot(
                latitude = manual.latitude,
                longitude = manual.longitude,
                // No altitude and no claimed accuracy: this is where the
                // user says they are, not a measurement.
                bearingDeg = orientation?.magneticHeading,
                trueBearingDeg = orientation?.trueHeading,
                bearingSource = orientation?.source,
                capturedAtMs = capturedAtMs,
                locationSource = "manual",
            )
        } else {
            SensorSnapshot(
                latitude = location?.latitude,
                longitude = location?.longitude,
                altitude = location?.takeIf { it.hasAltitude() }?.altitude,
                accuracyM = location?.takeIf { it.hasAccuracy() }?.accuracy,
                bearingDeg = orientation?.magneticHeading,
                trueBearingDeg = orientation?.trueHeading,
                bearingSource = orientation?.source,
                capturedAtMs = capturedAtMs,
                locationSource = location?.let { "gps" },
                locationAgeMs = ageMs,
            )
        }
    }

    fun release() {
        try {
            locationManager.removeUpdates(locationListener)
        } catch (e: Exception) {
            // ignore
        }
        sensorService.stopSensor()
        try {
            shutterSound.release()
            warnTone.release()
        } catch (e: Exception) {
            // lazy instances may never have been created
        }
        cameraProvider?.unbindAll()
        cameraProvider = null
        camera = null
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
                            // Tap detection by hand (down..up within slop):
                            // a GestureDetector would also claim the events
                            // a future pinch-zoom needs.
                            var downX = 0f
                            var downY = 0f
                            setOnTouchListener { v, event ->
                                when (event.actionMasked) {
                                    android.view.MotionEvent.ACTION_DOWN -> {
                                        downX = event.x; downY = event.y; true
                                    }
                                    android.view.MotionEvent.ACTION_UP -> {
                                        val slop = android.view.ViewConfiguration
                                            .get(v.context).scaledTouchSlop
                                        if (kotlin.math.hypot(
                                                event.x - downX,
                                                event.y - downY,
                                            ) <= slop
                                        ) {
                                            v.performClick()
                                            focusAt(this, event.x, event.y)
                                        }
                                        true
                                    }
                                    else -> false
                                }
                            }
                        }.also { previewView = it }
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .clipToBounds(),
                )

                // The focus ring, drawn where the finger landed: yellow
                // while hunting, green on lock, red on failure, gone ~1 s
                // later — the idiom every native camera app trained.
                focusRing?.let { ring ->
                    val colour = when (ring.phase) {
                        FocusPhase.Focusing -> Color(0xFFFFC107)
                        FocusPhase.Success -> Color(0xFF2EA043)
                        FocusPhase.Failed -> Color(0xFFD93025)
                    }
                    val density = androidx.compose.ui.platform.LocalDensity.current
                    val sizeDp = 56.dp
                    Box(
                        Modifier
                            .offset {
                                androidx.compose.ui.unit.IntOffset(
                                    (ring.xPx - with(density) { sizeDp.toPx() } / 2f).toInt(),
                                    (ring.yPx - with(density) { sizeDp.toPx() } / 2f).toInt(),
                                )
                            }
                            .size(sizeDp)
                            .border(2.dp, colour, androidx.compose.foundation.shape.CircleShape)
                            .testTag("camera-focus-ring")
                            .semantics {
                                stateDescription = when (ring.phase) {
                                    FocusPhase.Focusing -> "focusing"
                                    FocusPhase.Success -> "focused"
                                    FocusPhase.Failed -> "focus failed"
                                }
                            },
                    )
                }
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
