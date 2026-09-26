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
import cz.hillview.settings.geoAutoExportEnabled

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
    /** What the tracking tables currently hold. */
    suspend fun tableCounts(): TrackingCounts
}

/**
 * Row counts for the external pane's readout.
 *
 * The IMU count is the one this mode most needs and the one it did not have: the
 * pane offers a switch for continuous inertial logging and, until this, showed no
 * evidence of it doing anything. A toggle with no feedback is a toggle you cannot
 * trust.
 */
data class TrackingCounts(
    val bearings: Int = 0,
    val locations: Int = 0,
    val imuSamples: Int = 0,
)

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
fun ExternalCameraPane(
    stateHolder: cz.hillview.map.MapStateHolder = org.koin.compose.koinInject(),
) {
    val controller = rememberExternalCameraController()
    val running by controller.running.collectAsState()
    val status by controller.status.collectAsState()
    val notice by controller.notice.collectAsState()
    val spatial by stateHolder.spatial.collectAsState()
    val bearing by stateHolder.bearing.collectAsState()
    var counts by remember { mutableStateOf(TrackingCounts()) }

    // Recording is started and stopped by the ACTIVITY (MainScreen), not
    // here: this pane is not composed in float mode — which is precisely
    // when recording must keep going — so its composition is the wrong
    // lifetime to hang it on. The pane only displays.
    // Polled once a second, which also gives the IMU rate for free: the difference
    // between two counts is samples per second, and that is the number that says
    // whether FASTEST actually took (a few hundred) or the fallback did (a few
    // tens) — visible on the device without a cable.
    var imuRate by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) {
        while (true) {
            val next = controller.tableCounts()
            // Only when the table GREW: a dump clears it, and a negative delta is
            // the export having run, not a rate.
            if (next.imuSamples > counts.imuSamples) {
                imuRate = next.imuSamples - counts.imuSamples
            }
            counts = next
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

        // THE APP'S value pair, not a feed of this pane's own — the whole
        // point of the engine work. This is the same bearing a capture would
        // stamp (car mode's mount offset included, a manual claim included)
        // and the same position the map is showing.
        Text(
            "%.6f, %.6f · %.1f° (%s)".format(
                spatial.latitude, spatial.longitude, bearing.bearing, bearing.source,
            ),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.testTag("external-camera-stamp"),
        )
        // The raw fix underneath it, for accuracy and provenance.
        Text(
            status,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.testTag("external-camera-status"),
        )

        Text(
            "Recorded: ${counts.bearings} heading rows · ${counts.locations} location rows" +
                " · ${counts.imuSamples} inertial samples" +
                if (imuRate > 0) " (${imuRate}/s)" else "",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.testTag("external-camera-counts"),
        )

        // THE POINT OF SAYING THIS HERE. The tracking tables are cleared five
        // minutes back on every dump, and the dump only WRITES a file when
        // auto-export is on. With it off, continuous logging fills a table that is
        // then thrown away — the samples never reach a file and nothing else
        // anywhere says so. This mode is the one where that matters, because an
        // external camera's frames have no other route to a motion record.
        if (!geoAutoExportEnabled()) {
            Text(
                "Auto-export is OFF — these rows are cleared every few minutes and " +
                    "never written to a file. Turn it on in settings, or use " +
                    "\"Export CSVs now\" before leaving.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("external-camera-export-warning"),
            )
        }

        // Directly under the row counts, because that is the readout of the thing
        // it controls. NOT "before you start recording": there is no start
        // button — MainScreen calls setRunning(activity == "external"), so the
        // session is already running by the time this pane is on screen and the
        // header already says "● recording". Which is precisely why flipping this
        // has to take effect live, and why both claimants of `imuContinuous`
        // re-claim on change (see ExternalImuSettings).
        ContinuousImuToggle()

        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = { controller.openSystemCamera() },
                modifier = Modifier.testTag("external-open-camera"),
            ) { Text("Open camera app") }

            // FLOAT MODE. Shrink to a PiP window first, THEN bring the
            // camera app up, so the map is already floating when it appears.
            // Safe to do from here specifically: this activity holds no
            // camera, and a camera app that comes to the front would evict
            // us anyway — being the pane without a stream is what makes the
            // hand-over clean rather than a race.
            if (cz.hillview.pip.pipSupported()) {
                Button(
                    onClick = {
                        cz.hillview.pip.enterPipMode()
                        cz.hillview.pip.launchSystemCamera()
                    },
                    modifier = Modifier.testTag("external-float-over-camera"),
                ) { Text("Float over camera") }
            }

            TextButton(
                onClick = { exportGeoTrackingNow() },
                modifier = Modifier.testTag("external-export-now"),
            ) { Text("Export CSVs now") }
        }

        // Below the buttons: a notice arriving must not move the control
        // you were reaching for.
        notice?.let {
            Text(
                it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("external-camera-notice"),
            )
        }

        Text(
            "CSVs also export automatically every 5 minutes while recording " +
                "(with tracking auto-export on in Settings) and when the mode " +
                "is left. Files land in GeoTrackingDumps/.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
