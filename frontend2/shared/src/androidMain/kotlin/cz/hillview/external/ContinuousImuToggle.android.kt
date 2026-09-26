package cz.hillview.external

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
actual fun ContinuousImuToggle() {
    val context = LocalContext.current.applicationContext
    val on by ExternalImuSettings.continuous.collectAsState()
    // The flow starts at the DEFAULT; this makes it the stored answer. Cheap and
    // idempotent, so running it on every entry to the pane costs nothing.
    LaunchedEffect(Unit) { ExternalImuSettings.load(context) }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.testTag("external-imu-continuous-row"),
    ) {
        Switch(
            checked = on,
            onCheckedChange = { ExternalImuSettings.setContinuous(context, it) },
            modifier = Modifier.testTag("external-imu-continuous"),
        )
        Column {
            Text("Log inertial samples continuously", style = MaterialTheme.typography.bodyMedium)
            // The number is the point of the switch: without it "continuously"
            // sounds free. ~1 kHz across two sensors, written as CSV.
            Text(
                if (on) {
                    "Full rate, for shutter detection. Roughly 100 MB of CSV an hour."
                } else {
                    "Off: samples are kept only around this app's own captures."
                },
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("external-imu-continuous-note"),
            )
        }
    }
}
