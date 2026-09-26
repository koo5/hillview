package cz.hillview.upload

import cz.hillview.plugin.UPLOAD_HOLD_IMU_WINDOW
import cz.hillview.plugin.UPLOAD_HOLD_REFINER
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The upload hold with TWO holders: the stamp refiner and the deferred IMU
 * window, both of which enrich a row after it exists and finish at different
 * times.
 *
 * Modelled rather than driven through Room, because what is under test is the
 * RULE — a bitmask, a deadline, and one selection predicate — and every ordering
 * of two events is enumerable here, which it is not on a device.
 *
 * Two bugs are pinned, and the second one was found BY this test:
 *
 *  1. The hold originally had one holder and one release (`uploadHoldUntil = 0`),
 *     so whichever enricher finished first freed the row out from under the
 *     other. A photo the refiner did not want had no hold at all, so its IMU
 *     payload could never reach an upload.
 *  2. The first fix kept a single deadline and had each holder release down to
 *     the OTHER's. That is correct only while the two deadlines DIFFER — when
 *     they are equal neither release lowers anything and the row waits out the
 *     full hold, which would have delayed every upload by a minute. They were
 *     equal. Hence named holders instead of arithmetic.
 */
class UploadHoldTest {

    /** `photos.uploadHoldUntil` + `uploadHoldReasons`, and the operations on them. */
    private class Row(reasons: Int, deadline: Long) {
        var reasons: Int = reasons
            private set

        var deadline: Long = deadline
            private set

        /**
         * `SET uploadHoldReasons = reasons & ~bit`, plus `uploadHoldUntil = 0`
         * once no holder is left — see the DAO for why both halves are needed.
         */
        fun release(bit: Int) {
            reasons = reasons and bit.inv()
            if (reasons == 0) deadline = 0
        }

        /**
         * `WHERE uploadHoldUntil <= :now` — UNCHANGED from before the bits
         * existed. The bits decide when the deadline is zeroed, and are never a
         * second gate; see the DAO for the two wrong turns that proves.
         */
        fun claimableAt(now: Long) = deadline <= now
    }

    private val shutter = 1_000_000L
    private val deadline = shutter + 60_000
    private val both = UPLOAD_HOLD_REFINER or UPLOAD_HOLD_IMU_WINDOW

    // --- neither holder may free the row alone ---

    @Test
    fun theRefinerFinishingFirstDoesNotFreeTheRow() {
        val r = Row(both, deadline)
        r.release(UPLOAD_HOLD_REFINER)
        assertFalse(r.claimableAt(shutter + 3_000), "freed while the window was still pending")
        assertFalse(r.claimableAt(shutter + 30_000))
    }

    @Test
    fun theWindowFinishingFirstDoesNotFreeTheRow() {
        val r = Row(both, deadline)
        r.release(UPLOAD_HOLD_IMU_WINDOW)
        assertFalse(r.claimableAt(shutter + 4_000), "freed while refinement was still pending")
    }

    // --- whoever finishes last frees it, in either order, IMMEDIATELY ---

    @Test
    fun bothOrdersFreeTheRowAsSoonAsTheSecondOneReleases() {
        val orders = listOf(
            listOf(UPLOAD_HOLD_REFINER, UPLOAD_HOLD_IMU_WINDOW),
            listOf(UPLOAD_HOLD_IMU_WINDOW, UPLOAD_HOLD_REFINER),
        )
        for (order in orders) {
            val r = Row(both, deadline)
            order.forEach { r.release(it) }
            // The regression the equal-deadline version had: freed at once, NOT
            // after waiting out the hold.
            assertTrue(
                r.claimableAt(shutter + 4_000),
                "still held after both released (order $order, reasons ${r.reasons})",
            )
        }
    }

    /** Releasing the same bit twice is harmless — a retry must not wedge a row. */
    @Test
    fun aRepeatedReleaseIsIdempotent() {
        val r = Row(both, deadline)
        r.release(UPLOAD_HOLD_REFINER)
        r.release(UPLOAD_HOLD_REFINER)
        assertFalse(r.claimableAt(shutter + 4_000), "the other holder's bit was cleared too")
        r.release(UPLOAD_HOLD_IMU_WINDOW)
        assertTrue(r.claimableAt(shutter + 4_000))
    }

    /** A holder clears ONLY its own bit — the whole point of naming them. */
    @Test
    fun aHolderCannotClearTheOthersBit() {
        val r = Row(both, deadline)
        r.release(UPLOAD_HOLD_REFINER)
        assertTrue(r.reasons == UPLOAD_HOLD_IMU_WINDOW, "reasons became ${r.reasons}")
    }

    // --- one holder only ---

    @Test
    fun aPhotoTheRefinerIgnoresIsStillHeldForItsWindow() {
        // Bug 1: this used to be no hold at all, so the window never landed.
        val r = Row(UPLOAD_HOLD_IMU_WINDOW, deadline)
        assertFalse(r.claimableAt(shutter + 1_000), "no hold — the window cannot land")
        r.release(UPLOAD_HOLD_IMU_WINDOW)
        assertTrue(r.claimableAt(shutter + 4_000))
    }

    @Test
    fun aCaptureWithNoShutterTimeIsHeldOnlyByTheRefiner() {
        val r = Row(UPLOAD_HOLD_REFINER, deadline)
        r.release(UPLOAD_HOLD_REFINER)
        assertTrue(r.claimableAt(shutter + 3_000))
    }

    /** Nothing to wait for: uploadable at once, with no deadline to sit out. */
    @Test
    fun aRowNobodyOwesIsImmediatelyClaimable() {
        assertTrue(Row(0, deadline = 0).claimableAt(shutter))
    }

    /**
     * A hold set as a BARE DEADLINE, with no holder bit, still holds. That is the
     * older contract (`UploadClaimRaceTest` on a device asserts it), and making
     * the bits alone authoritative silently voided every such hold — including the
     * stale ones `StartupReconciler` exists to clean up.
     */
    @Test
    fun aBareDeadlineWithNoHolderStillHolds() {
        val r = Row(0, deadline)
        assertFalse(r.claimableAt(deadline - 1), "a bare deadline must still hold")
        assertTrue(r.claimableAt(deadline))
    }

    // --- crash recovery, which is all the deadline is for now ---

    @Test
    fun aHolderThatDiesLeavesTheDeadlineToFreeTheRow() {
        val r = Row(both, deadline)
        // The window's pass never ran: process death, or the IMU never started.
        r.release(UPLOAD_HOLD_REFINER)
        assertFalse(r.claimableAt(deadline - 1), "freed before the escape hatch")
        assertTrue(r.claimableAt(deadline), "a wedged row must still be freed eventually")
    }
}
