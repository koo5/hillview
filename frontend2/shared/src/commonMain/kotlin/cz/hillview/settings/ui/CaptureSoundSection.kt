package cz.hillview.settings.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import cz.hillview.capture.CaptureCue
import cz.hillview.capture.CaptureSoundPreview
import cz.hillview.capture.rememberCaptureSoundPreview
import cz.hillview.settings.ShutterSound
import cz.hillview.settings.SoundChannel
import cz.hillview.settings.UploadSettingsRepository
import kotlin.math.roundToInt

/**
 * Capture sound: what a shot sounds like, and which volume control governs
 * it (user, 2026-11-07: the click played "even with all channels apparently
 * off, and on another device it's the ring volume… pretty random").
 *
 * [preview] is the platform's player and law check; null (desktop, tests)
 * hides the test buttons.
 */
@Composable
fun CaptureSoundSection(
    repository: UploadSettingsRepository,
    preview: CaptureSoundPreview? = rememberCaptureSoundPreview(),
) {
    val settings by repository.settings.collectAsState()
    val anySound = settings.shutterSound != ShutterSound.Off || settings.warnDegradedPosition
    val required = preview?.shutterSoundRequiredByLaw == true

    Column(
        verticalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.testTag("settings-capture-sound"),
    ) {
        Text("Capture sound", style = MaterialTheme.typography.bodyLarge)
        Text(
            "Both sounds play on the volume you pick below, so one control " +
                "turns them up, down or off.",
            style = MaterialTheme.typography.bodySmall,
        )
        if (required) {
            Text(
                "This phone must play a shutter sound by law where it is sold. " +
                    "The system click plays on every photo whatever is set here; " +
                    "the warning still follows these settings.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("settings-shutter-sound-required"),
            )
        }

        Text("Shutter", style = MaterialTheme.typography.bodyMedium)
        Column(Modifier.selectableGroup()) {
            ShutterSound.entries.forEach { sound ->
                RadioRow(
                    label = sound.label,
                    selected = settings.shutterSound == sound,
                    tag = "settings-shutter-sound-${sound.key}",
                    onSelect = { repository.update { it.copy(shutterSound = sound) } },
                )
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.weight(1f)) {
                Text("Warn when the position is degraded", style = MaterialTheme.typography.bodyMedium)
                Text(
                    "A double beep instead of the shutter sound when the photo's " +
                        "position is not a fresh GPS fix. Plays even with the shutter off: " +
                        "it is for interval runs in a pocket, where the screen can't warn you.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Switch(
                checked = settings.warnDegradedPosition,
                onCheckedChange = { on -> repository.update { it.copy(warnDegradedPosition = on) } },
                modifier = Modifier.testTag("settings-warn-degraded-position"),
            )
        }

        // With nothing to play, where and how loud is moot.
        if (!anySound) return@Column

        Text("Volume control", style = MaterialTheme.typography.bodyMedium)
        Column(Modifier.selectableGroup()) {
            SoundChannel.entries.forEach { channel ->
                RadioRow(
                    label = channel.label,
                    explanation = channel.explanation,
                    selected = settings.captureSoundChannel == channel,
                    tag = "settings-capture-sound-channel-${channel.key}",
                    onSelect = { repository.update { it.copy(captureSoundChannel = channel) } },
                )
            }
        }

        Text(
            "Loudness: ${(settings.captureSoundVolume * 100).roundToInt()} % of that volume",
            style = MaterialTheme.typography.bodyMedium,
        )
        Slider(
            value = settings.captureSoundVolume,
            onValueChange = { v -> repository.update { it.copy(captureSoundVolume = v.coerceIn(0f, 1f)) } },
            valueRange = 0f..1f,
            modifier = Modifier.fillMaxWidth().testTag("settings-capture-sound-volume"),
        )

        if (preview != null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val shutterCue = when (settings.shutterSound) {
                    ShutterSound.Click -> CaptureCue.Click
                    ShutterSound.Beep -> CaptureCue.Beep
                    ShutterSound.Off -> null
                }
                if (shutterCue != null) {
                    TextButton(
                        onClick = {
                            preview.play(shutterCue, settings.captureSoundChannel, settings.captureSoundVolume)
                        },
                        modifier = Modifier.testTag("settings-capture-sound-test-shutter"),
                    ) { Text("Test shutter") }
                }
                if (settings.warnDegradedPosition) {
                    TextButton(
                        onClick = {
                            preview.play(CaptureCue.Warning, settings.captureSoundChannel, settings.captureSoundVolume)
                        },
                        modifier = Modifier.testTag("settings-capture-sound-test-warning"),
                    ) { Text("Test warning") }
                }
            }
        }
    }
}

@Composable
private fun RadioRow(
    label: String,
    selected: Boolean,
    tag: String,
    onSelect: () -> Unit,
    explanation: String? = null,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .selectable(selected = selected, onClick = onSelect, role = Role.RadioButton)
            .testTag(tag),
    ) {
        RadioButton(selected = selected, onClick = null)
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            if (explanation != null) {
                Text(explanation, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
