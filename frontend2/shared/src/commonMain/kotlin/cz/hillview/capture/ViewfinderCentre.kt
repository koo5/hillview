package cz.hillview.capture

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** The reticle's overall extent — the outer end of the longest tick, doubled. */
internal val VIEWFINDER_CENTRE_SIZE = 40.dp

/**
 * How much of the half-extent is left EMPTY around the exact centre, as a fraction.
 * The point of aim must stay visible: a solid cross would hide the very thing being
 * aimed at, which for a distant landmark is a few pixels wide.
 */
internal const val VIEWFINDER_CENTRE_GAP = 0.3f

/**
 * WHERE THE LENS POINTS, marked on the preview.
 *
 * A photo's `bearing` and `attitude.pitch_deg` are the direction of the OPTICAL AXIS —
 * the centre of the frame — so without a centre mark the stamp refers to a point the
 * person framing the shot cannot see. That is reason enough on its own, and it is also
 * what makes a bearing measurement possible at all: centre a distant landmark and the
 * true bearing is known independently of every sensor in the phone, which is the ground
 * truth docs/todo/roll-skews-the-bearing.md needs and could not otherwise get from a
 * hand-held sweep.
 *
 * THE CENTRE IS EXACT, and specifically it is the one point that can be. The preview is
 * `FIT_CENTER` (see PhotoCapture.android.kt — deliberately, so the pane shows everything
 * the sensor sees), so the preview rectangle is centred in this pane with letterbox bars
 * on two sides. Under any CENTRED scale or crop the centre is a fixed point, and nothing
 * else is: a rule-of-thirds line or a corner would land somewhere different in the saved
 * photo than it appears here. So this draws the centre and makes no other claim about
 * the frame.
 *
 * Four ticks rather than a cross, with a gap in the middle, and each stroke drawn twice —
 * a wider dark pass under a narrower light one. A camera points at bright sky as readily
 * as at dark ground, and a single-colour overlay disappears into one of them.
 */
@Composable
fun ViewfinderCentre(modifier: Modifier = Modifier) {
    Box(modifier.size(VIEWFINDER_CENTRE_SIZE).testTag("viewfinder-centre")) {
        Canvas(Modifier.size(VIEWFINDER_CENTRE_SIZE)) {
            val c = Offset(size.width / 2f, size.height / 2f)
            val half = size.minDimension / 2f
            val inner = half * VIEWFINDER_CENTRE_GAP
            val ticks = listOf(
                Offset(-1f, 0f), Offset(1f, 0f),
                Offset(0f, -1f), Offset(0f, 1f),
            )
            // Dark first, wider: it becomes the outline of the light pass over it, which
            // is what keeps the mark readable against a blown-out sky.
            for ((width, colour) in listOf(
                3.5.dp.toPx() to Color.Black.copy(alpha = 0.45f),
                1.5.dp.toPx() to Color.White.copy(alpha = 0.9f),
            )) {
                for (dir in ticks) {
                    drawLine(
                        color = colour,
                        start = c + Offset(dir.x * inner, dir.y * inner),
                        end = c + Offset(dir.x * half, dir.y * half),
                        strokeWidth = width,
                        cap = StrokeCap.Round,
                    )
                }
                // A dot AT the centre, small enough to aim past. Without it the gap has
                // no centre of its own and the eye has to bisect four ticks.
                drawCircle(color = colour, radius = width / 2f, center = c)
            }
        }
    }
}
