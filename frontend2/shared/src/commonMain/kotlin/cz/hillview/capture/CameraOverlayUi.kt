package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import cz.hillview.map.BearingMode
import kotlinx.coroutines.delay

/**
 * The glass info panel over the camera preview, ported from
 * CameraOverlay.svelte — see docs/tauri-capture-ui-contract.md.
 *
 * Tapping it cycles the backdrop through the original's six levels
 * ([nextOverlayOpacity]); the rows stay readable at every level, the cycle
 * only trades legibility against how much preview the glass eats.
 */
@Composable
fun CameraOverlayUi(
    state: CaptureState,
    bearingMode: BearingMode,
    /** The claimed manual position, when it is what captures will record. */
    overridePosition: ManualLocation?,
    opacityLevel: Int,
    onCycleOpacity: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // The post-open hint: 4 s from the camera coming ready, as the
    // original fires doCalibrationHint right after the stream starts.
    var showHint by remember { mutableStateOf(false) }
    LaunchedEffect(state.ready) {
        if (state.ready) {
            showHint = true
            delay(4_000)
            showHint = false
        }
    }

    // The original's six backdrop levels (white tint + border alpha).
    val tint = when (opacityLevel.coerceIn(0, 5)) {
        0 -> 0f
        1 -> 0.15f
        2 -> 0.31f
        3 -> 0.45f
        4 -> 0.60f
        else -> 0.75f
    }

    Column(
        modifier = modifier
            .let {
                if (tint > 0f) {
                    it
                        .background(Color.White.copy(alpha = tint), RoundedCornerShape(8.dp))
                        .border(
                            1.dp,
                            Color.White.copy(alpha = (tint / 2f).coerceAtMost(0.2f)),
                            RoundedCornerShape(8.dp),
                        )
                } else {
                    it
                }
            }
            .clickable(onClick = onCycleOpacity)
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .testTag("location-overlay"),
    ) {
        when {
            showHint -> HintContent(bearingMode)
            else -> LocationRows(state, overridePosition)
        }
    }
}

@Composable
private fun HintContent(bearingMode: BearingMode) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.testTag("calibration-hint"),
    ) {
        if (bearingMode == BearingMode.Walking) {
            CalibrationFigure(Modifier.size(width = 72.dp, height = 44.dp))
        }
        Column(Modifier.padding(start = 8.dp)) {
            if (bearingMode == BearingMode.Car) {
                MonoText("• Adjust the bearing arrow.")
            } else {
                MonoText("• Calibrate compass.")
                MonoText("• Verify orientation.")
            }
            MonoText("• Verify location.")
        }
    }
}

@Composable
private fun LocationRows(state: CaptureState, overridePosition: ManualLocation?) {
    // The effective capture position — the honesty note in the contract:
    // Tauri shows its pairing position (map state); here that is the
    // claimed manual position when it wins, else the fix.
    val lat = overridePosition?.latitude ?: state.fixLatitude
    val lon = overridePosition?.longitude ?: state.fixLongitude

    // The stale-fix warning, in the overlay's ⚠️ slot: a capture right now
    // would stamp the photo with this aging fix (the original stamps
    // silently, however old). Ticks once a second so the age is live.
    var nowMs by remember { mutableStateOf(cz.hillview.core.nowMs()) }
    LaunchedEffect(state.fixAtMs) {
        while (true) {
            nowMs = cz.hillview.core.nowMs()
            delay(1_000)
        }
    }
    if (staleFixWarning(state.fixAtMs, nowMs, manualAvailable = overridePosition != null)) {
        MonoText(
            "⚠️ GPS stale — photos would use a fix " +
                "${(nowMs - (state.fixAtMs ?: nowMs)) / 1000}s old",
            Modifier.testTag("stale-fix-warning"),
        )
    }

    if (lat == null || lon == null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(
                modifier = Modifier.size(12.dp),
                strokeWidth = 2.dp,
            )
            MonoText("Getting location...", Modifier.padding(start = 6.dp))
        }
        return
    }

    Row {
        state.bearingDeg?.let { bearing ->
            MonoText("🧭 ${oneDp(bearing.toDouble())}°")
            androidx.compose.foundation.layout.Spacer(Modifier.width(8.dp))
        }
        MonoText("📍 ${sixDp(lat)}°, ${sixDp(lon)}°")
    }
    if (overridePosition == null) {
        state.fixAltitude?.let { MonoText("⛰️ ${oneDp(it)}m") }
        state.fixAccuracyM?.let { MonoText("🎯 ±${it.toInt()}m") }
    } else {
        // A claimed position has no altitude and no accuracy to show —
        // it is where the user says they are, not a measurement.
        MonoText("(map position)")
    }
}

@Composable
private fun MonoText(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        fontFamily = FontFamily.Monospace,
        style = MaterialTheme.typography.bodySmall,
        color = Color.Black.copy(alpha = 0.85f),
        modifier = modifier,
    )
}

private fun sixDp(v: Double): String = fmtDecimals(v, 6)
private fun oneDp(v: Double): String = fmtDecimals(v, 1)

/** toFixed(n), without java.lang.String.format (this is commonMain). */
internal fun fmtDecimals(v: Double, decimals: Int): String {
    var scale = 1L
    repeat(decimals) { scale *= 10 }
    val scaled = kotlin.math.round(v * scale).toLong()
    val sign = if (scaled < 0) "-" else ""
    val abs = kotlin.math.abs(scaled)
    val whole = abs / scale
    val frac = (abs % scale).toString().padStart(decimals, '0')
    return "$sign$whole.$frac"
}
