package cz.hillview.clockvideo

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

// The desktop target exists for fast Compose iteration (hot reload), not for
// recording — calibration videos are made with the phone. Honest stub only.
private class DesktopClockVideoRecorder : ClockVideoRecorder {
    override val state = ClockVideoState(
        supported = false,
        errorMessage = "Clock video recording is only available on Android.",
    )

    override fun start() {}
    override fun stop() {}

    @Composable
    override fun CameraPane(modifier: Modifier) {
        Box(
            modifier = modifier.background(Color(0xFF111111)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "Camera not available on desktop",
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

@Composable
actual fun rememberClockVideoRecorder(): ClockVideoRecorder =
    remember { DesktopClockVideoRecorder() }
