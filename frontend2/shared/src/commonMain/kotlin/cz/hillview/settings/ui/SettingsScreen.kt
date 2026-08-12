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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.core.permissions.rememberNotificationPermissionRequester
import cz.hillview.settings.ALLOWED_LICENSES
import cz.hillview.settings.GPS_INTERVAL_CHOICES_MS
import cz.hillview.settings.formatGpsInterval
import cz.hillview.settings.exportGeoTrackingNow
import cz.hillview.settings.geoAutoExportEnabled
import cz.hillview.settings.setGeoAutoExport
import cz.hillview.settings.CompassSettingsRepository
import cz.hillview.settings.StorageMode
import cz.hillview.settings.storageFacts
import cz.hillview.settings.storageFolderName
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
    onOpenLogin: () -> Unit = {},
    repository: UploadSettingsRepository = koinInject(),
    compassRepository: CompassSettingsRepository = koinInject(),
    mapRepository: cz.hillview.settings.MapSettingsRepository = koinInject(),
    sessionManager: cz.hillview.auth.SessionManager = koinInject(),
) {
    val settings by repository.settings.collectAsState()
    val compass by compassRepository.settings.collectAsState()
    val mapSettings by mapRepository.settings.collectAsState()
    val sessionState by sessionManager.state.collectAsState()
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

        // The field edits RAW text (normalizing per keystroke would fight
        // the cursor); the persisted setting is normalized — trimmed, no
        // trailing slash (a stored slash doubles up in every "$url/path").
        var serverUrlText by rememberSaveable { mutableStateOf(settings.serverUrl) }
        OutlinedTextField(
            value = serverUrlText,
            onValueChange = { url ->
                serverUrlText = url
                repository.update { it.copy(serverUrl = url.trim().trimEnd('/')) }
            },
            label = { Text("API URL") },
            supportingText = { Text("Full API URL incl. /api — applies after an app restart") },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("settings-server-url"),
        )

        // The setting vs the RUNTIME: deliberately separate values. Auth,
        // the upload workers, and every cached client resolved the runtime
        // URL at startup; the only sanctioned way to move them all is a
        // full restart — a live switch leaves components talking to
        // different servers (the stranded-client-key incident).
        val runtimeConfig: cz.hillview.core.net.BackendConfig = koinInject()
        if (settings.serverUrl.trimEnd('/') != runtimeConfig.apiUrl.trimEnd('/')) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("settings-restart-required"),
            ) {
                Text(
                    "Server URL changed — the app must restart to apply it everywhere.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = { cz.hillview.core.restartApp() },
                    modifier = Modifier.testTag("restart-app-button"),
                ) { Text("Restart now") }
            }
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Auto-upload", style = MaterialTheme.typography.bodyLarge)
                Text(
                    if (settings.license == null) {
                        "Pick an upload license below first"
                    } else {
                        "Upload captures in the background"
                    },
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
                // Inert until the licence is accepted: turning this on is an
                // agreement to publish under it, so there must be a licence
                // to agree to. The shared upload stack enforces the same
                // null-check server-side of this switch.
                enabled = settings.license != null,
                modifier = Modifier.testTag("settings-auto-upload"),
            )
        }

        // Geo tracking export: the CSVs that let photos be stamped
        // retroactively as if taken in the moment (the effective stream
        // samples the same arbitration the shutter runs). Auto-export
        // dumps at each capture-session end; the button dumps right now.
        var geoAutoExport by rememberSaveable { mutableStateOf(geoAutoExportEnabled()) }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.weight(1f)) {
                Text("Tracking CSV export", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Bearings and locations → GeoTrackingDumps/",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            TextButton(
                onClick = { exportGeoTrackingNow() },
                modifier = Modifier.testTag("settings-geo-export-now"),
            ) { Text("Export now") }
            Switch(
                checked = geoAutoExport,
                onCheckedChange = { on ->
                    geoAutoExport = on
                    setGeoAutoExport(on)
                },
                modifier = Modifier.testTag("settings-geo-auto-export"),
            )
        }

        // How often the fused provider is asked for a fix. The value goes
        // straight through BindGeoToActivity into the GeoEngine — one of the
        // two knobs that decide what tracking costs — but it is also the
        // RESOLUTION of every stamp downstream, so the trade is stated
        // rather than left for the battery graph to reveal.
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("GPS fix interval", style = MaterialTheme.typography.bodyLarge)
            Text(
                "How often position is sampled. Longer saves power; it also " +
                    "coarsens photo stamps, which are only as fresh as the " +
                    "last fix (and are interpolated between fixes).",
                style = MaterialTheme.typography.bodySmall,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                GPS_INTERVAL_CHOICES_MS.forEach { ms ->
                    val selected = mapSettings.gpsIntervalMs == ms
                    TextButton(
                        onClick = { mapRepository.update { it.copy(gpsIntervalMs = ms) } },
                        modifier = Modifier.testTag("settings-gps-interval-$ms"),
                    ) {
                        Text(
                            formatGpsInterval(ms),
                            color = if (selected) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                            style = if (selected) {
                                MaterialTheme.typography.bodyLarge
                            } else {
                                MaterialTheme.typography.bodyMedium
                            },
                        )
                    }
                }
            }
        }

        // Uploads are impossible logged out, and this section is where a
        // user chasing the auto-upload prompt lands — so the way in sits
        // right here. (A frontend2 addition: the original's upload settings
        // page has no login affordance.)
        if (sessionState !is cz.hillview.auth.SessionState.LoggedIn) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    "Uploading needs an account.",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = onOpenLogin,
                    modifier = Modifier.testTag("settings-login-button"),
                ) { Text("Sign in") }
            }
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
            if (settings.license == null) {
                Text(
                    "Not accepted — uploads stay on this device until you pick one.",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag("settings-license-unset"),
                )
            }
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
                    "Save into \"${storageFolderName(true)}\" instead of " +
                        "\"${storageFolderName(false)}\"",
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
                Text("Write EXIF into photo files", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "For using the files outside Hillview (GPS, heading, provenance " +
                        "tags). Slower per shot — each photo is rewritten whole. " +
                        "Uploads carry the full stamp either way.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = settings.writeExif,
                onCheckedChange = { on -> repository.update { it.copy(writeExif = on) } },
                modifier = Modifier.testTag("settings-write-exif"),
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
    val folder = storageFolderName(hideFromGallery)
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
