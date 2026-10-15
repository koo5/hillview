package cz.hillview.geo

import cz.hillview.map.BearingMode
import cz.hillview.map.LocationTracking
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * What the map asks the geo hardware for (user, 2026-10-11): the walking
 * compass alone no longer runs the fix stream, only a position for its
 * declination; everything that needs actual fixes still gets the stream.
 */
class MapGeoNeedTest {

    @Test
    fun theWalkingCompassAloneNeedsOnlyTheCompass() {
        assertEquals(
            MapGeoNeed.Compass,
            mapGeoNeed(LocationTracking.Off, bearingWanted = true, BearingMode.Walking),
        )
    }

    @Test
    fun carModeNeedsFixesBecauseItsHeadingIsTheGpsCourse() {
        assertEquals(
            MapGeoNeed.Fixes,
            mapGeoNeed(LocationTracking.Off, bearingWanted = true, BearingMode.Car),
        )
    }

    @Test
    fun followMeNeedsFixesWhateverTheCompassDoes() {
        for (tracking in listOf(LocationTracking.Active, LocationTracking.Background)) {
            for (wanted in listOf(true, false)) {
                for (mode in BearingMode.entries) {
                    assertEquals(MapGeoNeed.Fixes, mapGeoNeed(tracking, wanted, mode), "$tracking $wanted $mode")
                }
            }
        }
    }

    @Test
    fun nothingOnNeedsNothing() {
        for (mode in BearingMode.entries) {
            assertEquals(MapGeoNeed.Nothing, mapGeoNeed(LocationTracking.Off, bearingWanted = false, mode))
        }
    }
}
