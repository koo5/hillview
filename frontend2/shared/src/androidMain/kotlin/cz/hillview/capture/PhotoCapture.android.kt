package cz.hillview.capture

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
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
import androidx.compose.ui.graphics.asImageBitmap
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.IOException
import kotlin.coroutines.resume

private const val TAG = "PhotoCapture"

// Finalization (EXIF rewrite, gallery index) must survive the pane: a photo
// taken a heartbeat before leaving capture still needs its final bytes —
// the controller's own scope dies in release().
private val captureFinishScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

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

    // The shared-kt fused service (PRIORITY_HIGH_ACCURACY) — the same
    // location path the Tauri app's capture geotag rides on.
    private var preciseLocation: cz.hillview.plugin.PreciseLocationService? = null

    // Geo tracking — the same tables and CSV dumps the Tauri app writes
    // (GeoTrackingManager, shared-kt). Two kinds of stream, deliberately:
    // the RAW feeds (fused fixes, orientation samples) as extra data, and
    // the EFFECTIVE stream — sampled through snapshotSensors(), the exact
    // arbitration a shutter press runs — so a retroactive stamp reads
    // "what the app would have written at that instant" (manual claim
    // beats fix, exactly like a real capture; provenance in the source
    // name: effective_gps / effective_manual).
    private val geoTracking by lazy { cz.hillview.plugin.GeoTrackingManager(context) }
    private var effectiveLogJob: Job? = null

    private fun startEffectiveLog() {
        if (effectiveLogJob != null) return
        effectiveLogJob = scope.launch {
            while (true) {
                // Snapshot on Main (volatile field reads, same as a real
                // shutter press); the Room work strictly on IO — the source
                // lookup is a BLOCKING query and Room throws on main.
                val snap = snapshotSensors(System.currentTimeMillis())
                kotlinx.coroutines.withContext(Dispatchers.IO) {
                    logEffectiveSample(snap)
                }
                delay(1_000L)
            }
        }
    }

    private suspend fun logEffectiveSample(snap: SensorSnapshot) {
        val lat = snap.latitude ?: return
        val lon = snap.longitude ?: return
        val sourceName = "effective_" + (snap.locationSource ?: return)
        val sourceId = geoTracking.getOrCreateSourceId(sourceName)
        geoTracking.storeLocationEntity(
            cz.hillview.plugin.LocationEntity(
                timestamp = snap.capturedAtMs,
                latitude = lat,
                longitude = lon,
                sourceId = sourceId,
                altitude = snap.altitude,
                accuracy = snap.accuracyM,
                // The bearing a capture would stamp (true north).
                bearing = snap.trueBearingDeg,
            ),
        )
    }


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
        // A tap always means AUTO at this point: release a standing AE/AF
        // lock and un-pin infinity before metering.
        aeAfLocked = false
        if (focusInfinity) focusInfinity = false
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
    @Volatile override var manualLocationWins: Boolean = false

    override var stampBearing: StampBearing? = null
        set(value) {
            field = value
            // The pill shows what a capture would stamp (Tauri shows
            // bearingState the same way).
            value?.let { state = state.copy(bearingDeg = it.trueDeg) }
        }
    @Volatile private var lastOrientation: OrientationSensorData? = null
    private var lastAzimuthPush = 0L

    private fun onLocation(location: Location) {
        lastLocation = location
        val fixAgeMsAtArrival =
            (SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos) / 1_000_000
        // Declination (magnetic → true) needs coordinates.
        sensorService.updateLocation(location.latitude, location.longitude)
        val age = SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos
        state = state.copy(
            hasFix = age < FIX_FRESH_MS * 1_000_000,
            fixLatitude = location.latitude,
            fixLongitude = location.longitude,
            fixAtMs = System.currentTimeMillis() - fixAgeMsAtArrival,
            fixAltitude = location.takeIf { it.hasAltitude() }?.altitude,
            fixAccuracyM = location.takeIf { it.hasAccuracy() }?.accuracy,
        )
    }

    /** PreciseLocationData → the platform Location the snapshot path reads. */
    private fun asLocation(data: cz.hillview.plugin.PreciseLocationData): Location =
        Location(data.provider ?: "fused").apply {
            latitude = data.latitude
            longitude = data.longitude
            accuracy = data.accuracy
            data.altitude?.let { altitude = it }
            time = data.timestamp
            elapsedRealtimeNanos = data.elapsedRealtimeNanos
        }

    // The shared-kt heading engine — the same fusion/declination pipeline the
    // Tauri app runs (upright-rotation-vector default mode, EMA smoothing,
    // GeomagneticField declination). Replaces the earlier ad-hoc
    // rotation-vector listener, which produced MAGNETIC azimuth only.
    private val sensorService = EnhancedSensorService(context) { data ->
        lastOrientation = data
        // Raw orientation stream (the manager rate-limits storage).
        geoTracking.storeOrientationSensorData(data)
        // Throttled ~4 Hz. The displayed/stamped bearing comes from the
        // map's bearing state now (stampBearing) — here only the
        // magnetometer accuracy rides up, for the calibration button
        // (found unwired: compassAccuracy was never set).
        val now = SystemClock.elapsedRealtime()
        if (now - lastAzimuthPush > 250) {
            lastAzimuthPush = now
            state = state.copy(
                compassAccuracy = data.accuracyLevel.takeIf { it >= 0 },
            )
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

        val captureBuilder = ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
        pinnedResolution?.let { r ->
            // Three fences, because the default selector quietly prefers
            // 4:3: an aspect strategy derived from the request, a bounding
            // strategy, and an exact-match-first filter. Without the first,
            // pinning 1280x720 on the emulator yielded 640x480.
            val ratio43 = kotlin.math.abs(r.width * 3 - r.height * 4)
            val ratio169 = kotlin.math.abs(r.width * 9 - r.height * 16)
            captureBuilder.setResolutionSelector(
                androidx.camera.core.resolutionselector.ResolutionSelector.Builder()
                    .setAspectRatioStrategy(
                        androidx.camera.core.resolutionselector.AspectRatioStrategy(
                            if (ratio43 <= ratio169) {
                                androidx.camera.core.AspectRatio.RATIO_4_3
                            } else {
                                androidx.camera.core.AspectRatio.RATIO_16_9
                            },
                            androidx.camera.core.resolutionselector.AspectRatioStrategy
                                .FALLBACK_RULE_AUTO,
                        ),
                    )
                    .setResolutionStrategy(
                        androidx.camera.core.resolutionselector.ResolutionStrategy(
                            android.util.Size(r.width, r.height),
                            androidx.camera.core.resolutionselector.ResolutionStrategy
                                .FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER,
                        ),
                    )
                    .setResolutionFilter { sizes, _ ->
                        sizes.sortedByDescending {
                            it.width == r.width && it.height == r.height
                        }
                    }
                    .build(),
            )
        }
        val capture = captureBuilder.build()
        imageCapture = capture

        val preview = buildPreviewUseCase()
        previewUseCase = preview

        val group = UseCaseGroup.Builder()
            .addUseCase(preview)
            .addUseCase(capture)
            .build()

        provider.unbindAll()
        val cam = provider.bindToLifecycle(
            lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, group,
        )
        camera = cam
        previewBound = true
        applyZoomAfterBind(cam)

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
        // The real JPEG menu, from the sensor itself — the whole point of
        // diverging from Tauri's hardcoded four (see the contract).
        val jpegSizes = info.getCameraCharacteristic(
            CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP,
        )?.getOutputSizes(android.graphics.ImageFormat.JPEG)
            ?.sortedByDescending { it.width.toLong() * it.height }
            ?.map { CaptureResolution(it.width, it.height) }
            ?.distinct()
            .orEmpty()

        val afModes = info.getCameraCharacteristic(
            CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES,
        )
        val minFocusDistance = info.getCameraCharacteristic(
            CameraCharacteristics.LENS_INFO_MINIMUM_FOCUS_DISTANCE,
        )
        val manualFocus =
            afModes?.contains(CameraMetadata.CONTROL_AF_MODE_OFF) == true &&
                (minFocusDistance ?: 0f) > 0f

        state = state.copy(
            manualShutterSupported = manualSensor,
            manualFocusSupported = manualFocus,
            availableResolutions = jpegSizes,
            selectedResolution = pinnedResolution,
        )
        Log.d(
            TAG,
            "bound: pinned=$pinnedResolution actual=${capture.resolutionInfo?.resolution} " +
                "jpegSizes=${jpegSizes.take(4)}",
        )

        // Options chosen before (re)binding still apply.
        if (shutterNs != null || ecoPreviewFps != null) applyRequestOptions()
        cameraBound = true
        // A rebind starts with the preview in the group — re-enter whatever
        // eco duty mode is chosen.
        restartEcoDuty()
    }

    /**
     * A FRESH use case for every (re)attach: a Preview reused across
     * unbind/bind never re-attaches its surface (emulator-verified: the
     * session streams, the TextureView stays black) — the duty engine
     * rebuilds instead.
     */
    private fun buildPreviewUseCase(): Preview {
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
        return preview
    }

    @Volatile private var pinnedResolution: CaptureResolution? = null

    override fun selectResolution(resolution: CaptureResolution?) {
        if (resolution == pinnedResolution) return
        pinnedResolution = resolution
        // A use case's resolution is fixed at bind time; changing it means
        // rebinding. openCamera() rebuilds everything from current fields.
        if (cameraBound) {
            cameraBound = false
            cameraProvider?.unbindAll()
            openCamera()
        }
    }

    override var shutterNs: Long? = null
        set(value) {
            Log.d(TAG, "shutterNs <- $value")
            field = value
            applyRequestOptions()
        }

    override var ecoPreviewFps: Float? = null
        set(value) {
            if (field == value) return
            field = value
            applyRequestOptions()
            restartEcoDuty()
        }

    // --- native zoom / focus (deliberate divergence from the original's
    // necessity-born sliders: pinch to zoom, long-press to lock AE/AF,
    // ∞/auto in the camera menu — the native grammar) ---

    var zoomRatio by mutableStateOf(1f)
        private set
    private var zoomRange: ClosedFloatingPointRange<Float> = 1f..1f
    var zoomChipVisible by mutableStateOf(false)
        private set
    private var zoomChipJob: Job? = null
    var aeAfLocked by mutableStateOf(false)
        private set

    fun setZoom(ratio: Float) {
        val cam = camera ?: return
        val clamped = ratio.coerceIn(zoomRange)
        zoomRatio = clamped
        cam.cameraControl.setZoomRatio(clamped)
        zoomChipVisible = true
        zoomChipJob?.cancel()
        zoomChipJob = scope.launch {
            delay(1_200L)
            zoomChipVisible = false
        }
    }

    /** Re-arm zoom after any (re)bind — the control is per camera session. */
    private fun applyZoomAfterBind(cam: androidx.camera.core.Camera) {
        cam.cameraInfo.zoomState.value?.let {
            zoomRange = it.minZoomRatio..it.maxZoomRatio
        }
        if (zoomRatio > 1f) {
            cam.cameraControl.setZoomRatio(zoomRatio.coerceIn(zoomRange))
        }
    }

    override var focusInfinity: Boolean = false
        set(value) {
            if (field == value) return
            field = value
            applyRequestOptions()
        }

    // --- the sub-AE eco band: duty-cycling the preview use case ---
    //
    // At and below ECO_DUTY_BAND_MAX_FPS the Preview use case is unbound
    // between beats (AE ranges cover 7..30). ImageCapture stays bound
    // throughout, so the shutter never waits. One caveat, deliberate:
    // shutter-pin ISO scales from preview-frame metering, which goes
    // stale while frozen.
    //
    // The frozen frame is NOT free: unbinding blanks the TextureView
    // (emulator-verified — it does not hold its last frame), so the last
    // preview bitmap is grabbed at unbind time and CameraPane draws it
    // over the blank surface while the preview is down.
    private var previewUseCase: Preview? = null
    private var previewBound = false
    private var ecoDutyJob: Job? = null
    private var captureRefreshJob: Job? = null

    var frozenFrame by mutableStateOf<android.graphics.Bitmap?>(null)
        private set

    private fun setPreviewBound(want: Boolean) {
        val provider = cameraProvider ?: return
        val preview = previewUseCase ?: return
        if (want == previewBound || !cameraBound) return
        if (want) {
            runCatching {
                // Fresh use case every time — see buildPreviewUseCase.
                val fresh = buildPreviewUseCase()
                previewUseCase = fresh
                camera = provider.bindToLifecycle(
                    lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, fresh,
                )
                previewBound = true
                // A fresh bind means fresh capture-request options — and
                // the zoom, which is per camera session too.
                applyZoomAfterBind(camera!!)
                applyRequestOptions()
            }.onFailure { Log.w(TAG, "preview rebind failed", it) }
            // Drop the freeze only when frames ACTUALLY render — the
            // session's first on-screen frame can trail the bind by most
            // of a second; a timed clear flashed black through the beat.
            // (Also THE restart-cost number for the stream-vs-restarts
            // question: bind → first rendered frame.)
            val bindAt = SystemClock.elapsedRealtime()
            CaptureStatsLog.increment("preview binds", System.currentTimeMillis())
            scope.launch {
                waitForPreviewStreaming(3_000L)
                CaptureStatsLog.record(
                    "bind→streaming",
                    SystemClock.elapsedRealtime() - bindAt,
                    System.currentTimeMillis(),
                )
                if (previewBound) frozenFrame = null
            }
        } else {
            // Grab only a LIVE frame: a bind whose session never reached
            // the screen would freeze black — better to keep the last
            // good frame. (Main thread: PreviewView.getBitmap is legal.)
            val streaming =
                previewView?.previewStreamState?.value == PreviewView.StreamState.STREAMING
            if (streaming) previewView?.bitmap?.let { frozenFrame = it }
            Log.d(TAG, "eco freeze: streaming=$streaming grabbed=${streaming && frozenFrame != null}")
            runCatching {
                provider.unbind(preview)
                previewBound = false
            }.onFailure { Log.w(TAG, "preview unbind failed", it) }
        }
    }

    /** Resolves when the PreviewView reports real frames, or the timeout. */
    private suspend fun waitForPreviewStreaming(timeoutMs: Long) {
        val view = previewView ?: return
        withTimeoutOrNull(timeoutMs) {
            suspendCancellableCoroutine { cont ->
                val streamState = view.previewStreamState
                val observer = object : androidx.lifecycle.Observer<PreviewView.StreamState> {
                    override fun onChanged(value: PreviewView.StreamState) {
                        if (value == PreviewView.StreamState.STREAMING) {
                            streamState.removeObserver(this)
                            if (cont.isActive) cont.resume(Unit)
                        }
                    }
                }
                streamState.observeForever(observer)
                cont.invokeOnCancellation {
                    scope.launch { streamState.removeObserver(observer) }
                }
            }
        }
    }

    private fun restartEcoDuty() {
        ecoDutyJob?.cancel()
        ecoDutyJob = null
        captureRefreshJob?.cancel()
        val eco = ecoPreviewFps
        when {
            // Continuous preview: default, or the AE-range band.
            eco == null || eco > ECO_DUTY_BAND_MAX_FPS -> setPreviewBound(true)
            // Capture-only: frozen until a capture lands (ecoCaptureRefresh).
            eco <= 0f -> setPreviewBound(false)
            // 0.1..1 fps: a beat of live preview every 1/fps seconds. The
            // beat is stream-gated, not timed: bind, wait for real frames
            // (the emulator's session start can eat most of a second),
            // show a few, grab the freeze, unbind.
            else -> {
                val periodMs = (1000f / eco).toLong()
                ecoDutyJob = scope.launch {
                    while (true) {
                        val beatStart = SystemClock.elapsedRealtime()
                        CaptureStatsLog.increment("eco beats", System.currentTimeMillis())
                        setPreviewBound(true)
                        waitForPreviewStreaming(2_500L)
                        delay(300L)
                        setPreviewBound(false)
                        val elapsed = SystemClock.elapsedRealtime() - beatStart
                        delay((periodMs - elapsed).coerceAtLeast(300L))
                    }
                }
            }
        }
    }

    /** Capture-only mode: the capture IS the refresh signal. */
    private fun ecoCaptureRefresh() {
        if (ecoPreviewFps != 0f) return
        captureRefreshJob?.cancel()
        captureRefreshJob = scope.launch {
            setPreviewBound(true)
            waitForPreviewStreaming(2_500L)
            delay(600L)
            if (ecoPreviewFps == 0f) setPreviewBound(false)
        }
    }

    /**
     * Long-press: AE/AF LOCK at the pressed point — metering runs once and
     * stays (no auto-cancel), the native camera idiom. A later tap
     * refocuses and releases.
     */
    private fun lockFocusAt(view: PreviewView, x: Float, y: Float) {
        val cam = camera ?: return
        if (focusInfinity) focusInfinity = false
        val point = view.meteringPointFactory.createPoint(x, y)
        focusRingClear?.cancel()
        focusRing = FocusRing(x, y, FocusPhase.Focusing)
        val action = androidx.camera.core.FocusMeteringAction.Builder(point)
            .disableAutoCancel()
            .build()
        val future = cam.cameraControl.startFocusAndMetering(action)
        future.addListener({
            val locked = try {
                future.get().isFocusSuccessful
            } catch (e: Exception) {
                false
            }
            aeAfLocked = locked
            focusRing = focusRing?.takeIf { it.xPx == x && it.yPx == y }
                ?.copy(phase = if (locked) FocusPhase.Success else FocusPhase.Failed)
            focusRingClear = scope.launch {
                delay(900)
                focusRing = focusRing?.takeIf { it.xPx == x && it.yPx == y }?.let { null }
            }
        }, ContextCompat.getMainExecutor(context))
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

        if (focusInfinity && state.manualFocusSupported) {
            // The vista pin: AF off, lens at infinity (0 diopters).
            builder
                .setCaptureRequestOption(
                    CaptureRequest.CONTROL_AF_MODE,
                    CameraMetadata.CONTROL_AF_MODE_OFF,
                )
                .setCaptureRequestOption(CaptureRequest.LENS_FOCUS_DISTANCE, 0f)
            applied += " +focusInf"
        }
        state = state.copy(focusInfinity = focusInfinity && state.manualFocusSupported)

        val eco = ecoPreviewFps
        if (eco != null && eco < 30f) {
            // The AE band (8..29): the requested cap, as a fixed range —
            // the proven (15,15) mechanism, now tunable. In the duty-cycled
            // band the on-beat still runs capped at the duty ceiling so the
            // beat itself is cheap.
            val capFps = eco.coerceAtLeast(ECO_AE_MIN_FPS).toInt()
            builder.setCaptureRequestOption(
                CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
                android.util.Range(capFps, capFps),
            )
            applied += " +eco${capFps}fps"
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
                // Fused delivers its current best estimate immediately and
                // precise fixes on a 1 s cadence; freshness is judged at
                // capture time (FIX_FRESH_MS), so a stale seed can never
                // geotag a photo.
                preciseLocation = cz.hillview.plugin.PreciseLocationService(
                    context,
                    onLocationUpdate = { data ->
                        // Raw fused stream, as the Tauri plugin logs it.
                        geoTracking.storeLocationPreciseLocationData(data)
                        onLocation(asLocation(data))
                    },
                ).also { it.startLocationUpdates() }
                gpsStarted = true
            } catch (e: Exception) {
                Log.w(TAG, "location updates unavailable", e)
            }
        }
        if (!orientationStarted) {
            sensorService.startSensor()
            orientationStarted = true
        }
        startEffectiveLog()
    }

    // Stats timeline: shutter press → CameraX JPEG → finalization; plus
    // inter-shot cadence. Feeds the copyable Stats dialog.
    @Volatile private var captureStartMs = 0L
    @Volatile private var lastShotAtMs = 0L

    init {
        CaptureStatsLog.platformLines = {
            buildList {
                if (android.os.Build.VERSION.SDK_INT >= 29) {
                    val pm = context.getSystemService(Context.POWER_SERVICE)
                        as android.os.PowerManager
                    val status = when (pm.currentThermalStatus) {
                        android.os.PowerManager.THERMAL_STATUS_NONE -> "NONE"
                        android.os.PowerManager.THERMAL_STATUS_LIGHT -> "LIGHT"
                        android.os.PowerManager.THERMAL_STATUS_MODERATE -> "MODERATE"
                        android.os.PowerManager.THERMAL_STATUS_SEVERE -> "SEVERE"
                        android.os.PowerManager.THERMAL_STATUS_CRITICAL -> "CRITICAL"
                        android.os.PowerManager.THERMAL_STATUS_EMERGENCY -> "EMERGENCY"
                        android.os.PowerManager.THERMAL_STATUS_SHUTDOWN -> "SHUTDOWN"
                        else -> "?"
                    }
                    add("thermal: $status")
                }
            }
        }
    }

    override fun capture() {
        val capture = imageCapture ?: return
        if (state.capturing) return
        captureStartMs = SystemClock.elapsedRealtime()
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
                    val shotAt = SystemClock.elapsedRealtime()
                    val wall = System.currentTimeMillis()
                    CaptureStatsLog.record("shutter→jpeg", shotAt - captureStartMs, wall)
                    if (lastShotAtMs != 0L) {
                        CaptureStatsLog.record("cadence", shotAt - lastShotAtMs, wall)
                    }
                    lastShotAtMs = shotAt
                    // The shutter is FREE the moment CameraX hands the JPEG
                    // over: tone, eco refresh, and the next capture all
                    // proceed now. The EXIF rewrite below is a WHOLE-FILE
                    // copy (ExifInterface has no surgical patch) — 4-25 MB
                    // on a real sensor — and used to run right here on the
                    // main executor: per-shot jank, and the throughput
                    // ceiling that killed short-interval mode under thermal
                    // throttling in the Tauri app. Off-main also means
                    // overlapping captures finalize in parallel.
                    state = state.copy(capturing = false)
                    ecoCaptureRefresh()
                    playCaptureTone(snapshot)
                    captureFinishScope.launch {
                        val finalizeStart = SystemClock.elapsedRealtime()
                        try {
                            // MediaStore saves report a content:// URI; file
                            // saves report none, and the path is the locator.
                            val uri = results.savedUri
                            val locator = when {
                                file != null -> file.absolutePath
                                uri != null -> uri.toString()
                                else -> throw IOException("save reported neither file nor uri")
                            }
                            if (file != null) {
                                PhotoExifWriter.write(file, snapshot)
                                // After the EXIF rewrite, so the indexed entry
                                // has the final bytes.
                                if (!hideFromGallery) PhotoStorage.indexInGallery(context, file)
                            } else {
                                PhotoExifWriter.write(context, uri!!, snapshot)
                            }
                            // lastPhoto ONLY after the final bytes exist:
                            // the upload enqueue hashes the file it triggers
                            // on — publishing earlier would hash pre-EXIF
                            // bytes.
                            kotlinx.coroutines.withContext(Dispatchers.Main) {
                                state = state.copy(
                                    lastPhoto = CapturedPhoto(locator, filename, snapshot),
                                )
                            }
                            CaptureStatsLog.record(
                                "finalize(exif+index)",
                                SystemClock.elapsedRealtime() - finalizeStart,
                                System.currentTimeMillis(),
                            )
                            Log.i(TAG, "captured $filename via ${mode.key} -> $locator")
                        } catch (e: Exception) {
                            Log.e(TAG, "post-save handling failed", e)
                            kotlinx.coroutines.withContext(Dispatchers.Main) {
                                state = state.copy(
                                    errorMessage = "EXIF write failed: ${e.message}",
                                )
                            }
                        }
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
        // Fallback mode: a fresh fix beats the manual position, it only
        // fills a hole. Claimed mode (manualLocationWins): the user said
        // "I am at the map position" through the accept gate, and that
        // overrides even a fresh fix.
        val manual = manualLocation.takeIf {
            manualLocationWins ||
                location == null || (ageMs != null && ageMs > FIX_FRESH_MS)
        }
        // The stamp bearing is the MAP's bearing state (Tauri semantics:
        // capture reads $bearingState) — car mode's gps-kalman + mount
        // offset included. Raw compass only as a fallback before the
        // screen pushes the first value.
        val stamp = stampBearing
        return if (manual != null) {
            SensorSnapshot(
                latitude = manual.latitude,
                longitude = manual.longitude,
                // No altitude and no claimed accuracy: this is where the
                // user says they are, not a measurement.
                bearingDeg = orientation?.magneticHeading,
                trueBearingDeg = stamp?.trueDeg ?: orientation?.trueHeading,
                bearingSource = stamp?.source ?: orientation?.source,
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
                trueBearingDeg = stamp?.trueDeg ?: orientation?.trueHeading,
                bearingSource = stamp?.source ?: orientation?.source,
                capturedAtMs = capturedAtMs,
                locationSource = location?.let { "gps" },
                locationAgeMs = ageMs,
            )
        }
    }

    fun release() {
        try {
            preciseLocation?.stopLocationUpdates()
            preciseLocation = null
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
        // Session over: dump-and-clear like the Tauri cleanup path does —
        // exports CSVs only when auto_export is on (its own IO scope, so
        // the scope.cancel() below cannot kill it).
        try {
            geoTracking.dumpAndClear()
        } catch (e: Exception) {
            Log.w(TAG, "geo tracking dump failed", e)
        }
        cameraProvider?.unbindAll()
        cameraProvider = null
        camera = null
        imageCapture = null
        previewUseCase = null
        previewBound = false
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

        // The original asks for LOCATION as soon as capture opens, before
        // its in-app camera gate — the geotag matters more than the shot
        // order suggests. One ask per entry; the banner below remains the
        // manual path after a denial.
        var locationAsked by remember { mutableStateOf(false) }
        LaunchedEffect(Unit) {
            if (!locationAsked && !location.granted && !location.permanentlyDenied) {
                locationAsked = true
                location.request()
            }
        }

        if (camera.granted) {
            Box(modifier = modifier.background(Color(0xFF111111))) {
                AndroidView(
                    factory = { c ->
                        PreviewView(c).apply {
                            // FILL (centre-crop): the capture pane is the
                            // camera stream, edge to edge, whatever the
                            // split ratio — FIT_CENTER letterboxed a small
                            // rectangle in black (phone-in-hand feedback).
                            // The captured photo keeps the full sensor
                            // frame; only the preview crops.
                            scaleType = PreviewView.ScaleType.FILL_CENTER
                            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                            // The native touch grammar, by hand (a
                            // GestureDetector would fight the pinch): tap =
                            // focus, long-press = AE/AF lock, second finger
                            // = pinch zoom (kills tap and long-press).
                            var downX = 0f
                            var downY = 0f
                            var scaling = false
                            var longPressFired = false
                            var longPress: Runnable? = null
                            val scaleDetector = android.view.ScaleGestureDetector(
                                c,
                                object :
                                    android.view.ScaleGestureDetector.SimpleOnScaleGestureListener() {
                                    override fun onScale(
                                        detector: android.view.ScaleGestureDetector,
                                    ): Boolean {
                                        setZoom(zoomRatio * detector.scaleFactor)
                                        return true
                                    }
                                },
                            )
                            setOnTouchListener { v, event ->
                                scaleDetector.onTouchEvent(event)
                                when (event.actionMasked) {
                                    android.view.MotionEvent.ACTION_DOWN -> {
                                        downX = event.x; downY = event.y
                                        scaling = false
                                        longPressFired = false
                                        longPress = Runnable {
                                            longPressFired = true
                                            lockFocusAt(this, downX, downY)
                                        }.also { v.postDelayed(it, 450L) }
                                        true
                                    }
                                    android.view.MotionEvent.ACTION_POINTER_DOWN -> {
                                        scaling = true
                                        longPress?.let { v.removeCallbacks(it) }
                                        true
                                    }
                                    android.view.MotionEvent.ACTION_MOVE -> {
                                        val slop = android.view.ViewConfiguration
                                            .get(v.context).scaledTouchSlop
                                        if (kotlin.math.hypot(
                                                event.x - downX,
                                                event.y - downY,
                                            ) > slop
                                        ) {
                                            longPress?.let { v.removeCallbacks(it) }
                                        }
                                        true
                                    }
                                    android.view.MotionEvent.ACTION_UP -> {
                                        longPress?.let { v.removeCallbacks(it) }
                                        val slop = android.view.ViewConfiguration
                                            .get(v.context).scaledTouchSlop
                                        if (!scaling && !longPressFired &&
                                            kotlin.math.hypot(
                                                event.x - downX,
                                                event.y - downY,
                                            ) <= slop
                                        ) {
                                            v.performClick()
                                            focusAt(this, event.x, event.y)
                                        }
                                        true
                                    }
                                    android.view.MotionEvent.ACTION_CANCEL -> {
                                        longPress?.let { v.removeCallbacks(it) }
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

                // Deep-eco freeze frame: while the preview use case is
                // unbound the TextureView is blank, so the last live frame
                // stands in (same centre-crop as FILL_CENTER).
                frozenFrame?.let { frame ->
                    androidx.compose.foundation.Image(
                        bitmap = frame.asImageBitmap(),
                        contentDescription = null,
                        contentScale = androidx.compose.ui.layout.ContentScale.Crop,
                        modifier = Modifier
                            .fillMaxSize()
                            .clipToBounds()
                            .testTag("eco-frozen-frame"),
                    )
                }

                // Native chips, top-centre over the video: the transient
                // zoom ratio while pinching, and the standing AE/AF lock.
                Column(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = 40.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    if (zoomChipVisible) {
                        Text(
                            text = "%.1f×".format(zoomRatio),
                            color = Color.White,
                            modifier = Modifier
                                .background(
                                    Color(0xB3000000),
                                    androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                                )
                                .padding(horizontal = 10.dp, vertical = 4.dp)
                                .testTag("zoom-chip"),
                        )
                    }
                    if (aeAfLocked) {
                        Text(
                            text = "AE/AF locked",
                            color = Color.White,
                            modifier = Modifier
                                .padding(top = 4.dp)
                                .background(
                                    Color(0xB3000000),
                                    androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
                                )
                                .padding(horizontal = 10.dp, vertical = 4.dp)
                                .testTag("af-lock-chip"),
                        )
                    }
                }

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
