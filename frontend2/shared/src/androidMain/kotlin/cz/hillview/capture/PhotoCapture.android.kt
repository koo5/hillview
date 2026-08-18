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
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
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
import com.google.common.util.concurrent.ListenableFuture
import cz.hillview.core.permissions.PermissionGatePane
import cz.hillview.core.permissions.rememberPermissionsState
import cz.hillview.plugin.DeviceOrientation
import cz.hillview.plugin.EnhancedSensorService
import cz.hillview.plugin.MyDeviceOrientationSensor
import cz.hillview.plugin.OrientationSensorData
import cz.hillview.settings.StorageMode
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import java.io.IOException
import kotlin.coroutines.resume

private const val TAG = "PhotoCapture"

// The metering window prepareExposure opens between interval shots. The
// frame minimum is there so a single mid-convergence frame cannot be
// mistaken for a reading; the timeouts are ceilings, not waits — a
// converged AE returns immediately, and everything degrades to "use the
// last reading" rather than to a stuck run.
private const val REMETER_MIN_FRAMES = 3
private const val REMETER_STREAM_TIMEOUT_MS = 2_000L
private const val REMETER_SETTLE_TIMEOUT_MS = 900L
private const val REMETER_APPLY_TIMEOUT_MS = 600L

// How often a moving scene is allowed to re-spend the rule's budget.
// Measuring is free (it rides frames we already produce); APPLYING is a
// camera round trip, so it is rate-limited. ~3 Hz tracks a drive through
// shade and sun without churning the request queue.
private const val SCENE_APPLY_INTERVAL_MS = 300L

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
    // Subscriptions to the engine's streams (this pane owns no hardware).
    private var locationJob: Job? = null
    private var orientationJob: Job? = null

    // Geo tracking — the same tables and CSV dumps the Tauri app writes
    // (GeoTrackingManager, shared-kt): the raw feeds, fused fixes and
    // orientation samples.
    //
    // There used to be a third, synthetic "effective" stream here, sampling
    // snapshotSensors() once a second to record what a shutter press WOULD
    // have stamped. It existed only because the tables could not say which
    // source the app was actually using, so it logged the outcome instead —
    // the same move as the old "-background" name mangling. Every row now
    // carries its own election, and the map position is written as a real
    // row when it is elected, so the outcome is reconstructable and the
    // synthetic stream had nothing left to carry. It was also a derived row
    // sitting among observations, and it overloaded locations.bearing (the
    // GNSS course) with the composed stamp heading.
    private val geoTracking by lazy { cz.hillview.plugin.GeoTrackingManager.get(context) }


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
     * results while AE runs. This is the metering an exposure rule scales
     * from — see [planExposure]. Not updated while a rule is applied (AE
     * is off then, so the results would only echo our own values back),
     * which is precisely why [prepareExposure] exists.
     */
    @Volatile private var meteredExposureNs: Long? = null
    @Volatile private var meteredIso: Int? = null

    // Continuous metering. The scene is measured from analysis frames at
    // whatever exposure we are already using, so a rule's plan can be
    // recomputed at any moment without ever giving the camera back to AE —
    // no preview pump, no wait before a manual shot, and no per-shot
    // metering window in interval runs.
    private val sceneMeter = SceneMeter()
    private var analysisUseCase: ImageAnalysis? = null
    private val analysisExecutor = java.util.concurrent.Executors.newSingleThreadExecutor()
    @Volatile private var continuousMetering = true
    @Volatile private var lastSceneApplyMs = 0L

    /**
     * One analysis frame: measure, then re-spend the rule's budget if the
     * scene has actually moved. Rate-limited because re-applying request
     * options is a camera round trip, not arithmetic.
     */
    private fun onAnalysisFrame(image: androidx.camera.core.ImageProxy) {
        try {
            val rule = exposureRule
            // The exposure these pixels were taken at — ours when a rule is
            // in force, AE's otherwise.
            val exposure = meteredExposureNs ?: state.plan?.exposureNs
            val iso = meteredIso ?: state.plan?.iso
            if (exposure != null && iso != null) {
                val plane = image.planes[0]
                sceneMeter.onFrame(
                    meanLumaSubsampled(
                        plane.buffer, image.width, image.height, plane.rowStride,
                    ),
                    exposure, iso,
                )
            }
            if (rule == null || !continuousMetering) return
            val now = SystemClock.elapsedRealtime()
            if (now - lastSceneApplyMs < SCENE_APPLY_INTERVAL_MS) return
            lastSceneApplyMs = now
            scope.launch { applyRequestOptions() }
        } catch (e: Exception) {
            Log.w(TAG, "analysis frame failed", e)
        } finally {
            image.close()
        }
    }
    @Volatile private var lastFrameLog = 0L

    /**
     * Whether the request we last applied leaves AE running — the harvest
     * gate. Gating on "no rule is set" instead would shut the harvest out
     * of the deliberate metering window [prepareExposure] opens.
     */
    @Volatile private var aeIsOn = true

    /** Set while [prepareExposure] is deliberately holding AE on. */
    @Volatile private var meteringWindow = false

    /**
     * A rule is in force but has never had a reading to scale from, so AE
     * still owns the camera; the harvest applies the rule as soon as it
     * has one. This replaced a fabricated "plausible daylight" starting
     * point that was ~6 stops off and, in the capture-only eco band (no
     * preview, hence no AE frames, ever), was not a fallback but the only
     * path.
     */
    @Volatile private var awaitingMetering = false

    /** Monotonic count of harvested frames — how the metering window waits. */
    @Volatile private var meterFrames = 0
    @Volatile private var meterConverged = false

    @Volatile private var lastLocation: Location? = null
    @Volatile override var manualLocation: ManualLocation? = null

    // Mirrors MapSession.manualPositionElected, pushed in by the screen. This
    // object only reports what a capture would stamp; publishing the election
    // to the tracking tables belongs to the map pane, which is always composed
    // and therefore can answer for it whether or not capture is open.
    @Volatile override var manualLocationElected: Boolean = false

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
        // Declination (magnetic → true) is fed inside the engine now, once
        // per fix, for whichever panes are observing.
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
    // This pane OBSERVES the one owner; it does not open sensors itself, and
    // it no longer writes tracking rows — the engine already wrote them, at
    // full rate, for every consumer. See docs/frontend2-geo-engine-design.md.
    private val engine by lazy { cz.hillview.geo.GeoEngine.get(context) }

    private fun observeOrientation() = scope.launch {
        engine.orientation.collect { data ->
            data ?: return@collect
            lastOrientation = data
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
    }

    // The PURE DEVICE pose (accelerometer tilt), which is emphatically not
    // the screen's orientation. CameraX's default targetRotation is the
    // DISPLAY rotation sampled once, when ImageCapture was built — and this
    // activity handles `orientation` config changes itself and never
    // rebinds, so that default never moves again; worse, display rotation
    // stops tracking the device entirely as soon as auto-rotate is off,
    // which is the normal state for someone out shooting. Result before
    // this: every JPEG claimed the pose the pane happened to open in.
    //
    // shared-kt's sensor is the right source (the Tauri app drives its
    // `device-orientation` event from this same class) and it filters
    // FLAT_UP/FLAT_DOWN, so pointing at the ground or the sky keeps the last
    // real pose instead of snapping to portrait.
    @Volatile private var deviceOrientation: DeviceOrientation = DeviceOrientation.PORTRAIT

    private val orientationSensor = MyDeviceOrientationSensor(context) { pose ->
        deviceOrientation = pose
        // Settable on an already-bound use case — no rebind, no preview blink.
        val rotation = DeviceOrientation.toSurfaceRotation(pose)
        imageCapture?.targetRotation = rotation
        Log.d(TAG, "device pose $pose (${DeviceOrientation.toDegrees(pose)}°) → targetRotation $rotation")
    }

    // bindToLifecycle already unbinds the camera on STOP; the accelerometer
    // has no such contract, so it gets suspended alongside — the same
    // onPause/onResume pairing the Tauri plugin applies to this class.
    private val orientationLifecycle = object : androidx.lifecycle.DefaultLifecycleObserver {
        override fun onStart(owner: LifecycleOwner) = orientationSensor.setSuspended(false)
        override fun onStop(owner: LifecycleOwner) = orientationSensor.setSuspended(true)
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
        // Seed from the device pose rather than inheriting the builder's
        // display-rotation default; the sensor callback keeps it live.
        capture.targetRotation = DeviceOrientation.toSurfaceRotation(deviceOrientation)
        imageCapture = capture

        val preview = buildPreviewUseCase()
        previewUseCase = preview

        // Continuous metering (see SceneMeter): a small analysis stream lets
        // us measure the scene from frames we are already producing, instead
        // of handing the camera back to auto-exposure for a window before
        // every shot. Cheap — a few thousand subsampled luma samples.
        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setResolutionSelector(
                ResolutionSelector.Builder()
                    .setResolutionStrategy(
                        ResolutionStrategy(
                            android.util.Size(640, 480),
                            ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER,
                        ),
                    )
                    .build(),
            )
            .build()
            .also { it.setAnalyzer(analysisExecutor, ::onAnalysisFrame) }
        analysisUseCase = analysis

        provider.unbindAll()
        // Three use cases is a guaranteed combination on LIMITED and above
        // but not on LEGACY hardware, so a refusal degrades to the
        // two-use-case binding and the AE-window path rather than failing.
        val cam = try {
            provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                UseCaseGroup.Builder()
                    .addUseCase(preview).addUseCase(capture).addUseCase(analysis).build(),
            )
        } catch (e: Exception) {
            Log.w(TAG, "no analysis stream on this camera; metering falls back to AE windows", e)
            analysisUseCase = null
            continuousMetering = false
            provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                UseCaseGroup.Builder().addUseCase(preview).addUseCase(capture).build(),
            )
        }
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
        if (exposureRule != null || ecoPreviewFps != null) applyRequestOptions()
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
                    // Ground truth for the rule (the emulator's JPEG EXIF
                    // is canned, so this log is the only honest witness
                    // there).
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastFrameLog > 2_000) {
                        lastFrameLog = now
                        Log.d(TAG, "frame exposureNs=$exp iso=$iso rule=$exposureRule aeOn=$aeIsOn")
                    }
                    if (!aeIsOn) return
                    exp?.let { meteredExposureNs = it }
                    iso?.let { meteredIso = it }
                    // Seed the continuous meter from AE's own answer, so the
                    // first frame after a rule is chosen is already right
                    // rather than a step away from it.
                    if (exp != null && iso != null) sceneMeter.seedFromAutoExposure(exp, iso)
                    if (exp == null || iso == null) return
                    meterFrames++
                    val aeState = result.get(CaptureResult.CONTROL_AE_STATE)
                    // A HAL that reports no AE state at all leaves this
                    // false and the window falls back to its timeout.
                    meterConverged = aeState == CameraMetadata.CONTROL_AE_STATE_CONVERGED ||
                        aeState == CameraMetadata.CONTROL_AE_STATE_FLASH_REQUIRED ||
                        aeState == CameraMetadata.CONTROL_AE_STATE_LOCKED
                    if (awaitingMetering) {
                        awaitingMetering = false
                        // State and the camera control are the main
                        // thread's business; this is a camera thread.
                        scope.launch { applyRequestOptions() }
                    }
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

    override var exposureRule: ExposureRule? = null
        set(value) {
            Log.d(TAG, "exposureRule <- $value")
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
    // throughout, so the shutter never waits. The caveat this used to
    // carry — exposure-rule ISO scales from preview-frame metering, which
    // goes stale while frozen — is now [prepareExposure]'s business: it
    // borrows the preview back for its window and returns it.
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
    private fun applyRequestOptions(): ListenableFuture<Void?>? {
        val cam = camera ?: return null
        val builder = CaptureRequestOptions.Builder()
        var applied = "none"

        val rule = exposureRule?.takeIf { state.manualShutterSupported }
        // The scene estimate is CONTINUOUS (SceneMeter, fed by the analysis
        // stream), so a rule always has a current reading to spend and never
        // has to borrow the camera back to get one. The frozen AE harvest is
        // the fallback for hardware that refused the analysis stream.
        val sceneReading = sceneMeter.meteredPair()
        val metered = sceneReading?.first ?: meteredExposureNs
        val meteredGain = sceneReading?.second ?: meteredIso
        // A rule needs a reading to spend; without one AE keeps the camera
        // (and the harvest hands it back the moment a frame lands).
        awaitingMetering = rule != null && !meteringWindow &&
            (metered == null || meteredGain == null)
        if (rule != null && !meteringWindow && metered != null && meteredGain != null) {
            val plan = planExposure(rule, metered, meteredGain, sensorCaps())
            builder
                .setCaptureRequestOption(
                    CaptureRequest.CONTROL_AE_MODE,
                    CameraMetadata.CONTROL_AE_MODE_OFF,
                )
                .setCaptureRequestOption(CaptureRequest.SENSOR_EXPOSURE_TIME, plan.exposureNs)
                .setCaptureRequestOption(CaptureRequest.SENSOR_SENSITIVITY, plan.iso)
            applied = "${rule.mode}@${rule.targetNs} ${rule.evBias}EV metered=${metered}ns/" +
                "$meteredGain -> ${plan.exposureNs}ns iso=${plan.iso} ${plan.outcome}"
            aeIsOn = false
            state = state.copy(exposureRule = rule, plan = plan)
        } else {
            aeIsOn = true
            state = state.copy(exposureRule = rule, plan = null)
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

        val future = Camera2CameraControl.from(cam.cameraControl).setCaptureRequestOptions(
            builder.build(),
        )
        future.addListener(
            { Log.d(TAG, "request options applied: $applied") },
            ContextCompat.getMainExecutor(context),
        )
        return future
    }

    /** The walls a plan clamps to; the fallbacks are a mid-range phone. */
    private fun sensorCaps(): SensorExposureCaps = SensorExposureCaps(
        minExposureNs = exposureRange?.lower ?: 100_000L,
        maxExposureNs = exposureRange?.upper ?: 100_000_000L,
        minIso = isoRange?.lower ?: 50,
        maxIso = isoRange?.upper ?: 3200,
    )

    /**
     * Give AE the camera back for a moment, take its reading, and put the
     * rule back on top of it — see PhotoCapture.prepareExposure for why
     * this has to exist at all.
     *
     * Everything here runs on the main dispatcher, as does the eco duty
     * engine it borrows the preview from, so the two interleave at
     * suspension points rather than racing; setPreviewBound is a no-op
     * when the beat already has what we want.
     */
    override suspend fun prepareExposure() {
        if (exposureRule == null || !state.manualShutterSupported) return
        // Continuous metering makes this free: the scene estimate is already
        // current, so there is nothing to wait for. That deletes a metering
        // window from before EVERY interval shot — and it is why a manual
        // tap needs no window either. Only hardware that refused the
        // analysis stream still pays the AE handover below.
        if (continuousMetering && sceneMeter.meteredPair() != null) {
            applyRequestOptions()
            return
        }
        // Nothing to meter with, and every wait below would run its full
        // timeout before finding that out — a dead camera must not slow
        // the run's cadence down on top of taking no photos.
        if (camera == null || !cameraBound) return
        val startedAt = SystemClock.elapsedRealtime()
        val hadPreview = previewBound
        meterConverged = false
        meteringWindow = true
        try {
            applyRequestOptions()
            // AE only runs while frames flow, and in the eco bands the
            // preview may be unbound between beats — borrow it.
            if (!hadPreview) setPreviewBound(true)
            waitForPreviewStreaming(REMETER_STREAM_TIMEOUT_MS)
            awaitMeteredFrames(REMETER_MIN_FRAMES, REMETER_SETTLE_TIMEOUT_MS)
            meteringWindow = false
            // Wait for the rule to be genuinely back in force: a still
            // capture submitted before the manual request lands would be
            // exposed by whatever AE was doing mid-window.
            awaitAppliedRequestOptions(REMETER_APPLY_TIMEOUT_MS)
        } finally {
            // Cancellation (run stopped, pane left) must not strand the
            // window: the rule has to go back in force — fire-and-forget is
            // enough, nobody is about to shoot — and a borrowed preview has
            // to be returned, or the capture-only eco band is left streaming,
            // the exact power draw it exists to avoid. NonCancellable because
            // on that path the scope is already dead and a plain withContext
            // would refuse to enter.
            withContext(NonCancellable) {
                if (meteringWindow) {
                    meteringWindow = false
                    applyRequestOptions()
                }
                if (!hadPreview) setPreviewBound(false)
            }
        }
        CaptureStatsLog.record(
            "re-meter",
            SystemClock.elapsedRealtime() - startedAt,
            System.currentTimeMillis(),
        )
    }

    /** Resolves on a converged reading, or when the window runs out. */
    private suspend fun awaitMeteredFrames(minFrames: Int, timeoutMs: Long) {
        val start = meterFrames
        withTimeoutOrNull(timeoutMs) {
            while (meterFrames - start < minFrames || !meterConverged) delay(20)
        }
    }

    private suspend fun awaitAppliedRequestOptions(timeoutMs: Long) {
        val future = applyRequestOptions() ?: return
        withTimeoutOrNull(timeoutMs) {
            suspendCancellableCoroutine { cont ->
                future.addListener(
                    { if (cont.isActive) cont.resume(Unit) },
                    ContextCompat.getMainExecutor(context),
                )
            }
        }
    }

    // ---- Video modality -------------------------------------------------
    // A recording binds Preview + VideoCapture INSTEAD of Preview +
    // ImageCapture, rather than binding all three: three simultaneous use
    // cases is a device-dependent capability, and video is a mode here, not
    // something running alongside stills. Stopping rebinds the stills path.
    private var videoCapture: androidx.camera.video.VideoCapture<androidx.camera.video.Recorder>? = null
    private var activeRecording: androidx.camera.video.Recording? = null
    private var frameLog: VideoFrameLog? = null
    private var recordingFile: File? = null

    @androidx.annotation.OptIn(androidx.camera.camera2.interop.ExperimentalCamera2Interop::class)
    override fun startVideo() {
        if (activeRecording != null) return
        val provider = cameraProvider ?: return
        val settings = uploadSettings.settings.value
        val dir = when (settings.storage) {
            StorageMode.PrivateFolder -> PhotoStorage.privateDir(context, settings.hideFromGallery)
            else -> PhotoStorage.publicDir(settings.hideFromGallery)
        }
        if (!dir.exists() && !dir.mkdirs()) {
            state = state.copy(errorMessage = "cannot create ${dir.name}")
            return
        }
        val startedAt = System.currentTimeMillis()
        val file = File(dir, "hillview_video_$startedAt.mp4")

        val log = VideoFrameLog(
            timestampSource = camera?.let {
                Camera2CameraInfo.from(it.cameraInfo)
                    .getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE)
            },
        )
        val recorder = androidx.camera.video.Recorder.Builder()
            .setQualitySelector(
                androidx.camera.video.QualitySelector.from(
                    androidx.camera.video.Quality.HIGHEST,
                    androidx.camera.video.FallbackStrategy
                        .lowerQualityOrHigherThan(androidx.camera.video.Quality.SD),
                ),
            )
            .build()
        val builder = androidx.camera.video.VideoCapture.Builder(recorder)
        // The per-frame timestamps, straight off the capture session — no
        // extra stream, and the same value every output buffer of that frame
        // carries. See VideoFrameLog for why the mp4 cannot hold them.
        Camera2Interop.Extender(builder).setSessionCaptureCallback(
            object : android.hardware.camera2.CameraCaptureSession.CaptureCallback() {
                override fun onCaptureCompleted(
                    session: android.hardware.camera2.CameraCaptureSession,
                    request: android.hardware.camera2.CaptureRequest,
                    result: android.hardware.camera2.TotalCaptureResult,
                ) {
                    log.onFrame(result)
                }
            },
        )
        val useCase = builder.build()

        try {
            provider.unbindAll()
            val preview = buildPreviewUseCase()
            previewUseCase = preview
            val cam = provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_BACK_CAMERA,
                UseCaseGroup.Builder().addUseCase(preview).addUseCase(useCase).build(),
            )
            camera = cam
            previewBound = true
            videoCapture = useCase
            applyZoomAfterBind(cam)
            // The exposure rule is a repeating-request option, so it should
            // reach video too — the sidecar's per-frame exposure column is
            // what actually answers that.
            applyRequestOptions()
        } catch (e: Exception) {
            Log.e(TAG, "could not bind video", e)
            state = state.copy(errorMessage = "video unavailable: ${e.message}")
            rebindStills()
            return
        }

        val pending = recorder
            .prepareRecording(context, androidx.camera.video.FileOutputOptions.Builder(file).build())
        activeRecording = pending.start(ContextCompat.getMainExecutor(context)) { event ->
            when (event) {
                is androidx.camera.video.VideoRecordEvent.Start -> {
                    log.onRecordingStarted()
                    state = state.copy(recording = true, recordingStartedAtMs = startedAt)
                    Log.i(TAG, "recording -> ${file.absolutePath}")
                }
                is androidx.camera.video.VideoRecordEvent.Finalize -> onRecordingFinalized(event, file, log)
                else -> Unit
            }
        }
        frameLog = log
        recordingFile = file
    }

    private fun onRecordingFinalized(
        event: androidx.camera.video.VideoRecordEvent.Finalize,
        file: File,
        log: VideoFrameLog,
    ) {
        activeRecording = null
        val failed = event.hasError()
        if (failed) Log.e(TAG, "recording error ${event.error}", event.cause)
        // The sidecar is written even for a failed stop: whatever bytes the
        // file holds are still pairable, and the frame list is the only copy
        // of those timestamps.
        val sidecar = log.write(
            file,
            // Always writable, and the same shape as GeoTrackingDumps/ —
            // the other place this app parks data destined for the pics
            // pipeline.
            fallbackDir = File(context.getExternalFilesDir(null), "VideoSidecars"),
        )
        Log.i(
            TAG,
            "recording finalized: ${file.length()} bytes, ${log.frameCount} frames, " +
                log.exposureSummary(),
        )
        cz.hillview.plugin.EventLog.record(
            "video",
            "${file.name}: ${file.length() / 1024}KB, ${log.frameCount} frames, " +
                log.exposureSummary(),
        )
        if (!hideFromGalleryPref()) PhotoStorage.indexInGallery(context, file)
        state = state.copy(
            recording = false,
            recordingStartedAtMs = null,
            lastVideoPath = file.absolutePath,
            errorMessage = if (failed) "recording failed (${event.error})" else state.errorMessage,
        )
        CaptureStatsLog.increment(
            if (failed) "video failed" else "video recorded",
            System.currentTimeMillis(),
        )
        if (sidecar == null) Log.w(TAG, "no sidecar for ${file.name} — frames unpairable")
        frameLog = null
        recordingFile = null
        rebindStills()
    }

    private fun hideFromGalleryPref(): Boolean = uploadSettings.settings.value.hideFromGallery

    /**
     * Put the stills use cases back after a recording. ensureCameraBound is
     * guarded on [cameraBound], so the flag has to be dropped for it to do
     * anything — video unbound everything it was tracking.
     */
    private fun rebindStills() {
        videoCapture = null
        cameraBound = false
        previewBound = false
        scope.launch {
            try {
                ensureCameraBound()
            } catch (e: Exception) {
                Log.e(TAG, "could not rebind stills after video", e)
                state = state.copy(errorMessage = "camera restart failed: ${e.message}")
            }
        }
    }

    override fun stopVideo() {
        activeRecording?.stop()
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
            // Fused delivers its current best estimate immediately and
            // precise fixes on a 1 s cadence; freshness is judged at
            // capture time (FIX_FRESH_MS), so a stale seed can never
            // geotag a photo. The stream is the ENGINE's — it publishes the
            // platform Location itself, so elapsedRealtimeNanos (and with it
            // the fix age this stamps) survives the hop.
            locationJob = scope.launch {
                engine.location.collect { fix -> fix?.let { onLocation(it) } }
            }
            gpsStarted = true
        }
        if (!orientationStarted) {
            orientationJob = observeOrientation()
            // Separate listener from the heading engine's own, on purpose:
            // that one accepts FLAT_UP from ORIENTATION_UNKNOWN, which would
            // snap the EXIF orientation to portrait every time the phone
            // tilts flat.
            orientationSensor.setRunning(true)
            lifecycleOwner.lifecycle.addObserver(orientationLifecycle)
            orientationStarted = true
        }
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
        // Tally the rule's outcome PER SHOT, not per application: which
        // escape hatches a mode actually needed over a real drive is the
        // only way to judge whether it is the right mode.
        state.plan?.let {
            CaptureStatsLog.increment("exposure ${it.outcome.name.lowercase()}", capturedAtMs)
        }
        // Same idiom as the pose below: the rule/plan pair as it stands at
        // the shutter, for the UserComment provenance. Null when AE owns the
        // shot (auto, or a rule still awaiting its first metering).
        val exposureAtShutter = state.plan?.let { p ->
            exposureRule?.let { r ->
                ExposureStamp(r, p, meteredExposureNs, meteredIso)
            }
        }
        val filename = "hillview_photo_$capturedAtMs.jpg"
        // The pose at the shutter, not at whenever the last change event
        // fired: takePicture() reads targetRotation, so this is the last
        // moment it can still matter. Same value goes into the snapshot, so
        // what the tag claims and what the record says cannot drift.
        val poseAtShutter = deviceOrientation
        capture.targetRotation = DeviceOrientation.toSurfaceRotation(poseAtShutter)
        val snapshot = snapshotSensors(capturedAtMs, poseAtShutter, exposureAtShutter)
        val settings = uploadSettings.settings.value
        takePictureWithFallback(
            capture = capture,
            chain = PhotoStorage.chain(settings.storage),
            filename = filename,
            hideFromGallery = settings.hideFromGallery,
            writeExif = settings.writeExif,
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
        writeExif: Boolean,
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
                capture, chain.drop(1), filename, hideFromGallery, writeExif, snapshot, watchdog,
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
                            // The fork the fast-write default is about. OFF
                            // (default): the CameraX save IS the final file —
                            // no whole-file EXIF copy per shot; the stamp
                            // rides the photos table into the upload metadata,
                            // which the server prefers over file EXIF anyway.
                            // ON (opt-in, "use the files outside hillview"):
                            // the full EXIF pass, 4-25 MB copied per shot on
                            // a real sensor.
                            if (writeExif) {
                                if (file != null) {
                                    PhotoExifWriter.write(file, snapshot)
                                } else {
                                    PhotoExifWriter.write(context, uri!!, snapshot)
                                }
                            }
                            // After any EXIF rewrite, so the indexed entry
                            // has the final bytes.
                            if (file != null && !hideFromGallery) {
                                PhotoStorage.indexInGallery(context, file)
                            }
                            // lastPhoto ONLY after the final bytes exist:
                            // the upload enqueue hashes the file it triggers
                            // on — publishing earlier would hash pre-EXIF
                            // bytes. (In the fast path the save already wrote
                            // the final bytes.)
                            kotlinx.coroutines.withContext(Dispatchers.Main) {
                                state = state.copy(
                                    lastPhoto = CapturedPhoto(locator, filename, snapshot),
                                )
                            }
                            CaptureStatsLog.record(
                                if (writeExif) "finalize(exif+index)" else "finalize(fast)",
                                SystemClock.elapsedRealtime() - finalizeStart,
                                System.currentTimeMillis(),
                            )
                            Log.i(
                                TAG,
                                "captured $filename via ${mode.key} -> $locator " +
                                    "(device pose ${snapshot.deviceRotationDeg}°)",
                            )
                            cz.hillview.plugin.EventLog.record(
                                "capture",
                                "$filename (${mode.key}, " +
                                    (snapshot.locationSource ?: "no position") + ", " +
                                    (snapshot.exposure?.let {
                                        "${formatShutter(it.plan.exposureNs)} iso${it.plan.iso}"
                                    } ?: "auto exposure") + ")",
                            )
                        } catch (e: Exception) {
                            Log.e(TAG, "post-save handling failed", e)
                            kotlinx.coroutines.withContext(Dispatchers.Main) {
                                state = state.copy(
                                    errorMessage = "photo finalize failed: ${e.message}",
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
                            capture, rest, filename, hideFromGallery, writeExif, snapshot, watchdog,
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

    private fun snapshotSensors(
        capturedAtMs: Long,
        pose: DeviceOrientation = deviceOrientation,
        exposure: ExposureStamp? = null,
    ): SensorSnapshot {
        val location = lastLocation
        val orientation = lastOrientation
        val ageMs = location?.let {
            (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000
        }
        // No arbitration here, deliberately. The map position is used exactly
        // when the user elected it — through the pill's accepted claim or the
        // no-fix escape hatch — and never because a fix merely went stale. A
        // silent hand-over would make the election recorded on every row a
        // lie, and re-judging the choice later is the whole point of recording
        // it. Which stream is primary is decided in the UI, where it can be
        // seen and withdrawn; this function only reports the decision.
        val manual = manualLocation.takeIf { manualLocationElected }
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
                deviceRotationDeg = DeviceOrientation.toDegrees(pose),
                exposure = exposure,
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
                deviceRotationDeg = DeviceOrientation.toDegrees(pose),
                exposure = exposure,
            )
        }
    }

    fun release() {
        // Unsubscribe only — the engine's lifetime belongs to the ACTIVITY
        // (MainScreen hands it a GeoConfig), not to this pane.
        locationJob?.cancel()
        locationJob = null
        orientationJob?.cancel()
        orientationJob = null
        gpsStarted = false
        orientationStarted = false
        analysisUseCase?.clearAnalyzer()
        analysisUseCase = null
        analysisExecutor.shutdown()
        orientationSensor.setRunning(false)
        lifecycleOwner.lifecycle.removeObserver(orientationLifecycle)
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
                            // FIT (whole frame, letterboxed): the pane shows
                            // everything the sensor sees, scaled down to
                            // fit rather than cropped to fill.
                            //
                            // This REVERSES the round-4 choice of
                            // FILL_CENTER (user, 2026-08-09: "the capture
                            // panel should always contain the whole of the
                            // video stream, not try to stretch its edges
                            // beyond the borders"). The earlier complaint
                            // was about the letterboxed rectangle being
                            // small, which is a split-ratio problem, not a
                            // scaling one — and cropping the preview means
                            // framing a shot by a picture that is not the
                            // picture you get, since the captured photo
                            // keeps the full frame. Do not "fix" this back.
                            scaleType = PreviewView.ScaleType.FIT_CENTER
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
                // stands in — scaled the same way the live preview is, or
                // the picture would jump between beats.
                frozenFrame?.let { frame ->
                    androidx.compose.foundation.Image(
                        bitmap = frame.asImageBitmap(),
                        contentDescription = null,
                        contentScale = androidx.compose.ui.layout.ContentScale.Fit,
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
