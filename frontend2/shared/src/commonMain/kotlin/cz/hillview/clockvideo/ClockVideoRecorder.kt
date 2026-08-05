package cz.hillview.clockvideo

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.ui.Modifier

// Clock-calibration video recorder: the rear camera films an external camera's
// date/time settings screen while every frame gets a QR code of the phone's
// UTC time burned in. The file's container timestamps are irrelevant by
// design — each frame carries its own real time in pixels, so the pipeline
// (video_time_correction.py in the pics repo) only trusts pixels. The solver's
// hard requirements: QR payload is the decimal unix-time-in-ms, the overlay
// panel sits at a fixed position recorded as qr.panel_rect in the sidecar
// JSON (so it can be masked before the camera-clock OCR), and the sidecar
// shares the video's basename with a .json extension.

enum class ClockVideoPhase { Idle, Starting, Recording, Saving, Done, Error }

/** The QR panel's position normalized to video dimensions (0..1). */
data class PanelRectNorm(val x: Float, val y: Float, val w: Float, val h: Float)

data class ClockVideoState(
    val supported: Boolean = true,
    val phase: ClockVideoPhase = ClockVideoPhase.Idle,
    val elapsedSeconds: Int = 0,
    val framesStamped: Int = 0,
    // Where the per-frame stamps come from: "sensor_boottime"/"sensor_uptime"
    // (frame sensor timestamp mapped to epoch — no camera-pipeline latency
    // bias) or "draw_time" (stamped when the overlay was drawn).
    val stampSource: String? = null,
    val savedPath: String? = null,
    val errorMessage: String? = null,
    // Where the QR panel lands in the recorded video, for the preview ghost.
    // A geometry-formula estimate until the first frame is drawn, exact after.
    val panelRectNorm: PanelRectNorm? = null,
)

@Stable
interface ClockVideoRecorder {
    val state: ClockVideoState

    fun start()
    fun stop()

    /** Camera preview area, including any platform permission UI. */
    @Composable
    fun CameraPane(modifier: Modifier)
}

@Composable
expect fun rememberClockVideoRecorder(): ClockVideoRecorder
