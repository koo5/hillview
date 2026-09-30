package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals

class ElapsedFormatTest {

    @Test
    fun secondsAreAlwaysTwoDigitsAndMinutesNeverPadded() {
        assertEquals("0:00", formatElapsed(0))
        assertEquals("0:07", formatElapsed(7_000))
        assertEquals("0:59", formatElapsed(59_999))
        assertEquals("1:00", formatElapsed(60_000))
        assertEquals("12:34", formatElapsed(754_000))
    }

    /** Hours only once there are any, so the common case stays short. */
    @Test
    fun hoursAppearOnlyWhenThereAreSome() {
        assertEquals("59:59", formatElapsed(3_599_000))
        assertEquals("1:00:00", formatElapsed(3_600_000))
        assertEquals("1:02:03", formatElapsed(3_723_000))
    }

    /** A clock that ran backwards is a bug elsewhere; it must not show here. */
    @Test
    fun aNegativeElapsedReadsAsZero() {
        assertEquals("0:00", formatElapsed(-5_000))
    }
}
