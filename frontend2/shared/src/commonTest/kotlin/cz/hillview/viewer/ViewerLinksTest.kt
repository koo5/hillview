package cz.hillview.viewer

import cz.hillview.map.PhotoMarker
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ViewerLinksTest {

    private fun marker(source: String, id: String = "42", bearing: Double? = 137.5) = PhotoMarker(
        id = id,
        latitude = 50.11692,
        longitude = 14.48837,
        bearingDeg = bearing,
        capturedAtMs = 0L,
        source = source,
    )

    /** Byte-for-byte the original's constructMapUrl output. */
    @Test
    fun aServerPhotoLinksToTheMapWithItInFront() {
        assertEquals(
            "https://hillview.cz/?lat=50.11692&lon=14.48837&zoom=17.5&bearing=137.5&photo=hillview-42",
            photoWebUrl("https://hillview.cz", marker("hillview"), mapZoom = 17.5),
        )
    }

    @Test
    fun aTrailingSlashOnTheBaseDoesNotDouble() {
        assertEquals(
            "https://dev.test/?lat=50.11692&lon=14.48837&zoom=18.0&photo=hillview-42",
            photoWebUrl("https://dev.test/", marker("hillview", bearing = null), mapZoom = 18.0),
        )
    }

    @Test
    fun onlyServerPhotosHaveAPage() {
        assertNull(photoWebUrl("https://hillview.cz", marker("device"), 18.0))
        assertNull(photoWebUrl("https://hillview.cz", marker("mapillary"), 18.0))
    }

    @Test
    fun theUidIsPercentEncodedLikeEncodeURIComponent() {
        val url = photoWebUrl("https://hillview.cz", marker("hillview", id = "a b/c"), 18.0)!!
        assertEquals("hillview-a%20b%2Fc", url.substringAfter("&photo="))
    }
}
