package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Which rendition a slot asks for, ported from Photo.svelte's
 * updateSelectedUrl. The rule belongs to the SLOT, not the photo: the viewer
 * lays all five slots out at viewport size, so a neighbour asks for the same
 * width the front photo does.
 */
class PickRenditionTest {

    private fun photo(
        vararg sizes: Pair<String, Int>,
        url: String? = null,
    ) = PhotoMarker(
        id = "p",
        latitude = 0.0,
        longitude = 0.0,
        bearingDeg = 0.0,
        capturedAtMs = 0L,
        sizes = sizes.associate { (key, width) ->
            key to PhotoRendition("https://pics/$key.jpg", width, width * 3 / 4)
        },
        url = url,
    )

    @Test
    fun theSmallestRenditionThatWillNotBeUpscaled() {
        val p = photo("200" to 200, "500" to 500, "1024" to 1024, "full" to 4000)
        assertEquals("https://pics/500.jpg", p.pickRendition(320)?.url)
        assertEquals("https://pics/500.jpg", p.pickRendition(500)?.url, "exactly wide enough counts")
        assertEquals("https://pics/1024.jpg", p.pickRendition(501)?.url)
    }

    @Test
    fun aContainerWiderThanEveryRenditionGetsFull() {
        val p = photo("200" to 200, "500" to 500, "full" to 4000)
        assertEquals("https://pics/full.jpg", p.pickRendition(2000)?.url)
    }

    @Test
    fun withoutFullTheWidestNumericOneIsTheBestAvailable() {
        val p = photo("200" to 200, "500" to 500)
        assertEquals("https://pics/500.jpg", p.pickRendition(2000)?.url)
    }

    @Test
    fun aSourceWithNoRenditionsFallsBackToItsOneUrl() {
        val p = photo(url = "https://mapillary/thumb.jpg")
        assertEquals("https://mapillary/thumb.jpg", p.pickRendition(800)?.url)
    }

    @Test
    fun nothingToShowIsNull() {
        assertNull(photo().pickRendition(800))
    }

    @Test
    fun nonNumericKeysAreNotSizes() {
        // "full" is handled by name; anything else unparseable is ignored
        // rather than sorted as a width.
        val p = photo("thumb" to 64, "500" to 500, "full" to 4000)
        assertEquals("https://pics/500.jpg", p.pickRendition(300)?.url)
    }
}
