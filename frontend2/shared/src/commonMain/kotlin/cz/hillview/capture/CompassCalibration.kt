package cz.hillview.capture

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import cz.hillview.map.BearingMode
import kotlinx.coroutines.delay

/**
 * The calibration trigger, from the Tauri app's hints.svelte.ts: only in
 * walking mode (car mode takes its bearing from GPS travel, the
 * magnetometer is irrelevant there), and only when the magnetometer's
 * Android accuracy status is known and below HIGH (3).
 */
fun needsCompassCalibration(walkingMode: Boolean, accuracyLevel: Int?): Boolean =
    walkingMode && accuracyLevel != null && accuracyLevel >= 0 && accuracyLevel != 3

/** Android's 0-3 magnetometer scale, worded as the original words it. */
fun compassAccuracyLabel(accuracyLevel: Int?): String = when (accuracyLevel) {
    3 -> "HIGH"
    2 -> "MEDIUM"
    1 -> "LOW"
    0 -> "UNRELIABLE"
    else -> "UNKNOWN"
}

private fun accuracyColor(accuracyLevel: Int?): Color = when (accuracyLevel) {
    3 -> Color(0xFF2EA043)
    2 -> Color(0xFFD4A017)
    1, 0 -> Color(0xFFD93025)
    else -> Color.Gray
}

/**
 * The figure-8 the user is asked to trace, a dot riding the same lemniscate
 * the Tauri SVG animates (same path, 3 s loop).
 */
@Composable
fun CalibrationFigure(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition()
    val progress by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(durationMillis = 3_000, easing = LinearEasing)),
    )

    Canvas(modifier) {
        // The SVG path from CalibrationFigure.svelte, in its 100x60 viewBox.
        val sx = size.width / 100f
        val sy = size.height / 60f
        val path = Path().apply {
            moveTo(50f * sx, 30f * sy)
            cubicTo(50f * sx, 10f * sy, 80f * sx, 10f * sy, 80f * sx, 30f * sy)
            cubicTo(80f * sx, 50f * sy, 50f * sx, 50f * sy, 50f * sx, 30f * sy)
            cubicTo(50f * sx, 10f * sy, 20f * sx, 10f * sy, 20f * sx, 30f * sy)
            cubicTo(20f * sx, 50f * sy, 50f * sx, 50f * sy, 50f * sx, 30f * sy)
        }
        drawPath(path, Color.White.copy(alpha = 0.4f), style = Stroke(width = 2f * sx))

        val measure = PathMeasure().apply { setPath(path, forceClosed = false) }
        val at = measure.getPosition(progress * measure.length)
        drawCircle(Color(0xFF4A90E2), radius = 4f * sx, center = at)
    }
}

/**
 * The full-screen calibration sheet, ported from CompassCalibration.svelte:
 * figure-8 + instruction, a live accuracy readout, an escape hatch for
 * people who are actually in a car, and auto-dismiss 1.5 s after the
 * accuracy comes good (immediately if walking mode stops being the case).
 */
@Composable
fun CompassCalibrationOverlay(
    accuracyLevel: Int?,
    walkingMode: Boolean,
    onSwitchToCarMode: () -> Unit,
    onClose: () -> Unit,
) {
    val needed = needsCompassCalibration(walkingMode, accuracyLevel)

    LaunchedEffect(needed, walkingMode) {
        if (!needed) {
            delay(if (walkingMode) 1_500 else 0)
            onClose()
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0xE6000000))
            .testTag("compass-calibration-overlay"),
    ) {
        TextButton(
            onClick = onClose,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(8.dp)
                .testTag("calibration-close-btn"),
        ) { Text("×", color = Color.White, style = MaterialTheme.typography.headlineMedium) }

        Column(
            modifier = Modifier.align(Alignment.Center).padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                "Calibrate Compass",
                color = Color.White,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )

            Row(verticalAlignment = Alignment.CenterVertically) {
                CalibrationFigure(Modifier.size(width = 120.dp, height = 72.dp))
                Text(
                    "Move your phone in a figure-8 pattern several times",
                    color = Color.White,
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(start = 16.dp),
                )
            }

            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    "Compass Accuracy",
                    color = Color.White.copy(alpha = 0.7f),
                    style = MaterialTheme.typography.bodySmall,
                )
                Text(
                    compassAccuracyLabel(accuracyLevel),
                    color = accuracyColor(accuracyLevel),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.testTag("calibration-accuracy"),
                )
                if (!needed) {
                    Text(
                        if (accuracyLevel == 3) "Accuracy is good! Closing soon…" else "Closing soon…",
                        color = Color(0xFF2EA043),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            // The Tauri sheet teaches the long-press-for-modes gesture here;
            // this port offers the outcome directly.
            TextButton(
                onClick = onSwitchToCarMode,
                modifier = Modifier.testTag("switch-to-car-mode-btn"),
            ) {
                Text(
                    "In a vehicle? Switch to car mode →",
                    color = Color(0xFF4A90E2),
                )
            }
        }
    }
}
