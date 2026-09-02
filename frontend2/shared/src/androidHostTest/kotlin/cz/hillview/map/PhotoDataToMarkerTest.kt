package cz.hillview.map

import cz.hillview.plugin.LatLng
import cz.hillview.plugin.PhotoData
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** The marker's bearing follows has_bearing, never a test for 0.0. */
class PhotoDataToMarkerTest {
    private fun photo(bearing: Double, recorded: Boolean) = PhotoData(
        id = "1", uid = "hillview-1", source_type = "stream",
        coord = LatLng(50.0, 14.0), bearing = bearing, has_bearing = recorded, source = "hillview",
    )

    @Test
    fun aPhotoShotDueNorthHasABearing() {
        assertEquals(0.0, photo(0.0, recorded = true).toMarker().bearingDeg)
    }

    @Test
    fun anUnrecordedHeadingIsNoBearing() {
        assertNull(photo(0.0, recorded = false).toMarker().bearingDeg)
    }

    @Test
    fun aRecordedHeadingPassesThrough() {
        assertEquals(123.0, photo(123.0, recorded = true).toMarker().bearingDeg)
    }
}
