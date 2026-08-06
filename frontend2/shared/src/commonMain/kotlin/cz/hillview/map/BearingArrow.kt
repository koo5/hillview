package cz.hillview.map

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * The bearing arrow, ported from BearingStateArrow.svelte (see
 * docs/tauri-map-ui-contract.md). Colours, proportions and — importantly —
 * the hit areas match: the grabbable part is the OUTER THIRD of the arrow,
 * or a ring along the range circle in car mode, where
 *
 *   "a jump on first touch would swing the mount offset by however far from
 *    the arrow the grab happened to land"
 *
 * so car mode reports the angle the pointer *travelled* instead of the angle
 * it landed on.
 *
 * @param tipRadiusPx how far the tip sits from centre; the caller projects
 *   the range circle edge along the bearing so the arrow always touches it.
 * @param onBearing absolute bearing under the pointer (walking).
 * @param onBearingDelta angle travelled since the last event (car).
 */
@Composable
fun BearingArrow(
    bearingDeg: Double,
    fullCircleHitArea: Boolean,
    tipRadiusPx: Float,
    onDragStart: () -> Unit,
    onBearing: (Double) -> Unit,
    onBearingDelta: (Double) -> Unit,
    modifier: Modifier = Modifier,
) {
    val arrowBlue = Color(0xFF0405FA)
    val centreRed = Color(0xFFFA0000)

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .testTag("map-bearing-arrow")
            // The web app publishes the bearing as aria-valuenow on the
            // arrow's hit area — the only externally readable bearing in the
            // app, and what its tests assert against. Same idea here, so the
            // value is available to accessibility services and UI tests.
            .semantics {
                progressBarRangeInfo = ProgressBarRangeInfo(
                    current = bearingDeg.toFloat(),
                    range = 0f..360f,
                )
                contentDescription = "Bearing ${bearingDeg.toInt()} degrees"
            }
            .pointerInput(fullCircleHitArea, tipRadiusPx) {
                val centre = Offset(size.width / 2f, size.height / 2f)

                fun pointerBearing(p: Offset): Double {
                    val dx = p.x - centre.x
                    val dy = p.y - centre.y
                    return normalizeBearing(Math.toDegrees(atan2(dx, -dy).toDouble()))
                }

                // Outer third of the arrow (the Svelte hit line starts at
                // 1.8/3 of the way out and is 30px wide); in car mode the
                // whole ring, 36px wide.
                fun grabbable(p: Offset): Boolean {
                    val d = hypot(p.x - centre.x, p.y - centre.y)
                    return if (fullCircleHitArea) {
                        kotlin.math.abs(d - tipRadiusPx) <= 36f
                    } else {
                        d >= tipRadiusPx * 0.6f - 15f && d <= tipRadiusPx + 15f
                    }
                }

                var dragging = false
                var previous = 0.0
                detectDragGestures(
                    onDragStart = { position ->
                        dragging = grabbable(position)
                        if (dragging) {
                            onDragStart()
                            previous = pointerBearing(position)
                            if (!fullCircleHitArea) onBearing(previous)
                        }
                    },
                    onDragEnd = { dragging = false },
                    onDragCancel = { dragging = false },
                    onDrag = { change, _ ->
                        if (!dragging) return@detectDragGestures
                        change.consume()
                        val now = pointerBearing(change.position)
                        if (fullCircleHitArea) {
                            onBearingDelta(angularDistance(previous, now))
                            previous = now
                        } else {
                            onBearing(now)
                        }
                    },
                )
            },
    ) {
        val centre = Offset(size.width / 2f, size.height / 2f)
        val radians = Math.toRadians(bearingDeg)
        val tip = Offset(
            centre.x + (sin(radians) * tipRadiusPx).toFloat(),
            centre.y - (cos(radians) * tipRadiusPx).toFloat(),
        )

        // Car mode: show the ring that is grabbable, so the affordance is
        // visible rather than folklore.
        if (fullCircleHitArea) {
            drawCircle(
                color = arrowBlue.copy(alpha = 0.25f),
                radius = tipRadiusPx,
                center = centre,
                style = Stroke(width = 10f),
            )
        }

        drawLine(
            color = arrowBlue.copy(alpha = 0.5f),
            start = centre,
            end = tip,
            strokeWidth = 9f,
        )

        // Arrowhead, the SVG marker's 0 0 / 10 6 / 0 12 triangle.
        val head = 34f
        val back = Offset(
            tip.x - (sin(radians) * head).toFloat(),
            tip.y + (cos(radians) * head).toFloat(),
        )
        val perp = Offset(cos(radians).toFloat(), sin(radians).toFloat())
        drawPath(
            path = Path().apply {
                moveTo(tip.x, tip.y)
                lineTo(back.x + perp.x * head * 0.5f, back.y + perp.y * head * 0.5f)
                lineTo(back.x - perp.x * head * 0.5f, back.y - perp.y * head * 0.5f)
                close()
            },
            color = arrowBlue.copy(alpha = 0.5f),
        )

        // Centre dot: blue fill, red rim (r=3 in the original's viewBox).
        drawCircle(color = arrowBlue.copy(alpha = 0.6f), radius = 11f, center = centre)
        drawCircle(
            color = centreRed.copy(alpha = 0.5f),
            radius = 11f,
            center = centre,
            style = Stroke(width = 3f),
        )
    }
}
