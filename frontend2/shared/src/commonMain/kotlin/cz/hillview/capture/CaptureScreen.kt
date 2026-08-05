package cz.hillview.capture

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import cz.hillview.upload.PendingUpload
import cz.hillview.upload.UploadPipeline
import kotlinx.coroutines.delay
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
fun CaptureScreen(
    onBack: () -> Unit,
    uploadPipeline: UploadPipeline = org.koin.compose.koinInject(),
) {
    val capture = rememberPhotoCapture()
    val state = capture.state
    val queueStats by uploadPipeline.stats.collectAsState()

    // Every capture goes straight into the offline-first pipeline; it no-ops
    // when logged out and the entry survives for auto-upload-on-login.
    LaunchedEffect(state.lastPhoto) {
        val photo = state.lastPhoto ?: return@LaunchedEffect
        uploadPipeline.onPhotoCaptured(
            PendingUpload(
                id = photo.path,
                filePath = photo.path,
                filename = photo.path.substringAfterLast('/'),
                latitude = photo.snapshot.latitude,
                longitude = photo.snapshot.longitude,
                altitude = photo.snapshot.altitude,
                bearing = photo.snapshot.bearingDeg?.toDouble(),
            )
        )
    }

    // Stats poll for pipelines that derive stats from external state (the
    // shared-kt stack uploads in WorkManager, off this screen's call path).
    LaunchedEffect(Unit) {
        while (true) {
            uploadPipeline.refreshStats()
            delay(2_000)
        }
    }

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
                text = "Capture",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        capture.CameraPane(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
        )

        StatusLine(state)

        Text(
            text = "uploads: ${queueStats.done} done" +
                (if (queueStats.duplicate > 0) ", ${queueStats.duplicate} dup" else "") +
                (if (queueStats.pending > 0) ", ${queueStats.pending} pending" else "") +
                (if (queueStats.failed > 0) ", ${queueStats.failed} failed" else "") +
                (queueStats.lastError?.let { " · $it" } ?: ""),
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("capture-upload-stats"),
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
        ) {
            Button(
                onClick = capture::capture,
                enabled = state.ready && !state.capturing,
                modifier = Modifier
                    .size(width = 160.dp, height = 56.dp)
                    .testTag("capture-shutter"),
            ) {
                Text(if (state.capturing) "…" else "Capture")
            }
        }
    }
}

@Composable
private fun StatusLine(state: CaptureState) {
    val parts = buildList {
        add(
            when {
                !state.supported -> state.errorMessage ?: "Not supported on this platform"
                !state.ready -> "Starting camera…"
                state.hasFix -> "GPS fix"
                else -> "no GPS fix"
            }
        )
        state.bearingDeg?.let { add("bearing ${it.roundToInt()}°") }
        state.lastPhoto?.let { photo ->
            val s = photo.snapshot
            val loc = if (s.latitude != null && s.longitude != null) {
                "@${fmt(s.latitude)},${fmt(s.longitude)}"
            } else {
                "no location"
            }
            add("saved ${photo.path.substringAfterLast('/')} $loc")
        }
        state.errorMessage?.takeIf { state.supported }?.let { add(it) }
    }
    Text(
        text = parts.joinToString(" · "),
        style = MaterialTheme.typography.bodySmall,
        color = if (state.errorMessage != null && state.supported) {
            MaterialTheme.colorScheme.error
        } else {
            MaterialTheme.colorScheme.onSurface
        },
        modifier = Modifier
            .fillMaxWidth()
            .testTag("capture-status"),
    )
}

private fun fmt(value: Double): String {
    val rounded = (value * 100_000).roundToInt() / 100_000.0
    return rounded.toString()
}
