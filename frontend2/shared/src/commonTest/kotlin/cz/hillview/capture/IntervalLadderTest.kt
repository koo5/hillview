package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

class IntervalLadderTest {

    @Test
    fun theLadderRunsFasterThanASecondThenTheSecondsThenVideo() {
        // No cancel rung at the foot (user, 2026-09-18): the bottom band is
        // the fastest interval, and the way out is the button's side.
        assertEquals(LadderRung.Every(200), INTERVAL_LADDER.first())
        assertSame(LadderRung.Video, INTERVAL_LADDER.last())

        // Above 3 s the rungs thin out (user, 2026-10-10: "video 30 20 10 8
        // 6 4 3 (the lower rest would stay as it is)").
        val intervals = INTERVAL_LADDER.filterIsInstance<LadderRung.Every>()
        assertEquals(
            listOf(200, 300, 500, 750) +
                listOf(1, 2, 3, 4, 6, 8, 10, 20, 30).map { it * 1000 },
            intervals.map { it.ms },
        )
        // The whole point of the sub-second rungs: the run loop can be asked
        // for a beat faster than the second the old ladder bottomed out at.
        assertTrue(intervals.first().ms < 1_000)
    }

    @Test
    fun everyRungIsSlowerThanTheOneBelowIt() {
        val ms = INTERVAL_LADDER.filterIsInstance<LadderRung.Every>().map { it.ms }
        assertEquals(ms.sorted(), ms)
        assertEquals(ms.distinct(), ms)
    }

    @Test
    fun labelsReadAsTimes() {
        assertEquals("0.2s", formatIntervalMs(200))
        assertEquals("0.75s", formatIntervalMs(750))
        assertEquals("1s", formatIntervalMs(1_000))
        assertEquals("15s", formatIntervalMs(15_000))
        // No bare decimal point, and no trailing zeros to read past.
        assertEquals("1.5s", formatIntervalMs(1_500))
        assertEquals("0.05s", formatIntervalMs(50))
    }

    /**
     * The band a finger is in must be the band the ladder draws, which means
     * equal bands and a FLOOR — the old mapping rounded, giving the two end
     * stops half-height bands.
     */
    @Test
    fun eachRungOwnsAnEqualBandOfTheTrack() {
        val count = INTERVAL_LADDER.size
        val top = 0f
        val bottom = 1000f
        val band = (bottom - top) / count

        for (index in 0 until count) {
            val centre = bottom - (index + 0.5f) * band
            assertEquals(index, rungIndexAt(centre, top, bottom), "centre of band $index")
        }
        // The very bottom pixel is the bottom rung; the very top is the top.
        assertEquals(0, rungIndexAt(bottom, top, bottom))
        assertEquals(count - 1, rungIndexAt(top, top, bottom))
    }

    @Test
    fun aFingerOffTheEndsIsClampedRatherThanLost() {
        val count = INTERVAL_LADDER.size
        assertEquals(0, rungIndexAt(9_999f, 0f, 1000f))
        assertEquals(count - 1, rungIndexAt(-9_999f, 0f, 1000f))
        assertEquals(0f, ladderFractionAt(9_999f, 0f, 1000f))
        assertEquals(1f, ladderFractionAt(-9_999f, 0f, 1000f))
    }

    /**
     * Portrait: the pane ends at y = 1000 with the map beneath it and the
     * button's left edge at x = 400. A thumb that slides down-left past the
     * pane's foot meant the bottom rung, and is given it — leaving the pane
     * used to be the cancel (user, 2026-10-10).
     */
    @Test
    fun theBottomLeftOffThePaneIsTheFastestRunNotACancel() {
        val belowThePane = 1_180f
        assertTrue(overLadderAt(x = 120f, buttonLeft = 400f))
        assertEquals(0, rungIndexAt(belowThePane, 200f, 1000f))
        assertEquals(LadderRung.Every(200), INTERVAL_LADDER[0])
    }

    /** The button's side, the button included, is the way out — at any height. */
    @Test
    fun theButtonsSideIsTheWayOut() {
        assertFalse(overLadderAt(x = 400f, buttonLeft = 400f))
        assertFalse(overLadderAt(x = 700f, buttonLeft = 400f))
        assertTrue(overLadderAt(x = 399f, buttonLeft = 400f))
    }

    @Test
    fun theFractionIsMeasuredFromTheBottom() {
        assertEquals(0f, ladderFractionAt(1000f, 0f, 1000f))
        assertEquals(0.25f, ladderFractionAt(750f, 0f, 1000f))
        assertEquals(1f, ladderFractionAt(0f, 0f, 1000f))
    }

    /** A degenerate track must not divide by zero mid-gesture. */
    @Test
    fun aZeroHeightTrackIsHarmless() {
        assertEquals(0, rungIndexAt(5f, 10f, 10f))
        assertEquals(0f, ladderFractionAt(5f, 10f, 10f))
    }

    @Test
    fun onlyAnArmedRungWearsItsPromise() {
        val run = LadderRung.Every(1_000)
        assertEquals(ladderBandColor(run, selected = false, armed = true).alpha, 0f)
        // Hovering without being over the catch zone is not a promise.
        assertTrue(
            ladderBandColor(run, selected = true, armed = false) !=
                ladderBandColor(run, selected = true, armed = true),
        )
        assertTrue(
            ladderBandColor(LadderRung.Video, selected = true, armed = true) !=
                ladderBandColor(run, selected = true, armed = true),
        )
    }
}
