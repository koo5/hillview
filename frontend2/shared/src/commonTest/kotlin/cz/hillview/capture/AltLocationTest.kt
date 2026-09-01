package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The castling rule (altLocationFor) and the wire shape (altLocationJson).
 * The JSON is asserted byte-for-byte because the backend's provenance test
 * reads these exact keys out of the UserComment.
 */
class AltLocationTest {

    private val fix = AltLocation(50.076, 14.44, atMs = 1_700_000_000_000, accuracyM = 5f, source = ALT_SOURCE_GPS_BACKGROUND)
    private val map = AltLocation(50.1, 14.5, atMs = 1_700_000_001_000, accuracyM = null, source = ALT_SOURCE_MAP_UNCLAIMED)

    /** The original's exact case: map claimed, the live fix rides along. */
    @Test
    fun aClaimedMapPositionKeepsTheFixAsAlternative() {
        assertEquals(fix, altLocationFor(manualElected = true, exploring = true, fix = fix, mapPosition = map))
    }

    /** The case the original never has: exploring, prompt up, not yet claimed. */
    @Test
    fun anUnclaimedPanKeepsTheMapPositionAsAlternative() {
        assertEquals(map, altLocationFor(manualElected = false, exploring = true, fix = fix, mapPosition = map))
    }

    /** Following: the two streams are one stream, nothing worth keeping. */
    @Test
    fun followingRecordsNoAlternative() {
        assertNull(altLocationFor(manualElected = false, exploring = false, fix = fix, mapPosition = map))
    }

    /** The no-fix hatch: the map is elected, but there is no fix to keep. */
    @Test
    fun theNoFixHatchHasNothingToKeep() {
        assertNull(altLocationFor(manualElected = true, exploring = false, fix = null, mapPosition = map))
    }

    @Test
    fun theJsonIsTheOriginalsShape() {
        assertEquals(
            """{"lat":50.076,"lng":14.44,"ts":1700000000000,"accuracy":5.0,"source":"gps-background"}""",
            altLocationJson(fix),
        )
        // A map position has no accuracy and says so by omission, not by 0.
        assertEquals(
            """{"lat":50.1,"lng":14.5,"ts":1700000001000,"source":"map-unclaimed"}""",
            altLocationJson(map),
        )
    }
}
