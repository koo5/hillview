package cz.hillview.settings.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.core.permissions.rememberNotificationPermissionRequester
import cz.hillview.settings.ALLOWED_LICENSES
import cz.hillview.settings.CompassSettingsRepository
import cz.hillview.settings.StorageMode
import cz.hillview.settings.UploadSettingsRepository
import org.koin.compose.koinInject

/**
 * Edits the upload settings — on Android these are live config for the
 * shared-kt upload stack (every change persists immediately into the prefs
 * it reads). The server URL takes effect for auth/login on next app start
 * (BackendConfig is resolved once at startup); the upload stack reads it
 * per drain.
 */
@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    repository: UploadSettingsRepository = koinInject(),
    compassRepository: CompassSettingsRepository = koinInject(),
) {
    val settings by repository.settings.collectAsState()
    val compass by compassRepository.settings.collectAsState()
    val requestNotifications = rememberNotificationPermissionRequester()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                text = "Settings",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        OutlinedTextField(
            value = settings.serverUrl,
            onValueChange = { url -> repository.update { it.copy(serverUrl = url) } },
            label = { Text("API URL") },
            supportingText = { Text("Full API URL incl. /api — auth picks it up on next start") },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("settings-server-url"),
        )

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Auto-upload", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Upload captures in the background",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = settings.autoUploadEnabled,
                onCheckedChange = { on ->
                    // Upload progress/auth notifications become relevant now
                    // (no-op below Android 13 / on desktop).
                    if (on) requestNotifications()
                    repository.update { it.copy(autoUploadEnabled = on) }
                },
                modifier = Modifier.testTag("settings-auto-upload"),
            )
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Wi-Fi only", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Defer uploads on metered networks",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = settings.wifiOnly,
                onCheckedChange = { on -> repository.update { it.copy(wifiOnly = on) } },
                modifier = Modifier.testTag("settings-wifi-only"),
            )
        }

        Column {
            Text("Upload license", style = MaterialTheme.typography.bodyLarge)
            ALLOWED_LICENSES.forEach { license ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = settings.license == license,
                        onClick = { repository.update { it.copy(license = license) } },
                        modifier = Modifier.testTag("settings-license-$license"),
                    )
                    Text(license, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }

        Column {
            Text("Photo storage", style = MaterialTheme.typography.bodyLarge)
            Text(
                "Where captures are saved; if the chosen target is unavailable " +
                    "the others are tried in order.",
                style = MaterialTheme.typography.bodySmall,
            )
            StorageMode.entries.forEach { mode ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = settings.storage == mode,
                        onClick = { repository.update { it.copy(storage = mode) } },
                        modifier = Modifier.testTag("settings-storage-${mode.key}"),
                    )
                    Column {
                        Text(storageLabel(mode), style = MaterialTheme.typography.bodyMedium)
                        Text(
                            storageDetail(mode, settings.hideFromGallery),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Hide from gallery", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Save into \".Hillview\" instead of \"Hillview\"",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = settings.hideFromGallery,
                onCheckedChange = { on -> repository.update { it.copy(hideFromGallery = on) } },
                modifier = Modifier.testTag("settings-hide-from-gallery"),
            )
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Landscape compass workaround", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Negate the heading when face-down in landscape " +
                        "(device quirk; found on an Armor 22)",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = compass.landscapeWorkaround,
                onCheckedChange = { on ->
                    compassRepository.update { it.copy(landscapeWorkaround = on) }
                },
                modifier = Modifier.testTag("settings-landscape-workaround"),
            )
        }
    }
}

private fun storageLabel(mode: StorageMode) = when (mode) {
    StorageMode.PublicFolder -> "Public folder"
    StorageMode.PrivateFolder -> "App-private folder"
    StorageMode.MediaStore -> "Gallery (MediaStore)"
}

private fun storageDetail(mode: StorageMode, hideFromGallery: Boolean): String {
    val folder = if (hideFromGallery) ".Hillview" else "Hillview"
    return when (mode) {
        StorageMode.PublicFolder -> "DCIM/$folder — survives uninstall"
        StorageMode.PrivateFolder -> "Android/data/…/Pictures/$folder — removed on uninstall"
        StorageMode.MediaStore -> "DCIM/$folder via MediaStore — no storage permission"
    }
}
