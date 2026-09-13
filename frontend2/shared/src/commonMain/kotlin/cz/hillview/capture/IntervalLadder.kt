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
 * The rungs are NOT evenly spaced in time, deliberately. Even seconds are
 * the working range, so they get a rung each; below one second the useful
 * differences are proportional rather than absolute, so the stops thin out.
 * The top rung is VIDEO, which is where "even less than zero interval"
 * belongs; the bottom is the way out.
 */
internal sealed interface LadderRung {
    /** What the ladder band and the shutter both show. */
    val label: String

    /**
     * The bottom rung: releasing here does nothing at all.
     *
     * It read "single" until 2026-09-06, which was wrong twice over
     * (user-caught): a plain tap is what takes a single shot, and this
     * rung does not take one. Releasing here is the same act as releasing
     * back over the button — the original's release-over-nothing — so it
     * says the same word.
     */
    data object Cancel : LadderRung {
        override val label = "cancel"
    }

    data class Every(val ms: Int) : LadderRung {
        override val label: String get() = formatIntervalMs(ms)
    }

    data object Video : LadderRung {
        override val label = "VIDEO"
    }
}

/**
 * Same physical track, finer grain: 15 s is the longest useful spacing (the
 * original's slow mode is 10 s) — a 60 s ceiling made every useful value
 * crowd the bottom centimetre of the scale.
 */
internal const val INTERVAL_MAX_SEC = 15

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
    add(LadderRung.Cancel)
    SUB_SECOND_MS.forEach { add(LadderRung.Every(it)) }
    (1..INTERVAL_MAX_SEC).forEach { add(LadderRung.Every(it * 1000)) }
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
private val PointerLine = Color(0xE6FFFFFF)

internal fun ladderBandColor(rung: LadderRung, selected: Boolean, armed: Boolean): Color = when {
    !selected -> Color.Transparent
    !armed -> HoverBand
    rung is LadderRung.Video -> VideoBand
    rung is LadderRung.Every -> RunBand
    // Armed over "cancel": releasing does nothing, so it wears no promise.
    else -> HoverBand
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
 * carries a small label too when there is room, so the scale can be aimed at
 * before the finger gets there.
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
        // thin for a line of text.
        val roomForEveryLabel = maxHeight / rungs.size >= 14.dp
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
                        selected -> Text(
                            rung.label,
                            style = MaterialTheme.typography.titleSmall,
                            color = Color.White,
                            modifier = Modifier
                                .align(Alignment.Center)
                                .testTag("capture-interval-value"),
                        )
                        roomForEveryLabel -> Text(
                            rung.label,
                            style = MaterialTheme.typography.labelSmall,
                            color = BandLabel,
                            modifier = Modifier
                                .align(Alignment.CenterStart)
                                .padding(start = 8.dp),
                        )
                    }
                }
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
    }
}
