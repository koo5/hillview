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

/**
 * When the lock dims: not under the system's pinning confirmation (user,
 * 2026-11-05: "there should be a delay like 10 seconds, because Android pops
 * up a dialogue that the user first has to confirm").
 */
class LockDimTest {

    @Test
    fun withoutPinningThereIsNoDialogSoItDimsAtOnce() {
        assertTrue(dimNow(pinRequested = false, pinned = false, sinceLockMs = 0))
    }

    @Test
    fun withPinningItWaitsWhileTheDialogIsUp() {
        assertFalse(dimNow(pinRequested = true, pinned = false, sinceLockMs = 0))
        assertFalse(dimNow(pinRequested = true, pinned = false, sinceLockMs = DIM_AFTER_PIN_PROMPT_MS - 1))
    }

    @Test
    fun aConfirmedPinDimsStraightAway() {
        assertTrue(dimNow(pinRequested = true, pinned = true, sinceLockMs = 300))
    }

    @Test
    fun aDeclinedOrIgnoredDialogDimsAfterTheWait() {
        assertTrue(dimNow(pinRequested = true, pinned = false, sinceLockMs = DIM_AFTER_PIN_PROMPT_MS))
        assertEquals(10_000L, DIM_AFTER_PIN_PROMPT_MS)
    }
}
