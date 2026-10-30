package cz.hillview.help

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.settings.LICENSE_INFO
import cz.hillview.settings.UploadSettingsRepository
import org.koin.compose.koinInject

/** Available offline, beside each grant; opening this page accepts nothing. */
@Composable
fun LicenseInfoScreen(
    licenseId: String,
    onBack: () -> Unit,
    onOpenPanoramaxInfo: () -> Unit,
    repository: UploadSettingsRepository = koinInject(),
) {
    val license = LICENSE_INFO.firstOrNull { it.id == licenseId }
    val uriHandler = LocalUriHandler.current
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("license-info-$licenseId"),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        TextButton(onClick = onBack, modifier = Modifier.testTag("license-info-back")) {
            Text("< Back", style = MaterialTheme.typography.bodyLarge)
        }
        Text(
            license?.label ?: "Unknown upload license",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.testTag("license-info-title"),
        )
        if (license != null) {
            Text("Your grant to Hillview", style = MaterialTheme.typography.titleMedium)
            Text(license.explainer, style = MaterialTheme.typography.bodyLarge)
            Text("Upload grant and public license", style = MaterialTheme.typography.titleMedium)
            Text(
                "The upload grant is the permission you give Hillview. The public license says " +
                    "how other people may reuse the published photo. They can be different.",
                style = MaterialTheme.typography.bodyLarge,
            )
            Text("Panoramax sharing", style = MaterialTheme.typography.titleMedium)
            Text(
                when (licenseId) {
                    "full1" -> "This grant allows Panoramax sharing. With sharing on, Hillview publishes " +
                        "the photo as Panoramax; with sharing off, it publishes as all rights reserved " +
                        "with the OSM mapping grant. Sharing offers the photo to the federation; " +
                        "eligibility and view selection still apply."
                    "panoramax_in" -> "Hillview publishes the photo as Panoramax even with sharing off. " +
                        "Sharing separately offers it to the federation, subject to eligibility and " +
                        "view selection. The final Panoramax license wording is still pending."
                    else -> "CC BY-SA 4.0 + OSM alone does not cover the federation's derived-data " +
                        "uses. Turning on sharing does not make photos under this grant eligible " +
                        "for Panoramax federation."
                },
                style = MaterialTheme.typography.bodyLarge,
            )
            Text("Your choice", style = MaterialTheme.typography.titleMedium)
            Text(
                "Reading this help changes nothing. Choose a grant in Settings to apply it to future " +
                    "captures. Photos already captured keep their grant. Uploading and Panoramax " +
                    "sharing have separate controls.",
                style = MaterialTheme.typography.bodyLarge,
            )
            TextButton(
                onClick = onOpenPanoramaxInfo,
                modifier = Modifier.testTag("license-info-panoramax"),
            ) { Text("How Panoramax contribution works", style = MaterialTheme.typography.bodyLarge) }
            TextButton(
                onClick = { uriHandler.openUri(repository.settings.value.webUrl.trimEnd('/') + "/licensing") },
                modifier = Modifier.testTag("license-info-website"),
            ) { Text("Hillview licensing details online", style = MaterialTheme.typography.bodyLarge) }
        }
    }
}
