package cz.hillview.lock

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The unlock gesture. Every case here is a way a pocket could open the lock
 * it exists to hold shut.
 */
class UnlockSliderTest {

    private val track = 600f

    @Test
    fun aNudgeDoesNotOpenIt() {
        assertFalse(unlockReached(0f, track))
        assertFalse(unlockReached(30f, track))
        assertFalse(unlockReached(track / 2f, track))
    }

    /** Nearly the whole way, because half a track is a plausible accident. */
    @Test
    fun onlyASweepThatLandsOpensIt() {
        assertFalse(unlockReached(track * 0.9f, track))
        assertTrue(unlockReached(track * UNLOCK_TRAVEL_FRACTION, track))
        assertTrue(unlockReached(track, track))
    }

    @Test
    fun theKnobNeverLeavesItsTrack() {
        assertEquals(0f, unlockKnobOffset(-500f, track))
        assertEquals(250f, unlockKnobOffset(250f, track))
        assertEquals(track, unlockKnobOffset(5_000f, track))
    }

    /**
     * Before layout the track has no width. Nothing may open then — a
     * zero-length track would otherwise be travelled by standing still.
     */
    @Test
    fun anUnmeasuredTrackOpensNothing() {
        assertFalse(unlockReached(0f, 0f))
        assertFalse(unlockReached(1_000f, 0f))
        assertEquals(0f, unlockKnobOffset(50f, 0f))
    }
}

/**
 * The lock itself is one flag, and the only interesting thing about it is
 * that it does NOT persist — see the class doc.
 */
class ControlsLockStateTest {

    @Test
    fun itStartsOpenAndClosesOnDemand() {
        val lock = ControlsLock()
        assertFalse(lock.locked.value)
        lock.lock()
        assertTrue(lock.locked.value)
        lock.unlock()
        assertFalse(lock.locked.value)
    }

    @Test
    fun lockingTwiceIsStillLocked() {
        val lock = ControlsLock()
        lock.lock()
        lock.lock()
        assertTrue(lock.locked.value)
        lock.unlock()
        assertFalse(lock.locked.value, "one unlock must be enough")
    }

    /**
     * The defaults are the shape of the trade: dim yes, because the screen
     * has to be on and need not be bright; the two intrusive ones no.
     */
    @Test
    fun theDefaultsLeaveTheIntrusiveOnesOff() {
        val o = LockOptions()
        assertTrue(o.dimScreen)
        assertEquals(0f, o.brightness)
        assertFalse(o.darkTheme, "an LCD gains nothing and loses legibility")
        assertFalse(o.pinScreen, "the system asks before it pins")
        assertTrue(o.hideSystemBars)
    }
}
