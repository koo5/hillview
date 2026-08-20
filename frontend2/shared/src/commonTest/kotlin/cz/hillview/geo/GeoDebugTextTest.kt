package cz.hillview.geo

import cz.hillview.map.BearingMode
import cz.hillview.map.BearingState
import cz.hillview.map.LocationTracking
import cz.hillview.map.SpatialState
import cz.hillview.map.TrackingPhase
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The readout exists to tell three states apart that all look identical on
 * screen: a still phone, a chain that stopped writing, and a source that
 * never wrote at all. The tests are those three.
 */
class GeoDebugTextTest {

    private val now = 1_000_000L

    private fun input(
        bearing: BearingState = BearingState(bearing = 90.0, source = "android-compass-true", ts = now),
        wanted: Boolean = true,
        phase: TrackingPhase = TrackingPhase.Active,
        raw: Double? = 90.0,
    ) = GeoDebugInput(
        bearing = bearing,
        spatial = SpatialState(latitude = 50.1, longitude = 14.5, source = "gps", ts = now),
        bearingWanted = wanted,
        bearingPhase = phase,
        bearingMode = BearingMode.Walking,
        locationTracking = LocationTracking.Active,
        rawHeadingDeg = raw,
        rawAccuracy = 3,
        rawAtMs = now,
        nowMs = now,
    )

    @Test
    fun aLiveChainReadsAsZeroAgeAndNoDrift() {
        val lines = geoDebugLines(input())
        assertEquals("🧭 90.0° android-compass-true 0.0s", lines[0])
        assertTrue(lines[1].contains("Δ0.0° 0.0s"), lines[1])
        assertTrue(lines[1].endsWith("walk · want ON · Active"), lines[1])
    }

    /**
     * The reported bug, in one line: the elected value is old and the raw
     * heading has moved away from it. Neither number alone says that.
     */
    @Test
    fun aStalledChainShowsItsAgeAndTheDriftFromRaw() {
        val lines = geoDebugLines(
            input(
                bearing = BearingState(bearing = 310.0, source = "android-compass-true", ts = now - 47_000),
                wanted = false,
                phase = TrackingPhase.Inactive,
                raw = 86.9,
            ),
        )
        assertEquals("🧭 310.0° android-compass-true 47s", lines[0])
        assertTrue(lines[1].contains("raw 86.9°"), lines[1])
        // 310 → 86.9 the short way round is 136.9, not 223.1.
        assertTrue(lines[1].contains("Δ136.9°"), lines[1])
        assertTrue(lines[1].contains("want OFF"), lines[1])
        // The pair that names the fault: the reading is fresh, the write is
        // not. Either age alone is ambiguous.
        assertTrue(lines[1].contains("Δ136.9° 0.0s"), lines[1])
    }

    /**
     * The dead-band means a still phone's elected bearing is legitimately
     * minutes old. That must not look like the stalled case above, and the
     * fresh raw age plus a zero delta is what says so.
     */
    @Test
    fun aStillPhoneIsNotAStalledChain() {
        val lines = geoDebugLines(
            input(
                bearing = BearingState(
                    bearing = 71.5,
                    source = "android-compass-true",
                    ts = now - 25 * 60_000,
                ),
                raw = 71.5,
            ),
        )
        assertEquals("🧭 71.5° android-compass-true 25m", lines[0])
        assertTrue(lines[1].contains("Δ0.0° 0.0s"), lines[1])
    }

    @Test
    fun aSourceThatNeverWroteSaysSoRatherThanShowingZero() {
        val lines = geoDebugLines(
            input(bearing = BearingState(bearing = 141.0, source = "map", ts = null), raw = null),
        )
        assertEquals("🧭 141.0° map never", lines[0])
        assertTrue(lines[1].startsWith("   raw — acc"), lines[1])
        // No Δ when there is nothing to compare against.
        assertTrue(!lines[1].contains("Δ"), lines[1])
    }

    @Test
    fun theTurnedToPhotoIsNamedSoNavigationIsDistinguishable() {
        val lines = geoDebugLines(
            input(
                bearing = BearingState(
                    bearing = 12.0,
                    source = "photo_navigation",
                    photoUid = "40b42f32-5334-491c-88b0-c0b2dda7a6d0",
                    ts = now,
                ),
            ),
        )
        assertTrue(lines[0].endsWith("uid:40b42f32"), lines[0])
    }

    @Test
    fun theSensorDetailIsCompressedToWhatVariesBetweenDevices() {
        assertEquals(
            "ROTATION_VECTOR·UPRIGHT",
            compactDetail("TYPE_ROTATION_VECTOR (UPRIGHT MODE) (EMA smoothed)"),
        )
        assertEquals("ACCELEROMETER", compactDetail("TYPE_ACCELEROMETER"))
    }

    /**
     * The tick this is compared against runs at 2 Hz, so a reading landing
     * between ticks is momentarily "in the future" — that is the clock, not
     * a fault, and it must not print as one.
     */
    @Test
    fun aReadingNewerThanTheTickReadsAsFresh() {
        val lines = geoDebugLines(input().copy(rawAtMs = now + 400))
        assertTrue(lines[1].contains("Δ0.0° 0.0s"), lines[1])
    }

    @Test
    fun theLocationLineCarriesItsOwnSourceAndAge() {
        val lines = geoDebugLines(input())
        assertEquals("📍 50.1,14.5 gps 0.0s · ACTIVE", lines[2])
    }
}
