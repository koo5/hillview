package cz.hillview.capture

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.requiredWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Slider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import cz.hillview.upload.PendingUpload
import cz.hillview.upload.UploadPipeline
import kotlinx.coroutines.delay
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt

@Composable
fun CaptureScreen(
    onBack: () -> Unit,
    onOpenSettings: () -> Unit = {},
    uploadPipeline: UploadPipeline = org.koin.compose.koinInject(),
    uploadSettingsRepo: cz.hillview.settings.UploadSettingsRepository =
        org.koin.compose.koinInject(),
) {
    val capture = rememberPhotoCapture()
    val state = capture.state
    val queueStats by uploadPipeline.stats.collectAsState()
    val uploadSettings by uploadSettingsRepo.settings.collectAsState()

    // The lifted-gate state: session-scoped, so the fix requirement guards
    // every fresh visit and lifting it is a deliberate act each time.
    var manualLocationArmed by rememberSaveable { mutableStateOf(false) }
    val mapStateStore: cz.hillview.map.MapStateStore = org.koin.compose.koinInject()

    // The after-capture auto-upload prompt: shown once a capture lands while
    // auto-upload is off, unless the user chose "never". Session-dismissed
    // so it cannot nag a rapid-fire run.
    var promptVisible by rememberSaveable { mutableStateOf(false) }
    var promptDismissed by rememberSaveable { mutableStateOf(false) }

    // 0 = one shot per tap; otherwise the shutter arms a repeating run.
    var intervalSec by rememberSaveable { mutableStateOf(0) }
    var repeating by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(repeating, intervalSec) {
        if (!repeating || intervalSec <= 0) return@LaunchedEffect
        while (true) {
            if (!state.capturing) capture.capture()
            delay(intervalSec * 1000L)
        }
    }

    // Every capture goes straight into the offline-first pipeline; it no-ops
    // when logged out and the entry survives for auto-upload-on-login.
    LaunchedEffect(state.lastPhoto) {
        val photo = state.lastPhoto ?: return@LaunchedEffect
        uploadPipeline.onPhotoCaptured(
            PendingUpload(
                id = photo.path,
                filePath = photo.path,
                filename = photo.filename,
                latitude = photo.snapshot.latitude,
                longitude = photo.snapshot.longitude,
                altitude = photo.snapshot.altitude,
                // True heading — the DB/authorize bearing is true north
                // everywhere in the pipeline (see SensorSnapshot).
                bearing = photo.snapshot.trueBearingDeg?.toDouble(),
                capturedAtMs = photo.snapshot.capturedAtMs,
            )
        )
        // The original waits 800 ms after the shutter before prompting, "to
        // avoid UI confusion" right at the moment of capture.
        if (!uploadSettings.autoUploadEnabled &&
            uploadSettings.autoUploadPromptEnabled &&
            !promptDismissed
        ) {
            delay(800)
            promptVisible = true
        }
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

        if (promptVisible) {
            AutoUploadPrompt(
                onConfigure = { promptVisible = false; onOpenSettings() },
                onDismiss = { promptVisible = false; promptDismissed = true },
                onNever = {
                    promptVisible = false
                    uploadSettingsRepo.update { it.copy(autoUploadPromptEnabled = false) }
                },
            )
        }

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

        // The gate's escape hatch, offered only while it is actually shut:
        // shooting underground means positioning the map by hand first and
        // capturing against that.
        if (state.ready && !state.hasFix) {
            if (!manualLocationArmed) {
                TextButton(
                    onClick = {
                        val spatial = mapStateStore.load()?.first
                            ?: cz.hillview.map.SpatialState()
                        capture.manualLocation = ManualLocation(
                            latitude = spatial.latitude,
                            longitude = spatial.longitude,
                        )
                        manualLocationArmed = true
                    },
                    modifier = Modifier.testTag("capture-use-map-position"),
                ) {
                    Text("No GPS fix — capture at the map position instead")
                }
            } else {
                TextButton(
                    onClick = {
                        capture.manualLocation = null
                        manualLocationArmed = false
                    },
                    modifier = Modifier.testTag("capture-manual-location"),
                ) {
                    val at = capture.manualLocation
                    Text(
                        "Using map position" +
                            (at?.let { " (${fmt(it.latitude)}, ${fmt(it.longitude)})" } ?: "") +
                            " — tap to require GPS again",
                    )
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Interval as a continuous slider rather than a couple of fixed
            // modes: the useful spacing depends on how fast you're moving.
            IntervalSlider(
                intervalSec = intervalSec,
                enabled = !repeating,
                onChange = { intervalSec = it },
            )

            Button(
                onClick = {
                    if (intervalSec == 0) capture.capture() else repeating = !repeating
                },
                // The location gate (see shutterEnabled): no fix, no photo —
                // unless the user has deliberately lifted it below.
                enabled = shutterEnabled(state.ready, state.hasFix, manualLocationArmed) &&
                    (repeating || !state.capturing),
                modifier = Modifier
                    .size(width = 160.dp, height = 56.dp)
                    .testTag("capture-shutter"),
            ) {
                Text(
                    when {
                        repeating -> "Stop"
                        intervalSec > 0 -> "Start ${intervalSec}s"
                        state.capturing -> "…"
                        else -> "Capture"
                    }
                )
            }
        }
    }
}

/** Off, then 1…60 s. Vertical because it sits beside the shutter. */
@Composable
private fun IntervalSlider(
    intervalSec: Int,
    enabled: Boolean,
    onChange: (Int) -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.padding(end = 16.dp),
    ) {
        Text(
            text = if (intervalSec == 0) "single" else "${intervalSec}s",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.testTag("capture-interval-value"),
        )
        Box(
            modifier = Modifier.size(width = 48.dp, height = 140.dp),
            contentAlignment = Alignment.Center,
        ) {
            // Material has no vertical slider; rotating a horizontal one and
            // giving it the box's height as its width is the usual trick.
            Slider(
                value = intervalSec.toFloat(),
                onValueChange = { onChange(it.roundToInt()) },
                valueRange = 0f..60f,
                enabled = enabled,
                modifier = Modifier
                    .requiredWidth(140.dp)
                    .rotate(-90f)
                    .testTag("capture-interval-slider"),
            )
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
            add("saved ${photo.filename} $loc")
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

/**
 * "Your photos are staying on this device." One line, three exits — the
 * same three the original offers: configure (goes to upload settings, where
 * the licence gate lives), not now, and never (persisted, so the overlay
 * can never block a rapid-fire run again).
 */
@Composable
private fun AutoUploadPrompt(
    onConfigure: () -> Unit,
    onDismiss: () -> Unit,
    onNever: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .testTag("auto-upload-prompt"),
    ) {
        Text(
            "Auto-upload is off — captures stay on this device.",
            style = MaterialTheme.typography.bodyMedium,
        )
        Row {
            TextButton(
                onClick = onConfigure,
                modifier = Modifier.testTag("configure-auto-upload"),
            ) { Text("Set up") }
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testTag("dismiss-auto-upload-prompt"),
            ) { Text("Not now") }
            TextButton(
                onClick = onNever,
                modifier = Modifier.testTag("never-auto-upload-prompt"),
            ) { Text("Never ask") }
        }
    }
}
