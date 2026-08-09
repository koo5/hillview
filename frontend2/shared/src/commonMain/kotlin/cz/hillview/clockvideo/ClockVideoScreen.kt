package cz.hillview.clockvideo

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun ClockVideoScreen(onBack: () -> Unit) {
    val recorder = rememberClockVideoRecorder()
    val state = recorder.state

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                text = "Clock calibration video",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        recorder.CameraPane(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        )

        StatusLine(state)

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
        ) {
            when (state.phase) {
                ClockVideoPhase.Recording -> Button(
                    onClick = recorder::stop,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFDC2626)),
                    modifier = Modifier.testTag("clock-video-stop-button"),
                ) { Text("Stop & Save") }

                ClockVideoPhase.Starting, ClockVideoPhase.Saving -> Button(
                    onClick = {},
                    enabled = false,
                ) { Text("…") }

                else -> Button(
                    onClick = recorder::start,
                    enabled = state.supported,
                    modifier = Modifier.testTag("clock-video-start-button"),
                ) {
                    Text(
                        if (state.phase == ClockVideoPhase.Done || state.phase == ClockVideoPhase.Error) {
                            "Record Another"
                        } else {
                            "Start Recording"
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun StatusLine(state: ClockVideoState) {
    val text = when (state.phase) {
        ClockVideoPhase.Idle ->
            if (state.supported) {
                "Ready. Fill the frame with the camera's clock screen — keep it " +
                    "clear of the marked corner, the QR overlay covers it in the " +
                    "recording — then start."
            } else {
                state.errorMessage ?: "Not supported on this platform."
            }
        ClockVideoPhase.Starting -> "Starting camera…"
        ClockVideoPhase.Recording ->
            "● Recording — ${state.elapsedSeconds}s, ${state.framesStamped} frames" +
                (state.stampSource?.let { " · $it stamps" } ?: "")
        ClockVideoPhase.Saving -> "Saving…"
        ClockVideoPhase.Done -> "Saved to ${state.savedPath ?: "?"}"
        ClockVideoPhase.Error -> state.errorMessage ?: "Unknown error"
    }
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = if (state.phase == ClockVideoPhase.Error) {
            MaterialTheme.colorScheme.error
        } else {
            MaterialTheme.colorScheme.onSurface
        },
        modifier = Modifier
            .fillMaxWidth()
            .testTag("clock-video-status"),
    )
}
