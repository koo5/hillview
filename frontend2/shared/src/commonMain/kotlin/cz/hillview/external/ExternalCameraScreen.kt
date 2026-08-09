package cz.hillview.external

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.settings.exportGeoTrackingNow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow

/**
 * What the platform provides to the external-camera pane. Android backs
 * this with [ExternalCameraService]; desktop is a stub (there is no system
 * camera to shoot with).
 */
interface ExternalCameraController {
    val running: StateFlow<Boolean>
    val status: StateFlow<String>
    /** A user-facing obstacle ("location permission missing"), or null. */
    val notice: StateFlow<String?>
    fun setRunning(on: Boolean)
    fun openSystemCamera()
    /** (bearings rows, locations rows) currently in the tracking tables. */
    suspend fun tableCounts(): Pair<Int, Int>
}

@Composable
expect fun rememberExternalCameraController(): ExternalCameraController

/**
 * The external-camera mode: a PANEL alongside capture and gallery (user's
 * framing — "just another panel mode next to capture mode… just no camera
 * stream running"), not a separate page. The map below it stays fully in
 * charge — elections (the pill's manual claim), car mode, follow-me — while
 * this pane shows the live record.
 *
 * The pane being active IS the mode: composing it starts the tracking
 * engine, switching to another panel stops it. The engine is a foreground
 * service so the record SURVIVES the system camera app taking the screen —
 * backgrounding does not leave the composition, so the service keeps
 * running exactly then, which is the whole point.
 */
@Composable
fun ExternalCameraPane() {
    val controller = rememberExternalCameraController()
    val running by controller.running.collectAsState()
    val status by controller.status.collectAsState()
    val notice by controller.notice.collectAsState()
    var counts by remember { mutableStateOf(0 to 0) }

    DisposableEffect(Unit) {
        controller.setRunning(true)
        onDispose { controller.setRunning(false) }
    }
    LaunchedEffect(Unit) {
        while (true) {
            counts = controller.tableCounts()
            delay(1_000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("external-camera-pane"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("External camera", style = MaterialTheme.typography.titleMedium)
            Text(
                if (running) "● recording" else "starting…",
                color = if (running) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.outline
                },
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.testTag("external-camera-state"),
            )
        }

        Text(
            "Position and heading are being recorded continuously — including " +
                "while another camera app is in front — so its photos can be " +
                "stamped from the record afterwards. The map below stays in " +
                "charge: claim a map position or switch car mode there as usual.",
            style = MaterialTheme.typography.bodySmall,
        )

        notice?.let {
            Text(
                it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("external-camera-notice"),
            )
        }

        Text(
            status,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.testTag("external-camera-status"),
        )

        Text(
            "Recorded: ${counts.first} heading rows · ${counts.second} location rows",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.testTag("external-camera-counts"),
        )

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = { controller.openSystemCamera() },
                modifier = Modifier.testTag("external-open-camera"),
            ) { Text("Open camera app") }

            TextButton(
                onClick = { exportGeoTrackingNow() },
                modifier = Modifier.testTag("external-export-now"),
            ) { Text("Export CSVs now") }
        }

        Text(
            "CSVs also export automatically every 5 minutes while recording " +
                "(with tracking auto-export on in Settings) and when the mode " +
                "is left. Files land in GeoTrackingDumps/.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
