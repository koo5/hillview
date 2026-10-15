package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp

/**
 * The shutter ladder — what holding the shutter and sliding up can choose.
 *
 * The original offers exactly two speeds, Turtle (10 s) and Zap (2 s), and
 * you pick one by sliding onto its button (DualCaptureButton.svelte). This
 * port keeps the gesture and replaces the pair with a scale, because the
 * useful interval depends on how fast you are moving and 2 s versus 10 s is
 * a coarse way to say that.
 *
 * The rungs are NOT evenly spaced in time, deliberately. Every second up
 * to 3 gets its own rung; above and below that, the useful differences are
 * proportional rather than absolute, so the stops thin out both ways —
 * 4, 6, 8, 10, 20, 30 above (user, 2026-10-10: "video 30 20 10 8 6 4 3
 * (the lower rest would stay as it is)"), 0.75 to 0.2 below. Until then
 * every whole second to 15 had a rung of its own, which made twenty thin
 * bands of which the upper half differed by little.
 * The top rung is VIDEO, which is where "even less than zero interval"
 * belongs. There is no rung for getting out: the bottom one read
 * "cancel" (and, before 2026-09-06, wrongly "single") until 2026-09-18,
 * when the user asked for it to go. The way out is the button's own side
 * of the pane (see [CancelZone]), and the bottom rung is the fastest
 * interval however far below the ladder the finger slides
 * ([overLadderAt]).
 */
internal sealed interface LadderRung {
    /** What the ladder band and the shutter both show. */
    val label: String

    data class Every(val ms: Int) : LadderRung {
        override val label: String get() = formatIntervalMs(ms)
    }

    data object Video : LadderRung {
        override val label = "VIDEO"
    }
}

/**
 * The whole-second rungs. The ceiling has moved twice: a 60 s top with a
 * rung per second crowded every useful value into the bottom centimetre of
 * the scale, so it came down to 15; since 2026-10-10 the rungs above 3 s
 * thin out instead, which buys 30 s back for six bands rather than fifteen
 * (the original's slow mode is 10 s).
 */
private val WHOLE_SECONDS = listOf(1, 2, 3, 4, 6, 8, 10, 20, 30)

/**
 * The sub-second rungs (user-raised, 2026-09-06: "can we try to support
 * modes faster than 1s?").
 *
 * What the phone will actually deliver is another matter: a full-resolution
 * JPEG takes a few hundred milliseconds to issue on a mid-range device, so
 * the fast end of this is a REQUEST, not a promise. The run loop is built
 * for that — it works to an absolute timeline, waits for the previous shot
 * rather than dropping the beat, and counts every late one as "interval
 * behind" in the capture stats. Asking for 0.2 s on hardware that can only
 * manage 0.4 s therefore yields "as fast as it can" plus an honest counter,
 * which is the behaviour worth having at that end of the scale.
 */
private val SUB_SECOND_MS = listOf(200, 300, 500, 750)

/** The rungs, bottom (index 0) to top. */
internal val INTERVAL_LADDER: List<LadderRung> = buildList {
    SUB_SECOND_MS.forEach { add(LadderRung.Every(it)) }
    WHOLE_SECONDS.forEach { add(LadderRung.Every(it * 1000)) }
    add(LadderRung.Video)
}

/**
 * "0.2s", "0.75s", "3s" — trailing zeros trimmed, and never a bare decimal
 * point. Written out rather than left to `Double.toString`, whose output is
 * a platform's business and not something a label should depend on.
 */
internal fun formatIntervalMs(ms: Int): String {
    val whole = ms / 1000
    val frac = ms % 1000
    if (frac == 0) return "${whole}s"
    val digits = frac.toString().padStart(3, '0').trimEnd('0')
    return "$whole.${digits}s"
}

/**
 * Which rung a finger at [y] is on, given the ladder's [top] and [bottom] in
 * the same coordinates. Index 0 is the bottom.
 *
 * FLOOR, not round: each rung owns exactly one band of the track, and the
 * band it owns is the band the ladder draws. The previous mapping rounded
 * against the number of INTERVALS, which gave the two end stops half-height
 * bands — invisible while the scale was undrawn, and a lie the moment it is.
 */
internal fun rungIndexAt(
    y: Float,
    top: Float,
    bottom: Float,
    count: Int = INTERVAL_LADDER.size,
): Int {
    if (count <= 0) return 0
    val height = bottom - top
    if (height <= 0f) return 0
    val fromBottom = (bottom - y) / height
    return (fromBottom * count).toInt().coerceIn(0, count - 1)
}

/** Where on the ladder a finger at [y] is: 0 at the bottom, 1 at the top. */
internal fun ladderFractionAt(y: Float, top: Float, bottom: Float): Float {
    val height = bottom - top
    if (height <= 0f) return 0f
    return ((bottom - y) / height).coerceIn(0f, 1f)
}

private val BandLine = Color(0x22FFFFFF)
private val BandWash = Color(0x14FFFFFF)
private val BandLabel = Color(0x8CFFFFFF)
private val HoverBand = Color(0x33FFFFFF)
private val RunBand = Color(0x664CAF50)
private val VideoBand = Color(0x66FF5252)
// A shade, not a colour: releasing here does nothing, and the zone goes
// darker rather than promising something.
private val CancelBand = Color(0x66000000)
private val PointerLine = Color(0xE6FFFFFF)
private val ValueShade = Color(0x99000000)

internal fun ladderBandColor(rung: LadderRung, selected: Boolean, armed: Boolean): Color = when {
    !selected -> Color.Transparent
    !armed -> HoverBand
    rung is LadderRung.Video -> VideoBand
    else -> RunBand
}

/**
 * Whether a held shutter released at [x] lands on the ladder: everything
 * left of the button's left edge ([buttonLeft]), at ANY height, on the pane
 * or off it. Everything else is the way out.
 *
 * Height does not enter into it, and neither do the pane's bounds — which
 * is the fix. Until 2026-10-10 the ladder ended at the pane, and leaving
 * the pane cancelled. In portrait the pane sits ABOVE the map with the
 * shutter at its foot, so the bottom rung was a band level with the thumb
 * and a slide down-left onto it overshot onto the map and cancelled
 * instead (user: "sliding to the bottom left should mean starting at the
 * lowest interval, not cancel"). Below the ladder is now the bottom rung,
 * as [rungIndexAt] already clamps it.
 */
internal fun overLadderAt(x: Float, buttonLeft: Float): Boolean = x < buttonLeft

/**
 * The other half of the catch zone: everything right of the ladder — the
 * button's own side of the pane, the button included. Releasing here does
 * NOTHING: it is the way out of the long press, and it is where the thumb
 * already is when the ladder opens, so letting go without sliding anywhere
 * changes nothing.
 *
 * History, since this side has meant three things. The original's
 * release-over-nothing cancelled (DualCaptureButton.svelte). From
 * 2026-09-18 it took ONE photo (user: "make the right side of the pane
 * show that it means capture"), and the way out moved off the pane — onto
 * the map, which in portrait is exactly where a slide to the bottom rung
 * overshoots. On 2026-10-10 the user put the cancel back here ("sliding to
 * the right side should mean basically cancel of the gesture") and the
 * ladder took the off-pane bottom ([overLadderAt]). A long press can no
 * longer end in a single photo; a tap is how one is taken.
 */
@Composable
internal fun CancelZone(armed: Boolean, modifier: Modifier = Modifier) {
    Box(
        modifier
            .background(if (armed) CancelBand else BandWash)
            .testTag("capture-cancel-zone")
            .semantics {
                stateDescription = (if (armed) "armed " else "hover ") + "cancel"
            },
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("✕", style = MaterialTheme.typography.titleMedium, color = Color.White)
            Text(
                "cancel",
                style = MaterialTheme.typography.titleMedium,
                color = Color.White,
                modifier = Modifier.testTag("capture-cancel-zone-label"),
            )
        }
    }
}

/**
 * The ladder, drawn over the shutter's catch zone.
 *
 * It IS the catch zone (everything left of the shutter, full pane height),
 * which is the whole point: the band the finger is in is the band that will
 * be chosen, at the size it is actually being chosen at. The previous
 * control was a rotated Material slider of fixed height sitting beside the
 * button, so the scale it drew and the region the gesture read were two
 * different things — and at common split positions its head was clipped
 * off-pane entirely.
 *
 * Three things are shown, which is what was asked for (user, 2026-09-06):
 * where the gesture is landing right now ([pointerFraction], drawn as a line
 * across the whole zone), which span that is ([hoverIndex], filled), and
 * what that span means (the label, inside the fill). Every other rung
 * carries a label too when there is room, so the scale can be aimed at
 * before the finger gets there. Until the finger IS there ([armed] false),
 * the zone also names itself — "⏱ interval" — and the pointed-at rung's
 * label waits at the edge with the others.
 */
@Composable
internal fun IntervalLadder(
    hoverIndex: Int,
    armed: Boolean,
    pointerFraction: Float?,
    modifier: Modifier = Modifier,
) {
    val rungs = INTERVAL_LADDER
    val hover = hoverIndex.coerceIn(0, rungs.lastIndex)
    BoxWithConstraints(
        modifier
            .background(BandWash)
            .testTag("capture-interval-ladder")
            .semantics {
                stateDescription =
                    (if (armed) "armed " else "hover ") + rungs[hover].label
            },
    ) {
        // A label per rung only while they can be read; the ladder is as
        // tall as the pane, and a short pane in landscape leaves bands too
        // thin for a line of text. As large as the band allows (user,
        // 2026-10-10: "the interval value readouts could be bigger font
        // everywhere") — it was labelSmall at any height.
        val band = maxHeight / rungs.size
        val everyLabelStyle = when {
            band >= 24.dp -> MaterialTheme.typography.titleMedium
            band >= 18.dp -> MaterialTheme.typography.labelLarge
            band >= 14.dp -> MaterialTheme.typography.labelSmall
            else -> null
        }
        Column(Modifier.fillMaxSize()) {
            for (index in rungs.indices.reversed()) {
                val rung = rungs[index]
                val selected = index == hover
                Box(
                    Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .background(ladderBandColor(rung, selected, armed)),
                ) {
                    Box(
                        Modifier
                            .align(Alignment.TopStart)
                            .fillMaxWidth()
                            .height(1.dp)
                            .background(BandLine),
                    )
                    when {
                        // Armed: drawn after the bands instead (below), since
                        // the value is bigger than its band and the bands
                        // under it would paint over the overflow.
                        selected && armed -> Unit
                        // Only pointed at: where the other labels are, in
                        // white. The middle of the zone belongs to its name
                        // until the finger is on it.
                        selected -> Text(
                            rung.label,
                            style = everyLabelStyle ?: MaterialTheme.typography.labelLarge,
                            color = Color.White,
                            modifier = Modifier
                                .align(Alignment.CenterStart)
                                .padding(start = 8.dp)
                                .testTag("capture-interval-value"),
                        )
                        everyLabelStyle != null -> Text(
                            rung.label,
                            style = everyLabelStyle,
                            color = BandLabel,
                            modifier = Modifier
                                .align(Alignment.CenterStart)
                                .padding(start = 8.dp),
                        )
                    }
                }
            }
        }
        // The zone's name while the finger is not on it (user, 2026-10-10:
        // "the whole left side should maybe also say 'interval' when the
        // finger is not over it") — the twin of CancelZone's "✕ cancel",
        // so both halves say what they are before either is chosen.
        if (!armed) {
            Column(
                Modifier
                    .align(Alignment.Center)
                    .testTag("capture-interval-title"),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("⏱", style = MaterialTheme.typography.titleMedium, color = Color.White)
                Text("interval", style = MaterialTheme.typography.titleMedium, color = Color.White)
            }
        }
        // Where the finger is, to the pixel — the band says what will
        // happen, this says how close the next band is.
        pointerFraction?.let { fraction ->
            val lowest = (maxHeight - 2.dp).coerceAtLeast(0.dp)
            val y = (maxHeight * (1f - fraction) - 1.dp).coerceIn(0.dp, lowest)
            Box(
                Modifier
                    .offset(y = y)
                    .fillMaxWidth()
                    .height(2.dp)
                    .background(PointerLine)
                    .testTag("capture-interval-pointer"),
            )
        }
        // The armed value, big, centred on its band and allowed to spill
        // past it — over the pointer line too, on a shade, because this is
        // the one readout the release is about to act on.
        if (armed) {
            Box(
                Modifier
                    .offset(y = maxHeight - band * (hover + 1))
                    .fillMaxWidth()
                    .height(band),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    rungs[hover].label,
                    style = MaterialTheme.typography.headlineSmall,
                    color = Color.White,
                    modifier = Modifier
                        .wrapContentHeight(unbounded = true)
                        .background(ValueShade, RoundedCornerShape(6.dp))
                        .padding(horizontal = 8.dp)
                        .testTag("capture-interval-value"),
                )
            }
        }
    }
}
