package cz.hillview.capture

import cz.hillview.settings.overlapSpacing
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The SfM run's pacing (user, 2026-11-05: "the sweet spot is somewhere in the
 * middle"): a shot per stretch of ground or turn of the lens, not per tick.
 */
class OverlapRunTest {

    private fun near(expected: Double, actual: Double, tol: Double = 1e-6) =
        assertTrue(abs(expected - actual) <= tol, "expected $expected, got $actual")

    // --- the odometer ---

    @Test
    fun theOdometerIntegratesTheReceiversSpeed() {
        val o = Odometer()
        o.onFix(0, 1.2f)
        o.onFix(1_000, 1.2f)
        o.onFix(2_000, 0.6f)
        near(2.4, o.metresAt(2_000))
        near(2.7, o.metresAt(2_500), 1e-6) // coasting on the last speed (a Float speed)
    }

    @Test
    fun aQuietReceiverStopsAddingDistance() {
        val o = Odometer(maxCoastMs = 2_000)
        o.onFix(0, 1.0f)
        near(2.0, o.metresAt(60_000))
    }

    @Test
    fun noSpeedOrASpeedInsideItsErrorBarIsStandingStill() {
        val o = Odometer()
        o.onFix(0, null)
        o.onFix(1_000, 0.3f, speedAccuracyMps = 0.5f)
        o.onFix(2_000, Float.NaN)
        near(0.0, o.metresAt(3_000))
    }

    @Test
    fun theOdometerNeverRunsBackwards() {
        val o = Odometer()
        o.onFix(0, 2.0f)
        val coasted = o.metresAt(900)
        o.onFix(1_000, 0.0f)
        assertTrue(o.metresAt(1_000) >= coasted)
    }

    // --- the turn ---

    @Test
    fun aTurnIsTheAngleBetweenLensDirections() {
        near(15.0, turnBetween(ViewDirection(350.0, 0.0), ViewDirection(5.0, 0.0)), 1e-9)
        near(20.0, turnBetween(ViewDirection(90.0, 0.0), ViewDirection(90.0, 20.0)), 1e-9)
        near(180.0, turnBetween(ViewDirection(0.0, 0.0), ViewDirection(180.0, 0.0)), 1e-9)
    }

    @Test
    fun lookingStraightDownHeadingMeansNothing() {
        // The compass swings wildly there; the view does not.
        near(0.0, turnBetween(ViewDirection(0.0, 90.0), ViewDirection(170.0, 90.0)), 1e-6)
    }

    // --- the trigger ---

    private val spacing = OverlapSpacing(metres = 1.5, turnDeg = 15.0, minGapMs = 200, maxGapMs = 5_000)
    private val north = ViewDirection(0.0, 0.0)

    @Test
    fun theFirstShotGoesAtOnce() {
        assertEquals(OverlapReason.Start, OverlapTrigger(spacing).due(0, 0.0, null))
    }

    @Test
    fun walkingFarEnoughIsDue() {
        val t = OverlapTrigger(spacing).apply { shot(0, 10.0, north) }
        assertNull(t.due(1_000, 11.4, north))
        assertEquals(OverlapReason.Moved, t.due(1_200, 11.5, north))
    }

    @Test
    fun turningOnTheSpotIsDue() {
        val t = OverlapTrigger(spacing).apply { shot(0, 0.0, north) }
        assertNull(t.due(500, 0.0, ViewDirection(14.0, 0.0)))
        assertEquals(OverlapReason.Turned, t.due(500, 0.0, ViewDirection(344.0, 0.0)))
    }

    @Test
    fun withNoDirectionOnlyDistanceAndTheHeartbeatCount() {
        val t = OverlapTrigger(spacing).apply { shot(0, 0.0, null) }
        assertNull(t.due(1_000, 0.0, ViewDirection(90.0, 0.0)))
        assertEquals(OverlapReason.Heartbeat, t.due(5_000, 0.0, ViewDirection(90.0, 0.0)))
    }

    @Test
    fun standingStillGetsOnlyTheHeartbeat() {
        val t = OverlapTrigger(spacing).apply { shot(0, 0.0, north) }
        assertNull(t.due(4_999, 0.0, north))
        assertEquals(OverlapReason.Heartbeat, t.due(5_000, 0.0, north))
    }

    @Test
    fun aFastCarCannotOutrunTheFloor() {
        // 30 m/s puts the next 1.5 m 50 ms away; the floor holds it to 200 ms.
        val t = OverlapTrigger(spacing).apply { shot(0, 0.0, north) }
        assertNull(t.due(199, 6.0, north))
        assertEquals(OverlapReason.Moved, t.due(200, 6.0, north))
    }

    @Test
    fun aSwitchedOffTriggerNeverFires() {
        val noDistance = OverlapTrigger(spacing.copy(metres = null)).apply { shot(0, 0.0, north) }
        assertNull(noDistance.due(1_000, 100.0, north))
        val noTurn = OverlapTrigger(spacing.copy(turnDeg = null)).apply { shot(0, 0.0, north) }
        assertNull(noTurn.due(1_000, 0.0, ViewDirection(180.0, 0.0)))
        val noHeartbeat = OverlapTrigger(spacing.copy(maxGapMs = null)).apply { shot(0, 0.0, north) }
        assertNull(noHeartbeat.due(600_000, 0.0, north))
    }

    /** The settings page's switches and values are what the run is paced by. */
    @Test
    fun theSettingsAreTheSpacing() {
        val defaults = cz.hillview.settings.MapSettings().overlapSpacingForTest()
        assertEquals(OverlapSpacing(), defaults)
        val off = cz.hillview.settings.MapSettings(
            sfmDistanceOn = false, sfmTurnOn = false, sfmHeartbeatOn = false,
            sfmMinGapMs = 500,
        ).overlapSpacingForTest()
        assertEquals(OverlapSpacing(metres = null, turnDeg = null, minGapMs = 500, maxGapMs = null), off)
        val tuned = cz.hillview.settings.MapSettings(sfmMetres = 3f, sfmTurnDeg = 25f, sfmHeartbeatMs = 10_000)
            .overlapSpacingForTest()
        assertEquals(OverlapSpacing(metres = 3.0, turnDeg = 25.0, maxGapMs = 10_000), tuned)
    }

    private fun cz.hillview.settings.MapSettings.overlapSpacingForTest() = overlapSpacing()

    @Test
    fun theRunIsOffUnlessAskedFor() {
        assertTrue(!cz.hillview.settings.MapSettings().sfmRunEnabled)
    }

    /** A walk at 1.2 m/s, simulated end to end: about one shot per 1.5 m. */
    @Test
    fun aSteadyWalkIsShotEveryStretch() {
        val o = Odometer()
        val t = OverlapTrigger(spacing)
        val shots = mutableListOf<Long>()
        var nextFix = 0L
        var now = 0L
        while (now <= 60_000) {
            if (now >= nextFix) { o.onFix(now, 1.2f); nextFix += 1_000 }
            val reason = t.due(now, o.metresAt(now), north)
            if (reason != null) { t.shot(now, o.metresAt(now), north); shots += now }
            now += 50
        }
        // 72 m in a minute, 1.5 m apart: 48 stretches, plus the first shot.
        assertTrue(shots.size in 47..50, "${shots.size} shots")
        val gaps = shots.zipWithNext { a, b -> b - a }
        assertTrue(gaps.all { it in 1_200..1_300 }, "gaps $gaps")
    }
}
