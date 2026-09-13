package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

class IntervalLadderTest {

    @Test
    fun theLadderRunsCancelThenFasterThanASecondThenTheSecondsThenVideo() {
        assertSame(LadderRung.Cancel, INTERVAL_LADDER.first())
        assertSame(LadderRung.Video, INTERVAL_LADDER.last())

        val intervals = INTERVAL_LADDER.filterIsInstance<LadderRung.Every>()
        assertEquals(
            listOf(200, 300, 500, 750) + (1..INTERVAL_MAX_SEC).map { it * 1000 },
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
        // Releasing over "cancel" does nothing, so it never wears the green.
        assertEquals(
            ladderBandColor(LadderRung.Cancel, selected = true, armed = false),
            ladderBandColor(LadderRung.Cancel, selected = true, armed = true),
        )
    }
}
