package cz.hillview.diag

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Tracking rows dropped this process because the sensor-log write queue passed its
 * memory budget — 0 until the first (GeoTrackingManager.droppedRows on Android).
 */
expect fun trackingDroppedRows(): StateFlow<Long>

/**
 * Whether this session has already been warned. Process-wide, not `remember`: a
 * rotation or a recreated activity is the same session, and must not warn again.
 */
private val warnedThisSession = MutableStateFlow(false)

/**
 * The one warning per app session that the sensor log has started losing rows
 * (user, 2026-11-06: "you really dont want those values to drop when you're out
 * shooting ... the ui should warn when it has to finally start dropping values").
 *
 * Drawn over every screen from [cz.hillview.App]. It cannot stop the drop — the queue
 * is at its budget because the database is not keeping up, and the alternative was
 * the process running out of memory — so it says what is lost and what is not, and
 * the event log carries the details and the final count.
 */
@Composable
fun TrackingDropWarning() {
    val warned by warnedThisSession.collectAsState()
    // Warned already: stop watching the count, which can climb by hundreds a second
    // while the queue is full and would recompose this for every one.
    if (warned) return
    val dropped by trackingDroppedRows().collectAsState()
    if (dropped == 0L) return
    AlertDialog(
        onDismissRequest = { warnedThisSession.value = true },
        confirmButton = {
            TextButton(
                onClick = { warnedThisSession.value = true },
                modifier = Modifier.testTag("tracking-drop-warning-ok"),
            ) { Text("OK") }
        },
        title = { Text("Sensor log is dropping data") },
        text = {
            Text(
                "The phone is not writing the sensor log to its database fast enough, and " +
                    "the backlog has reached its memory limit. To keep the app from running " +
                    "out of memory, new bearings, positions and motion samples are being " +
                    "dropped until it catches up ($dropped so far).\n\n" +
                    "Photos are still saved, with the position and direction they were " +
                    "taken at. What has gaps is the continuous log beside them, including " +
                    "the motion window around a shutter. The Event log has the details.",
                modifier = Modifier.testTag("tracking-drop-warning-text"),
            )
        },
        modifier = Modifier.testTag("tracking-drop-warning"),
    )
}
