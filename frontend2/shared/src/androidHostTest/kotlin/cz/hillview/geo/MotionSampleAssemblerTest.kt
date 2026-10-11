package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The test that was missing when the listener stopped passing its own vectors on.
 *
 * The ring tests could not catch it: they build samples carrying gravity themselves, so
 * they round-tripped a vector the real listener never supplied. This one asserts the
 * ASSEMBLY — what the callback latched comes back out of the sample it publishes — which
 * is where the value was lost.
 */
class MotionSampleAssemblerTest {

    @Test
    fun whatTheCallbackLatchedIsWhatTheSampleCarries() {
        val a = MotionSampleAssembler()
        a.gravity(0.1f, -0.2f, 9.81f)
        a.linear(3f, 4f, 0f)
        val s = a.sampleAt(atMs = 1_700_000_000_000, elapsedNs = 812_340_000_000)

        assertEquals(listOf(0.1f, -0.2f, 9.81f), s.gravity)
        assertEquals(listOf(3f, 4f, 0f), s.linearAcceleration)
        assertEquals(1_700_000_000_000, s.atMs)
        assertEquals(812_340_000_000, s.elapsedNs)
    }

    /**
     * The two sensors arrive on independent callbacks, so the first sample after a
     * registration legitimately carries one vector. Honest, and distinguishable from
     * carrying none — which is the state that shipped for a day.
     */
    @Test
    fun oneSensorHavingReportedIsEnoughToPublish() {
        val a = MotionSampleAssembler()
        a.gravity(0f, 0f, 9.81f)
        val s = a.sampleAt(1_000, 2_000)
        assertEquals(listOf(0f, 0f, 9.81f), s.gravity)
        assertNull(s.linearAcceleration, "linear acceleration has not arrived yet")
    }

    /** Each callback replaces its own vector and leaves the other one standing. */
    @Test
    fun eachSensorUpdatesOnlyItsOwnHalf() {
        val a = MotionSampleAssembler()
        a.gravity(0f, 0f, 9.81f)
        a.linear(1f, 1f, 1f)
        a.gravity(0f, 9.81f, 0f)
        val s = a.sampleAt(1_000, 2_000)
        assertEquals(listOf(0f, 9.81f, 0f), s.gravity)
        assertEquals(listOf(1f, 1f, 1f), s.linearAcceleration)
    }

    /**
     * Nothing is being sensed any more, so a later sample must not report what was true
     * before the sensors were released — a stale "down" under a fresh timestamp is the
     * invented-value mistake in another costume.
     */
    @Test
    fun resetStopsThePreviousReadingFromTravellingOn() {
        val a = MotionSampleAssembler()
        a.gravity(0f, 0f, 9.81f)
        a.linear(1f, 1f, 1f)
        a.reset()
        val s = a.sampleAt(1_000, 2_000)
        assertNull(s.gravity)
        assertNull(s.linearAcceleration)
    }
}
