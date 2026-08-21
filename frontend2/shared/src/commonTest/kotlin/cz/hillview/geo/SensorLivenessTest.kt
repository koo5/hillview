package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The restart this decides is disruptive, so the rule has to be exactly
 * "repeating WHILE the phone turned" — never merely "repeating".
 */
class SensorLivenessTest {

    // Big enough that "long ago" stays a positive elapsed-realtime stamp.
    private val now = 1_000_000L
    private val limit = 12_000L

    @Test
    fun aSampleThatMovedRecentlyIsHealthy() {
        assertFalse(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = now,
                valueChangeAtMs = now - 500,
                orientationChangeAtMs = now - 200,
                stuckLimitMs = limit,
            ),
        )
    }

    /**
     * A phone on a table repeats for hours and is not broken — and it never
     * reports an orientation change either, so the "never" sentinel must
     * not read as "just now". (This test caught exactly that: 0 compared as
     * newer than every real stamp.)
     */
    @Test
    fun aStillPhoneIsNeverRestartedForBeingStill() {
        assertFalse(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = now,
                valueChangeAtMs = now - 600_000,
                orientationChangeAtMs = 0L,
                stuckLimitMs = limit,
            ),
        )
    }

    /** Turned, then set down: the sample moved DURING the turn, so it works. */
    @Test
    fun aTurnOlderThanTheLastMovementProvesNothing() {
        assertFalse(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = now,
                valueChangeAtMs = now - 30_000,
                orientationChangeAtMs = now - 40_000,
                stuckLimitMs = limit,
            ),
        )
    }

    /** The fault: the phone turned and the vector did not follow. */
    @Test
    fun aTurnWithNoMovementInTheSampleIsStuck() {
        assertTrue(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = now,
                valueChangeAtMs = now - 30_000,
                orientationChangeAtMs = now - 5_000,
                stuckLimitMs = limit,
            ),
        )
    }

    @Test
    fun aFreshFreezeWaitsOutTheLimitBeforeCounting() {
        assertFalse(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = now,
                valueChangeAtMs = now - 5_000,
                orientationChangeAtMs = now - 1_000,
                stuckLimitMs = limit,
            ),
        )
    }

    /** Silence is the other watchdog's job, and must not be answered here. */
    @Test
    fun aRegistrationThatNeverDeliveredIsNotThisFault() {
        assertFalse(
            sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = 0L,
                valueChangeAtMs = 0L,
                orientationChangeAtMs = now - 1_000,
                stuckLimitMs = limit,
            ),
        )
    }
}
