package cz.hillview.clockvideo

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Matrix
import android.graphics.PorterDuff
import android.hardware.camera2.CameraCharacteristics
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.Log
import android.util.Rational
import android.view.Surface
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.Camera
import androidx.camera.core.CameraEffect
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.core.UseCaseGroup
import androidx.camera.core.ViewPort
import androidx.camera.effects.Frame
import androidx.camera.effects.OverlayEffect
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import java.io.File
import kotlin.coroutines.resume
import kotlin.math.roundToLong

private const val TAG = "hv-ClockVideoRecorder"

@Composable
actual fun rememberClockVideoRecorder(): ClockVideoRecorder {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val recorder = remember(lifecycleOwner) {
        AndroidClockVideoRecorder(context.applicationContext, lifecycleOwner)
    }
    DisposableEffect(recorder) {
        onDispose { recorder.release() }
    }
    return recorder
}

/**
 * Native reimplementation of the Tauri app's clock-video recorder
 * (ClockVideoRecorder.svelte + ClockVideoWriter.kt).
 *
 * CameraX records the rear camera to an mp4 while an OverlayEffect burns a
 * phone-time QR into every VIDEO_CAPTURE frame. Unlike the WebView version,
 * stamps come from the frame's *sensor* timestamp mapped to the epoch —
 * anchored to System.currentTimeMillis() per frame so NTP steps during the
 * session can't skew them — which removes the camera-pipeline latency bias
 * the old sidecars had to confess to (draw-time stamping remains as the
 * fallback when the sensor timebase is unrecognizable).
 *
 * Output lands in GeoTrackingDumps/ next to the geo CSV dumps, same as the
 * old app, so whatever pulls the CSVs picks the videos up too.
 */
private class AndroidClockVideoRecorder(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
) : ClockVideoRecorder {

    override var state by mutableStateOf(ClockVideoState())
        private set

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    var previewView: PreviewView? = null

    private var cameraProvider: ProcessCameraProvider? = null
    private var overlayEffect: OverlayEffect? = null
    private var handlerThread: HandlerThread? = null
    private var videoRecorder: Recorder? = null
    private var cameraBound = false
    private var recording: Recording? = null
    private var tickerJob: Job? = null

    // Frames flow through the overlay whenever the camera is bound (the pane
    // shows live preview before and between recordings); stats only count
    // frames of an active recording.
    @Volatile private var recordingActive = false

    private var outputFile: File? = null
    private var startedAtMs = 0L
    private var sensorTimestampSource: String? = null

    // Written on the overlay handler thread, read on main by the ticker and at
    // finalize time.
    @Volatile private var framesDrawn = 0
    @Volatile private var sensorBoottimeFrames = 0
    @Volatile private var sensorUptimeFrames = 0
    @Volatile private var drawTimeFrames = 0
    @Volatile private var latencySumMs = 0.0
    @Volatile private var latencyMaxMs = 0.0
    @Volatile private var panel: QrTimePanel? = null
    @Volatile private var videoWidth = 0
    @Volatile private var videoHeight = 0
    @Volatile private var rotationDegrees = 0

    private companion object {
        // All CameraX video qualities are 16:9-family, so the portrait video
        // is 9:16; used for the shared viewport and the pre-recording ghost.
        val PORTRAIT_ASPECT = Rational(9, 16)

        // Ghost estimate before the first real frame fixes the exact rect:
        // the panel geometry normalized to assumed 1080x1920. Resolution
        // changes shift this by under a percent (module rounding only).
        val ESTIMATED_PANEL = QrTimePanel(1080, 1920).rect.let {
            PanelRectNorm(it.left / 1080f, it.top / 1920f, it.width() / 1080f, it.height() / 1920f)
        }
    }

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    override fun start() {
        if (state.phase == ClockVideoPhase.Starting || state.phase == ClockVideoPhase.Recording) return
        scope.launch { doStart() }
    }

    /**
     * Binds the whole session (preview + video capture + overlay effect) once;
     * called when the pane opens so the user can aim before recording, and
     * idempotently again from start(). Recording start/stop doesn't rebind —
     * the camera stays warm between takes.
     */
    private suspend fun ensureCameraBound() {
        if (cameraBound) return
        if (!hasPermission()) throw IllegalStateException("Camera permission not granted")

        val provider = awaitCameraProvider()
        cameraProvider = provider

        val thread = HandlerThread("clockvideo-overlay").also { it.start() }
        handlerThread = thread
        val effect = OverlayEffect(CameraEffect.VIDEO_CAPTURE, 0, Handler(thread.looper)) { t ->
            Log.e(TAG, "overlay effect error", t)
        }
        effect.setOnDrawListener { frame -> onDrawFrame(frame) }
        overlayEffect = effect

        val recorder = Recorder.Builder()
            .setQualitySelector(
                QualitySelector.from(
                    Quality.FHD,
                    FallbackStrategy.higherQualityOrLowerThan(Quality.FHD),
                )
            )
            .build()
        videoRecorder = recorder
        val videoCapture = VideoCapture.withOutput(recorder)

        val preview = Preview.Builder().build()
        previewView?.let { preview.surfaceProvider = it.surfaceProvider }

        // Shared viewport: the preview shows exactly the recorded FOV
        // instead of each use case cropping the sensor independently.
        val group = UseCaseGroup.Builder()
            .setViewPort(ViewPort.Builder(PORTRAIT_ASPECT, Surface.ROTATION_0).build())
            .addUseCase(preview)
            .addUseCase(videoCapture)
            .addEffect(effect)
            .build()

        provider.unbindAll()
        val camera = provider.bindToLifecycle(
            lifecycleOwner,
            CameraSelector.DEFAULT_BACK_CAMERA,
            group,
        )
        sensorTimestampSource = readTimestampSource(camera)
        cameraBound = true
    }

    fun openCamera() {
        scope.launch {
            try {
                ensureCameraBound()
            } catch (e: Exception) {
                Log.e(TAG, "🎬 failed to open camera", e)
                state = state.copy(
                    phase = ClockVideoPhase.Error,
                    errorMessage = "camera failed to open: ${e.message ?: e}",
                )
            }
        }
    }

    private suspend fun doStart() {
        state = ClockVideoState(
            phase = ClockVideoPhase.Starting,
            panelRectNorm = state.panelRectNorm ?: ESTIMATED_PANEL,
        )
        framesDrawn = 0
        sensorBoottimeFrames = 0
        sensorUptimeFrames = 0
        drawTimeFrames = 0
        latencySumMs = 0.0
        latencyMaxMs = 0.0

        try {
            ensureCameraBound()

            startedAtMs = System.currentTimeMillis()
            val dir = File(context.getExternalFilesDir(null), "GeoTrackingDumps")
            dir.mkdirs()
            val file = File(dir, "hillview_clockvideo_$startedAtMs.mp4")
            outputFile = file
            Log.i(TAG, "🎬 Recording clock video to ${file.absolutePath}")

            recordingActive = true
            recording = videoRecorder!!
                .prepareRecording(context, FileOutputOptions.Builder(file).build())
                .start(ContextCompat.getMainExecutor(context)) { event -> onRecordEvent(event) }
        } catch (e: Exception) {
            Log.e(TAG, "🎬 failed to start clock video recording", e)
            recordingActive = false
            state = ClockVideoState(phase = ClockVideoPhase.Error, errorMessage = e.message ?: e.toString())
            cleanupCamera()
        }
    }

    override fun stop() {
        if (state.phase != ClockVideoPhase.Recording) return
        state = state.copy(phase = ClockVideoPhase.Saving)
        recording?.stop()
    }

    private fun onRecordEvent(event: VideoRecordEvent) {
        when (event) {
            is VideoRecordEvent.Start -> {
                state = state.copy(phase = ClockVideoPhase.Recording)
                startTicker()
            }
            is VideoRecordEvent.Finalize -> onFinalize(event)
            else -> {}
        }
    }

    private fun startTicker() {
        tickerJob?.cancel()
        tickerJob = scope.launch {
            while (isActive && state.phase == ClockVideoPhase.Recording) {
                delay(500)
                if (state.phase == ClockVideoPhase.Recording) {
                    state = state.copy(
                        elapsedSeconds = ((System.currentTimeMillis() - startedAtMs) / 1000).toInt(),
                        framesStamped = framesDrawn,
                        stampSource = dominantStampSource(),
                    )
                }
            }
        }
    }

    private fun onFinalize(finalize: VideoRecordEvent.Finalize) {
        recordingActive = false
        tickerJob?.cancel()
        val endedAtMs = System.currentTimeMillis()
        val file = outputFile
        try {
            if (file != null) {
                val sidecar = buildSidecar(endedAtMs)
                File(file.parentFile, file.nameWithoutExtension + ".json")
                    .writeText(sidecar.toString(1))
                Log.i(TAG, "🎬 Finalized clock video ${file.name} (${file.length()} bytes)")
            }
            if (finalize.hasError()) {
                // The file, if any, is kept — a truncated recording is still
                // analyzable, same policy as the old ClockVideoWriter.
                state = ClockVideoState(
                    phase = ClockVideoPhase.Error,
                    errorMessage = "recording finalized with error code ${finalize.error}" +
                        (file?.takeIf { it.exists() }?.let { "; partial file kept at ${it.absolutePath}" } ?: ""),
                )
            } else {
                state = ClockVideoState(
                    phase = ClockVideoPhase.Done,
                    framesStamped = framesDrawn,
                    stampSource = dominantStampSource(),
                    savedPath = file?.absolutePath,
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "🎬 failed to finalize clock video", e)
            state = ClockVideoState(phase = ClockVideoPhase.Error, errorMessage = e.message ?: e.toString())
        } finally {
            // Camera stays bound: the preview keeps running for the next take;
            // release() (leaving the screen) is what unbinds.
            recording = null
        }
    }

    /**
     * Called on the overlay handler thread for every VIDEO_CAPTURE frame.
     */
    private fun onDrawFrame(frame: Frame): Boolean {
        val (stampMs, source) = stampFor(frame.timestampNanos)

        val canvas = frame.overlayCanvas
        // Software lockCanvas with a null dirty rect: previous buffer content
        // is undefined, repaint everything.
        canvas.drawColor(android.graphics.Color.TRANSPARENT, PorterDuff.Mode.CLEAR)

        // The canvas is in buffer coordinates; the pipeline then applies
        // crop -> rotate -> mirror. Set the inverse so we draw in final-video
        // coordinates and panel_rect means what the solver thinks it means.
        val crop = frame.cropRect
        val rot = frame.rotationDegrees
        val cw = crop.width().toFloat()
        val ch = crop.height().toFloat()
        val fw = if (rot % 180 == 0) crop.width() else crop.height()
        val fh = if (rot % 180 == 0) crop.height() else crop.width()
        val forward = Matrix()
        forward.setTranslate(-crop.left.toFloat(), -crop.top.toFloat())
        forward.postRotate(rot.toFloat(), cw / 2f, ch / 2f)
        forward.postTranslate((fw - cw) / 2f, (fh - ch) / 2f)
        if (frame.isMirroring) forward.postScale(-1f, 1f, fw / 2f, fh / 2f)
        val finalToBuffer = Matrix()
        forward.invert(finalToBuffer)
        canvas.setMatrix(finalToBuffer)

        val p = panel ?: QrTimePanel(fw, fh).also {
            panel = it
            videoWidth = fw
            videoHeight = fh
            rotationDegrees = rot
            val exact = PanelRectNorm(
                it.rect.left.toFloat() / fw,
                it.rect.top.toFloat() / fh,
                it.rect.width().toFloat() / fw,
                it.rect.height().toFloat() / fh,
            )
            scope.launch { state = state.copy(panelRectNorm = exact) }
        }
        p.draw(canvas, stampMs)

        if (recordingActive) {
            framesDrawn++
            when (source) {
                "sensor_boottime" -> sensorBoottimeFrames++
                "sensor_uptime" -> sensorUptimeFrames++
                else -> drawTimeFrames++
            }
        }
        return true
    }

    /**
     * Maps a frame's sensor timestamp to the epoch. The camera timestamp is in
     * either the boottime or the uptime timebase depending on
     * SENSOR_INFO_TIMESTAMP_SOURCE; recognize it by which base yields a sane
     * non-negative latency, and fall back to plain draw time when neither does.
     */
    private fun stampFor(tsNanos: Long): Pair<Long, String> {
        val nowMs = System.currentTimeMillis()
        val bootLatencyMs = (SystemClock.elapsedRealtimeNanos() - tsNanos) / 1e6
        if (bootLatencyMs in 0.0..2000.0) {
            recordLatency(bootLatencyMs)
            return (nowMs - bootLatencyMs).roundToLong() to "sensor_boottime"
        }
        val uptimeLatencyMs = (SystemClock.uptimeMillis() * 1_000_000L - tsNanos) / 1e6
        if (uptimeLatencyMs in 0.0..2000.0) {
            recordLatency(uptimeLatencyMs)
            return (nowMs - uptimeLatencyMs).roundToLong() to "sensor_uptime"
        }
        return nowMs to "draw_time"
    }

    private fun recordLatency(latencyMs: Double) {
        if (!recordingActive) return
        latencySumMs += latencyMs
        if (latencyMs > latencyMaxMs) latencyMaxMs = latencyMs
    }

    private fun dominantStampSource(): String? = when {
        sensorBoottimeFrames >= sensorUptimeFrames && sensorBoottimeFrames >= drawTimeFrames &&
            sensorBoottimeFrames > 0 -> "sensor_boottime"
        sensorUptimeFrames >= drawTimeFrames && sensorUptimeFrames > 0 -> "sensor_uptime"
        drawTimeFrames > 0 -> "draw_time"
        else -> null
    }

    private fun buildSidecar(endedAtMs: Long): JSONObject {
        val sensorFrames = sensorBoottimeFrames + sensorUptimeFrames
        return JSONObject().apply {
            put("kind", "hillview_clock_video")
            put("version", 2)
            put("recorder", "frontend2-camerax-overlay")
            put("started_at_ms", startedAtMs)
            put("ended_at_ms", endedAtMs)
            put("video", JSONObject().apply {
                put("width", videoWidth)
                put("height", videoHeight)
                put("mime", "video/mp4")
                put("rotation_degrees_applied", rotationDegrees)
            })
            put("qr", JSONObject().apply {
                put("format", "unix_ms")
                put("error_correction", "M")
                panel?.rect?.let {
                    put("panel_rect", JSONObject().apply {
                        put("x", it.left)
                        put("y", it.top)
                        put("w", it.width())
                        put("h", it.height())
                    })
                }
            })
            put("frames_drawn", framesDrawn)
            // v1-compatible naming: "capture time" now means sensor-timestamp
            // stamping rather than rVFC captureTime.
            put("capture_time_frames", sensorFrames)
            put("draw_time_frames", drawTimeFrames)
            put(
                "capture_latency_ms",
                if (sensorFrames > 0) {
                    JSONObject().apply {
                        put("mean", latencySumMs / sensorFrames)
                        put("max", latencyMaxMs)
                    }
                } else {
                    JSONObject.NULL
                },
            )
            put("stamp_source", dominantStampSource() ?: JSONObject.NULL)
            put("stamp_source_frames", JSONObject().apply {
                put("sensor_boottime", sensorBoottimeFrames)
                put("sensor_uptime", sensorUptimeFrames)
                put("draw_time", drawTimeFrames)
            })
            put("sensor_timestamp_source", sensorTimestampSource ?: JSONObject.NULL)
            put("device", JSONObject().apply {
                put("manufacturer", Build.MANUFACTURER)
                put("model", Build.MODEL)
                put("sdk_int", Build.VERSION.SDK_INT)
            })
        }
    }

    @androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
    private fun readTimestampSource(camera: Camera): String? =
        when (
            Camera2CameraInfo.from(camera.cameraInfo)
                .getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE)
        ) {
            CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME -> "REALTIME"
            CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_UNKNOWN -> "UNKNOWN"
            else -> null
        }

    private suspend fun awaitCameraProvider(): ProcessCameraProvider =
        suspendCancellableCoroutine { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener(
                { cont.resume(future.get()) },
                ContextCompat.getMainExecutor(context),
            )
        }

    private fun cleanupCamera() {
        cameraBound = false
        videoRecorder = null
        cameraProvider?.unbindAll()
        cameraProvider = null
        overlayEffect?.close()
        overlayEffect = null
        handlerThread?.quitSafely()
        handlerThread = null
    }

    fun release() {
        // If a recording is live, stopping it triggers Finalize, which keeps
        // the partial file and writes the sidecar — same orphan policy as the
        // old plugin.
        recording?.stop()
        recording = null
        tickerJob?.cancel()
        cleanupCamera()
        scope.cancel()
    }

    @Composable
    override fun CameraPane(modifier: Modifier) {
        val camera = cz.hillview.core.permissions.rememberPermissionsState(
            permissions = listOf(Manifest.permission.CAMERA),
        )
        val granted = camera.granted

        if (granted) {
            BoxWithConstraints(modifier = modifier.background(Color(0xFF111111))) {
                AndroidView(
                    factory = { c ->
                        PreviewView(c).apply {
                            scaleType = PreviewView.ScaleType.FIT_CENTER
                            // TextureView mode: composites like a normal view
                            // under the ghost overlay (surfaces have their own
                            // z-order quirks).
                            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                        }.also { previewView = it }
                    },
                    // PreviewView scales its texture beyond the view bounds to
                    // apply the shared-viewport crop, and Compose interop
                    // containers don't clip child views — clip explicitly or
                    // the preview bleeds over the whole screen.
                    modifier = Modifier
                        .fillMaxSize()
                        .clipToBounds(),
                )

                // Ghost of the recorded QR panel: the burn-in happens only on
                // the VIDEO_CAPTURE stream (keeping panel_rect exact), so mark
                // the covered region here — aim the camera's menu clear of it.
                // The shared ViewPort makes the preview show the recorded FOV,
                // and FIT_CENTER letterboxing is undone below.
                val ghost = state.panelRectNorm ?: ESTIMATED_PANEL
                val paneW = constraints.maxWidth.toFloat()
                val paneH = constraints.maxHeight.toFloat()
                val aspect = 9f / 16f
                val contentW = minOf(paneW, paneH * aspect)
                val contentH = contentW / aspect
                val offX = (paneW - contentW) / 2f
                val offY = (paneH - contentH) / 2f
                val d = LocalDensity.current
                Box(
                    modifier = Modifier
                        .offset(
                            x = with(d) { (offX + ghost.x * contentW).toDp() },
                            y = with(d) { (offY + ghost.y * contentH).toDp() },
                        )
                        .size(
                            width = with(d) { (ghost.w * contentW).toDp() },
                            height = with(d) { (ghost.h * contentH).toDp() },
                        )
                        .background(Color.White.copy(alpha = 0.25f))
                        .border(1.dp, Color.White.copy(alpha = 0.8f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = "QR",
                        color = Color.White.copy(alpha = 0.9f),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        } else {
            cz.hillview.core.permissions.PermissionGatePane(
                state = camera,
                explanation = "Camera access is needed to record the calibration video.",
                testTagPrefix = "clockvideo-camera",
                modifier = modifier,
            )
        }

        // Live preview from the moment the pane is usable — aim first, record
        // second. Re-fires when the permission grant flips granted to true.
        LaunchedEffect(granted) {
            if (granted) openCamera()
        }

        // Recording sessions are minutes long and hands-off; don't let the
        // screen sleep mid-recording (the old app used a web wake lock).
        val view = LocalView.current
        DisposableEffect(state.phase) {
            view.keepScreenOn = state.phase == ClockVideoPhase.Recording
            onDispose { view.keepScreenOn = false }
        }
    }
}
