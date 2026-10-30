package cz.hillview.help

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

@Composable
fun PanoramaxInfoScreen(onBack: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("panoramax-info"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                "Contributing to Panoramax",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        Section("Your grant and the published licence")
        Text("Your upload licence is the grant you give Hillview. Full rights to Hillview and the Panoramax contribution grant allow sharing; CC BY-SA 4.0 + OSM alone does not cover the federation's derived-data uses.")
        Text("For Full rights photos, turning sharing on publishes the photo as Panoramax even if it does not qualify for federation. The Panoramax contribution grant always publishes as Panoramax, with sharing on or off. Panoramax licence wording is a placeholder pending the final text.")
        Section("Choose which photos to share")
        Text("The P button above the camera settings button switches sharing for future photos. Each photo keeps that choice. Change an existing photo's Panoramax on/off button in Device photos; offline edits are sent when you reconnect.")
        Section("Anonymization")
        Text("Only photos checked by the detector with no blurred boxes qualify. Photos with anonymization doodles, manual rectangles, or skipped blurring are excluded from federation.")
        Section("Photo quality")
        Text("Contribute useful, clear views with a location and capture time. Further photo-quality rules are being finalized.")
        Section("Moderation")
        Text("Sharing offers a photo for contribution. Moderators can withhold approval for a photo or disable an account's contributions. Existing visibility, processing and moderation checks still apply.")
        Section("Copies may remain")
        Text("Turning sharing off stops future federation from Hillview. Copies already collected or reused elsewhere may remain available.")
    }
}

@Composable
private fun Section(title: String) {
    Text(
        title,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(top = 6.dp),
    )
}

