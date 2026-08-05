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
) {
    val settings by repository.settings.collectAsState()
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
    }
}
