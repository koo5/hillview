package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals

/**
 * The rule that decides which photos a consumer must fetch together.
 *
 * It exists because of a measurement: the IMU arrays tile exactly, but a photo's own
 * array holds its own exposure in 1 case out of 86, so anything at-exposure needs the
 * run. What makes a run is CONTIGUOUS COVERAGE — consecutive presses no further apart
 * than one full window — not which button was pressed.
 */
class CaptureRunTrackerTest {

    private val window = 6_000L

    private fun tracker(): CaptureRunTracker {
        var n = 0
        return CaptureRunTracker(window) { "run${++n}" }
    }

    @Test
    fun capturesInsideOneWindowShareARun() {
        val t = tracker()
        // The measured interval run: ~0.75 s apart, windows overlapping heavily.
        val ids = (0 until 10).map { t.idFor(it * 750L) }
        assertEquals(setOf("run1"), ids.toSet())
    }

    /**
     * The measured hole was 4812.9 ms of missing coverage from a ~6 s gap between
     * bursts. A gap wider than the window means photo N's window opens after photo
     * N-1's ended, so the slices genuinely do not touch and the run is over.
     */
    @Test
    fun aGapWiderThanTheWindowStartsANewRun() {
        val t = tracker()
        assertEquals("run1", t.idFor(0))
        assertEquals("run1", t.idFor(window), "exactly one window still touches")
        assertEquals("run2", t.idFor(window * 2 + 1), "one millisecond too far")
        assertEquals("run2", t.idFor(window * 2 + 2), "and the new run then continues")
    }

    /**
     * A manual shot a few seconds after another one tiles with it, so it is the same
     * run whatever the UI was doing. The rule is about coverage, and coverage does not
     * know about modes.
     */
    @Test
    fun theRuleIgnoresHowTheShutterWasTriggered() {
        val t = tracker()
        val first = t.idFor(0)
        assertEquals(first, t.idFor(3_000), "a hand-pressed shot 3 s later still tiles")
    }

    @Test
    fun theFirstCaptureAlwaysOpensARun() {
        assertEquals("run1", tracker().idFor(1_234_567))
    }

    /**
     * Two separate sessions must not collide, which is the whole point of an id rather
     * than a timestamp: a consumer groups by equality and a repeated value would weld
     * unrelated photos into one sequence.
     */
    @Test
    fun consecutiveRunsGetDifferentIds() {
        val t = tracker()
        val a = t.idFor(0)
        val b = t.idFor(100_000)
        val c = t.idFor(200_000)
        assertNotEquals(a, b)
        assertNotEquals(b, c)
    }

    /**
     * elapsedRealtime does not go backwards within a process, but the guard is cheap and
     * the alternative is a negative "gap" silently reading as continuous.
     */
    @Test
    fun aBackwardInstantDoesNotSilentlyContinueARun() {
        val t = tracker()
        assertEquals("run1", t.idFor(10_000))
        assertEquals("run2", t.idFor(9_000))
    }
}
