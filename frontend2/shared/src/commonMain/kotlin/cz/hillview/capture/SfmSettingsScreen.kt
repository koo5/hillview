package cz.hillview.capture

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
import cz.hillview.settings.SFM_HEARTBEAT_MS_RANGE
import cz.hillview.settings.SFM_METRES_RANGE
import cz.hillview.settings.SFM_MIN_GAP_MS_RANGE
import cz.hillview.settings.SFM_TURN_DEG_RANGE
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/**
 * The SfM run's page: whether the ladder offers it at all, and what paces it
 * (user, 2026-11-05: "lets make it all opt-in and configurable"). Every
 * number here is a guess until a field run says otherwise, which is why each
 * one says what it is for.
 */
@Composable
fun SfmSettingsScreen(
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
            .testTag("sfm-settings-screen"),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        TextButton(onClick = onBack, modifier = Modifier.testTag("sfm-settings-back")) {
            Text("← Back")
        }
        Text("SfM run", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Stills for 3-D reconstruction, spaced by how much new view there " +
                "is rather than by the clock: a shot each time you have moved or " +
                "turned far enough since the last one. Between an interval run and " +
                "video — dense enough that each photo overlaps the next, without " +
                "filling the run with copies while you stand still.",
            style = MaterialTheme.typography.bodySmall,
        )

        SwitchRow(
            title = "Offer the SfM run",
            explanation = "Adds an SfM rung to the shutter's ladder, just under VIDEO. " +
                "Off, the ladder is as it was.",
            checked = settings.sfmRunEnabled,
            tag = "sfm-enabled",
            onChange = { on -> repository.update { it.copy(sfmRunEnabled = on) } },
        )
        if (!settings.sfmRunEnabled) return@Column

        SwitchRow(
            title = "Shoot on distance",
            explanation = "Distance comes from the GPS receiver's own speed. Without " +
                "a speed (indoors, a weak fix) it counts as standing still.",
            checked = settings.sfmDistanceOn,
            tag = "sfm-distance-on",
            onChange = { on -> repository.update { it.copy(sfmDistanceOn = on) } },
        )
        if (settings.sfmDistanceOn) {
            ValueSlider(
                label = "Every ${formatMetres(settings.sfmMetres)}",
                value = settings.sfmMetres,
                range = SFM_METRES_RANGE,
                tag = "sfm-metres-slider",
                onChange = { v ->
                    repository.update { it.copy(sfmMetres = (v * 10).roundToInt() / 10f) }
                },
            )
        }

        SwitchRow(
            title = "Shoot on turning",
            explanation = "How far the lens may turn between shots. Needs compass " +
                "tracking on — the phone's orientation is only recorded then.",
            checked = settings.sfmTurnOn,
            tag = "sfm-turn-on",
            onChange = { on -> repository.update { it.copy(sfmTurnOn = on) } },
        )
        if (settings.sfmTurnOn) {
            ValueSlider(
                label = "Every ${settings.sfmTurnDeg.roundToInt()}°",
                value = settings.sfmTurnDeg,
                range = SFM_TURN_DEG_RANGE,
                tag = "sfm-turn-slider",
                onChange = { v -> repository.update { it.copy(sfmTurnDeg = v.roundToInt().toFloat()) } },
            )
        }

        SwitchRow(
            title = "Heartbeat",
            explanation = "A shot anyway after this long without one, so losing both " +
                "signals does not stop the run.",
            checked = settings.sfmHeartbeatOn,
            tag = "sfm-heartbeat-on",
            onChange = { on -> repository.update { it.copy(sfmHeartbeatOn = on) } },
        )
        if (settings.sfmHeartbeatOn) {
            ValueSlider(
                label = "After ${settings.sfmHeartbeatMs / 1000} s",
                value = settings.sfmHeartbeatMs.toFloat(),
                range = SFM_HEARTBEAT_MS_RANGE.first.toFloat()..SFM_HEARTBEAT_MS_RANGE.last.toFloat(),
                tag = "sfm-heartbeat-slider",
                onChange = { v ->
                    repository.update { it.copy(sfmHeartbeatMs = (v / 1000f).roundToLong() * 1000L) }
                },
            )
        }

        ValueSlider(
            label = "Never sooner than ${settings.sfmMinGapMs} ms apart",
            value = settings.sfmMinGapMs.toFloat(),
            range = SFM_MIN_GAP_MS_RANGE.first.toFloat()..SFM_MIN_GAP_MS_RANGE.last.toFloat(),
            tag = "sfm-min-gap-slider",
            onChange = { v -> repository.update { it.copy(sfmMinGapMs = (v / 50f).roundToLong() * 50L) } },
        )

        if (!settings.sfmDistanceOn && !settings.sfmTurnOn && !settings.sfmHeartbeatOn) {
            Text(
                "With all three off, a run takes its first photo and then waits forever.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag("sfm-nothing-paces"),
            )
        }
    }
}

/** "1.5 m", "0.3 m", "10 m" — one decimal, none when whole. */
internal fun formatMetres(m: Float): String {
    val tenths = (m * 10).roundToInt()
    return if (tenths % 10 == 0) "${tenths / 10} m" else "${tenths / 10}.${tenths % 10} m"
}

@Composable
private fun SwitchRow(
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
        Switch(checked = checked, onCheckedChange = onChange, modifier = Modifier.testTag(tag))
    }
}

@Composable
private fun ValueSlider(
    label: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    tag: String,
    onChange: (Float) -> Unit,
) {
    Column(Modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.bodySmall)
        Slider(
            value = value.coerceIn(range),
            onValueChange = onChange,
            valueRange = range,
            modifier = Modifier.testTag(tag),
        )
    }
}
