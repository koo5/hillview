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
import cz.hillview.settings.storageFacts
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

        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Photo storage", style = MaterialTheme.typography.bodyLarge)
            Text(
                "If the chosen target is unavailable, the others are tried in order.",
                style = MaterialTheme.typography.bodySmall,
            )
            StorageMode.entries.forEach { mode ->
                StorageOption(
                    mode = mode,
                    selected = settings.storage == mode,
                    hideFromGallery = settings.hideFromGallery,
                    onSelect = { repository.update { it.copy(storage = mode) } },
                )
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

/**
 * One storage choice, with the three things that actually decide it: does the
 * photo show up in the gallery, can a file manager reach it, and does it
 * survive uninstalling the app.
 */
@Composable
private fun StorageOption(
    mode: StorageMode,
    selected: Boolean,
    hideFromGallery: Boolean,
    onSelect: () -> Unit,
) {
    val folder = if (hideFromGallery) ".Hillview" else "Hillview"
    // Version-dependent — asked of the platform, never assumed.
    val facts = storageFacts(mode, hideFromGallery)

    Row(
        verticalAlignment = Alignment.Top,
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 4.dp),
    ) {
        RadioButton(
            selected = selected,
            onClick = onSelect,
            enabled = facts.availableHere,
            modifier = Modifier.testTag("settings-storage-${mode.key}"),
        )
        Column(Modifier.padding(top = 12.dp)) {
            Text(
                text = when (mode) {
                    StorageMode.PublicFolder -> "DCIM/$folder"
                    StorageMode.PrivateFolder -> "App-private folder"
                    StorageMode.MediaStore -> "DCIM/$folder (via the gallery database)"
                } + if (facts.availableHere) "" else " — unavailable on this phone",
                style = MaterialTheme.typography.bodyLarge,
            )
            if (facts.availableHere) {
                Property(
                    facts.inGallery,
                    if (facts.inGallery) "Shows in the gallery" else "Hidden from the gallery",
                )
                Property(
                    facts.fileManagerReachable,
                    if (facts.fileManagerReachable) "Reachable with a file manager"
                    else "Not reachable with a file manager",
                )
                Property(
                    facts.survivesUninstall,
                    if (facts.survivesUninstall) "Kept when the app is uninstalled"
                    else "Deleted when the app is uninstalled",
                )
            }
            Text(
                text = facts.note,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
    }
}

@Composable
private fun Property(good: Boolean, text: String) {
    Text(
        text = (if (good) "✓ " else "✗ ") + text,
        style = MaterialTheme.typography.bodyMedium,
        color = if (good) {
            MaterialTheme.colorScheme.primary
        } else {
            MaterialTheme.colorScheme.onSurfaceVariant
        },
    )
}
