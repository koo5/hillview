package cz.hillview.capture

import cz.hillview.map.FixState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The stamp table from docs/one-state.md, "The position side", one row per
 * test. This is the rule the Android pane applies at the shutter; it lives
 * here so the four rows are pinned on the host rather than inferred from a
 * behaviour test whose "no fix" depends on what ran before it.
 */
class StampPositionTest {

    private val fix = FixState(
        50.076, 14.44, altitude = 271.0, accuracyM = 5f,
        atMs = 1_700_000_000_000, elapsedRealtimeNanos = 1_000_000_000L,
    )
    private val pan = ManualLocation(50.1, 14.5, atMs = 1_700_000_001_000)
    /** A map nobody has placed: the blank first run. */
    private val unplaced = ManualLocation(50.11692, 14.48837, atMs = null)

    @Test
    fun aFixIsThePositionUnlessTheMapIsClaimedOverIt() {
        val p = stampPosition(fix, fixAgeMs = 4_000, pan = pan, claimed = false)!!
        assertEquals("gps", p.source)
        assertEquals(50.076, p.latitude)
        assertEquals(271.0, p.altitude)
        assertEquals(5f, p.accuracyM)
        assertEquals(4_000L, p.fixAgeMs)
    }

    @Test
    fun aClaimStampsTheMapOverTheFixWithNoMeasurementAttached() {
        val p = stampPosition(fix, fixAgeMs = 4_000, pan = pan, claimed = true)!!
        assertEquals("map", p.source)
        assertEquals(50.1, p.latitude)
        assertNull(p.altitude)
        assertNull(p.accuracyM)
        assertNull(p.fixAgeMs)
    }

    @Test
    fun withNoFixTheMapIsThePositionAndNoClaimIsNeeded() {
        val p = stampPosition(fix = null, fixAgeMs = null, pan = pan, claimed = false)!!
        assertEquals("map", p.source)
        assertEquals(50.1, p.latitude)
        // Claimed or not makes no difference when there is nothing to override.
        assertEquals(p, stampPosition(fix = null, fixAgeMs = null, pan = pan, claimed = true))
    }

    @Test
    fun aBlankFirstRunRecordsNoPositionAndSaysSo() {
        assertNull(stampPosition(fix = null, fixAgeMs = null, pan = unplaced, claimed = false))
        assertNull(stampPosition(fix = null, fixAgeMs = null, pan = null, claimed = false))
    }

    /** A stale fix is still the fix: its age rides along, nothing arbitrates. */
    @Test
    fun freshnessNeverDecidesTheStream() {
        val p = stampPosition(fix, fixAgeMs = 3_600_000, pan = pan, claimed = false)!!
        assertEquals("gps", p.source)
        assertEquals(3_600_000L, p.fixAgeMs)
    }

    /** An unplaced map cannot be claimed over a fix; the fix stands. */
    @Test
    fun aClaimOnAnUnplacedMapFallsBackToTheFixNotToNothing() {
        assertEquals("gps", stampPosition(fix, fixAgeMs = 1, pan = unplaced, claimed = true)!!.source)
    }
}
