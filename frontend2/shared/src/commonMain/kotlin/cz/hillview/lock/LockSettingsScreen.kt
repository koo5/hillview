package cz.hillview.lock

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
import androidx.compose.ui.unit.dp
import cz.hillview.settings.MapSettingsRepository
import kotlin.math.roundToInt

/**
 * The lock's own settings page, because every one of these is a trade the
 * user has to make against their own hardware and habits (user, 2026-09-11:
 * "let's have a dedicated settings screen for all this where users can
 * experiment with toggling it").
 */
@Composable
fun LockSettingsScreen(
    onBack: () -> Unit,
    repository: MapSettingsRepository = org.koin.compose.koinInject(),
) {
    val settings by repository.settings.collectAsState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("lock-settings-screen"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        TextButton(onClick = onBack, modifier = Modifier.testTag("lock-settings-back")) {
            Text("← Back")
        }
        Text("Lock controls", style = MaterialTheme.typography.headlineSmall)
        Text(
            "For shooting an interval run from a pocket. Locking covers the " +
                "whole screen: nothing responds but the unlock slider. The " +
                "screen is kept awake whatever else you choose here — the " +
                "camera is released when the display sleeps, which would end " +
                "the run.",
            style = MaterialTheme.typography.bodySmall,
        )

        SettingRow(
            title = "Dim the screen",
            explanation = "The display has to stay on, but it does not have to be " +
                "bright. A lit screen in a pocket is most of what the run costs " +
                "in battery and heat.",
            checked = settings.lockDimScreen,
            tag = "lock-dim-screen",
            onChange = { on -> repository.update { it.copy(lockDimScreen = on) } },
        )
        if (settings.lockDimScreen) {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    "Brightness while locked: " +
                        if (settings.lockBrightness <= 0f) {
                            "as dark as the panel goes"
                        } else {
                            "${(settings.lockBrightness * 100).roundToInt()}%"
                        },
                    style = MaterialTheme.typography.bodySmall,
                )
                Slider(
                    value = settings.lockBrightness,
                    onValueChange = { v -> repository.update { it.copy(lockBrightness = v) } },
                    valueRange = 0f..1f,
                    modifier = Modifier.testTag("lock-brightness-slider"),
                )
            }
        }

        SettingRow(
            title = "Black theme while locked",
            explanation = "Free on an AMOLED, where a black pixel draws no power. " +
                "On an ordinary LCD the backlight is on regardless, so this only " +
                "makes the screen harder to read on the way back in.",
            checked = settings.lockDarkTheme,
            tag = "lock-dark-theme",
            onChange = { on -> repository.update { it.copy(lockDarkTheme = on) } },
        )

        SettingRow(
            title = "Hide the system bars",
            explanation = "The status and navigation bars go away, and the first " +
                "stray edge swipe brings them back instead of acting on them.",
            checked = settings.lockHideSystemBars,
            tag = "lock-hide-system-bars",
            onChange = { on -> repository.update { it.copy(lockHideSystemBars = on) } },
        )

        SettingRow(
            title = "Pin the screen",
            explanation = "Android's own screen pinning — the only thing that stops " +
                "home and recents, which nothing this app draws can reach. The " +
                "system asks before it starts, and some phones refuse it outright " +
                "unless app pinning is switched on in their settings.",
            checked = settings.lockPinScreen,
            tag = "lock-pin-screen",
            onChange = { on -> repository.update { it.copy(lockPinScreen = on) } },
        )

        // The seam for the version that makes the lock unnecessary. Not a
        // setting yet, because nothing behind it works: the run would have to
        // own a foreground service's lifetime instead of the activity's.
        Text(
            "Shooting with the screen off is not offered yet. It needs the run " +
                "to outlive the screen, which means moving it off the activity " +
                "and onto a service of its own.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SettingRow(
    title: String,
    explanation: String,
    checked: Boolean,
    tag: String,
    onChange: (Boolean) -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            Text(explanation, style = MaterialTheme.typography.bodySmall)
        }
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            modifier = Modifier.testTag(tag),
        )
    }
}
