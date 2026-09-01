package cz.hillview.viewer

import cz.hillview.map.PhotoMarker
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * The adapter between the map's markers and shared-kt's culler. What is
 * under test is the translation — the culling itself is the shared rule and
 * belongs to whoever owns AngularRangeCuller.
 */
class SharedRangeCullerTest {

    private val centerLat = 50.0
    private val centerLon = 14.0

    /** ~111 m per 0.001° of latitude, near enough for placing test photos. */
    private fun marker(id: String, bearing: Double?, metresNorth: Double = 0.0) = PhotoMarker(
        id = id,
        latitude = centerLat + metresNorth / 111_000.0,
        longitude = centerLon,
        bearingDeg = bearing,
        capturedAtMs = 0L,
        source = "hillview",
    )

    private fun cull(
        photos: List<PhotoMarker>,
        range: Double = 1000.0,
        picks: Set<String> = emptySet(),
    ) = SharedRangeCuller().inRange(photos, centerLat, centerLon, range, picks)

    @Test
    fun theRingComesBackInBearingOrder() {
        // Not cosmetic: left/right is index arithmetic on this order, and the
        // culler itself returns picks first and then bucket order.
        val out = cull(listOf(marker("s", 180.0), marker("n", 10.0), marker("e", 95.0)))
        assertEquals(listOf("n", "e", "s"), out.map { it.id })
    }

    @Test
    fun photosWithoutABearingAreDropped() {
        val out = cull(listOf(marker("a", 0.0), marker("unknown", null)))
        assertEquals(listOf("a"), out.map { it.id })
    }

    @Test
    fun aPickedPhotoWithoutABearingSurvivesTheCull() {
        // A tapped grey plus-marker becomes the pick; the shared culler keeps
        // in-range picks whether or not they carry a heading — without this
        // the photo being viewed is culled out from under the viewer.
        val chosen = marker("plus", null)
        val out = cull(listOf(marker("a", 0.0), chosen), picks = setOf("plus"))
        assertTrue(out.any { it === chosen }, "the picked heading-less marker must come back")
        assertTrue(out.any { it.id == "a" })
    }

    @Test
    fun aPickedHeadinglessPhotoBeyondTheRangeStaysOut() {
        // Picks bypass the cull, not the range: same rule as for any pick.
        val out = cull(listOf(marker("far", null, metresNorth = 5_000.0)), picks = setOf("far"))
        assertEquals(emptyList<String>(), out.map { it.id })
    }

    @Test
    fun photosBeyondTheRangeAreDropped() {
        val out = cull(listOf(marker("near", 0.0, metresNorth = 100.0), marker("far", 90.0, metresNorth = 5_000.0)))
        assertEquals(listOf("near"), out.map { it.id })
    }

    @Test
    fun theOriginalMarkersComeBackNotCopies() {
        // The stand-ins exist only to satisfy the shared culler's model; if
        // one leaked out, everything downstream would lose pitch, featured,
        // filteredOut and the rest.
        val original = marker("a", 42.0)
        val out = cull(listOf(original))
        assertEquals(1, out.size)
        assertSame(original, out.first())
    }

    @Test
    fun aPickInRangeSurvivesEvenInACrowd() {
        // Picks are what stop the photo you are looking at from being culled
        // out from under you. Fill one 10-degree bucket well past the cap and
        // check the pick is still there.
        val crowd = (1..400).map { marker("crowd$it", 90.0 + (it % 5) * 0.1) }
        val out = cull(crowd + marker("chosen", 270.0), picks = setOf("chosen"))
        assertTrue(out.any { it.id == "chosen" }, "the pick must survive the cull")
        assertEquals(300, out.size, "and the cap still holds")
    }
}
