package cz.hillview.viewer

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The viewer pane's navigation rules, from docs/tauri-viewer-ui-contract.md.
 *
 * Written before the pane exists: these are the behaviours the Svelte app
 * has and the Compose one must match, and every one of them is a rule that
 * would be easy to get subtly wrong by reading the UI instead of the
 * contract.
 */
class ViewerRulesTest {

    private data class P(
        val uid: String,
        val bearing: Double,
        val pitch: Double? = null,
        val filtered: Boolean = false,
        val featured: Boolean = false,
    )

    private fun ring(vararg photos: P) = photos.sortedWith(
        compareBy<P> { it.bearing }.thenBy { it.uid },
    )

    private fun navigable(
        photos: List<P>,
        hunter: Boolean = true,
        override: Boolean = false,
    ) = navigablePhotos(photos, hunter, override, { it.filtered }, { it.featured }, { it.bearing })

    private fun front(photos: List<P>, bearing: Double, sticky: String? = null) =
        viewerFrontPhoto(photos, bearing, sticky, { it.uid }, { it.bearing })

    private fun left(photos: List<P>, f: P?) = ringNeighbour(photos, f, -1) { it.uid }
    private fun right(photos: List<P>, f: P?) = ringNeighbour(photos, f, +1) { it.uid }

    private fun vertical(photos: List<P>, f: P?, up: Boolean, exclude: List<P?> = emptyList()) =
        pitchNeighbour(photos, f, up, exclude, { it.uid }, { it.bearing }, { it.pitch })

    // ---- what you may turn to -------------------------------------------

    @Test
    fun filteredPhotosAreDroppedUnlessOverridden() {
        val photos = ring(P("a", 0.0), P("b", 90.0, filtered = true))
        assertEquals(listOf("a"), navigable(photos).map { it.uid })
        assertEquals(listOf("a", "b"), navigable(photos, override = true).map { it.uid })
    }

    @Test
    fun withHunterOffASingleFeaturedPhotoCollapsesTheRing() {
        // The surprising rule, and the one most likely to be "fixed" by
        // someone who thinks it is a bug: with hunter mode off, anything
        // featured in range hides everything that is not.
        val photos = ring(P("plain", 0.0), P("star", 90.0, featured = true))
        assertEquals(listOf("star"), navigable(photos, hunter = false).map { it.uid })
        assertEquals(listOf("plain", "star"), navigable(photos, hunter = true).map { it.uid })
    }

    @Test
    fun overridingFiltersCannotManufactureAFeaturedRing() {
        // The only featured photo is also filtered. Overriding the filters
        // brings it back into view, but it must not suddenly count as "there
        // are featured photos here" and hide everything else -- anyFeatured
        // is decided over the in-range set as featured AND unfiltered.
        val photos = ring(P("plain", 0.0), P("hidden", 90.0, featured = true, filtered = true))
        assertEquals(
            listOf("plain", "hidden"),
            navigable(photos, hunter = false, override = true).map { it.uid },
        )
    }

    @Test
    fun withHunterOffAndNothingFeaturedEverythingStays() {
        val photos = ring(P("a", 0.0), P("b", 90.0))
        assertEquals(listOf("a", "b"), navigable(photos, hunter = false).map { it.uid })
    }

    @Test
    fun photosWithoutABearingCannotBeInTheRing() {
        val photos = listOf(P("a", 0.0), P("nobearing", 0.0))
        val kept = navigablePhotos(
            photos, hunterMode = true, overrideFilters = false,
            filtered = { it.filtered }, featured = { it.featured },
            bearing = { if (it.uid == "nobearing") null else it.bearing },
        )
        assertEquals(listOf("a"), kept.map { it.uid })
    }

    // ---- what you are facing --------------------------------------------

    @Test
    fun theFrontPhotoIsTheNearestBearing() {
        val photos = ring(P("n", 10.0), P("e", 90.0), P("s", 180.0))
        assertEquals("e", front(photos, 80.0)?.uid)
        // And the ring wraps: 350° is nearer to 10° than to 180°.
        assertEquals("n", front(photos, 350.0)?.uid)
    }

    @Test
    fun tiesGoToTheSmallerUidSoTheChoiceCannotFlip() {
        val photos = ring(P("b", 90.0), P("a", 90.0))
        assertEquals("a", front(photos, 90.0)?.uid)
    }

    @Test
    fun aDeliberateChoiceSticksUntilTheViewMoves() {
        // Two photos at the same bearing: without stickiness the id tiebreak
        // would silently reclaim the one we just turned to.
        val photos = ring(P("a", 90.0), P("b", 90.0))
        assertEquals("b", front(photos, 90.0, sticky = "b")?.uid)
        // Move the view by any amount and the ordinary rule takes over.
        assertEquals("a", front(photos, 91.0, sticky = "b")?.uid)
    }

    @Test
    fun stickinessCannotResurrectAPhotoThatLeftTheRing() {
        val photos = ring(P("a", 90.0))
        assertEquals("a", front(photos, 90.0, sticky = "gone")?.uid)
        assertNull(front(emptyList(), 90.0, sticky = "gone"))
    }

    // ---- left and right --------------------------------------------------

    @Test
    fun leftAndRightWalkTheRingAndWrapAround() {
        val photos = ring(P("n", 0.0), P("e", 90.0), P("s", 180.0))
        val f = photos.first { it.uid == "e" }
        assertEquals("n", left(photos, f)?.uid)
        assertEquals("s", right(photos, f)?.uid)
        // Past the ends: the ring is a compass, not a list.
        assertEquals("s", left(photos, photos.first { it.uid == "n" })?.uid)
        assertEquals("n", right(photos, photos.first { it.uid == "s" })?.uid)
    }

    @Test
    fun thereIsNowhereToTurnWithOneOrNoPhotos() {
        val one = ring(P("a", 0.0))
        assertNull(left(one, one.first()))
        assertNull(right(one, one.first()))
        assertNull(left(emptyList(), null))
    }

    @Test
    fun aFrontPhotoThatFellOutOfRangeHasNoNeighbours() {
        val photos = ring(P("a", 0.0), P("b", 90.0))
        val stale = P("gone", 45.0)
        assertNull(left(photos, stale))
        assertNull(right(photos, stale))
    }

    // ---- up and down -----------------------------------------------------

    @Test
    fun upAndDownFollowPitchAtTheSameBearing() {
        val photos = ring(
            P("level", 90.0, pitch = 0.0),
            P("higher", 92.0, pitch = 10.0),
            P("highest", 93.0, pitch = 25.0),
            P("lower", 88.0, pitch = -15.0),
        )
        val f = photos.first { it.uid == "level" }
        // The most extreme wins, so repeated swipes climb instead of dithering.
        assertEquals("highest", vertical(photos, f, up = true)?.uid)
        assertEquals("lower", vertical(photos, f, up = false)?.uid)
    }

    @Test
    fun aDifferentDirectionIsNotUpOrDown() {
        // 20 degrees away is a different view, however much higher it is.
        val photos = ring(P("level", 90.0, pitch = 0.0), P("elsewhere", 110.0, pitch = 30.0))
        assertNull(vertical(photos, photos.first { it.uid == "level" }, up = true))
    }

    @Test
    fun equalPitchIsNeitherUpNorDown() {
        val photos = ring(P("level", 90.0, pitch = 5.0), P("same", 91.0, pitch = 5.0))
        val f = photos.first { it.uid == "level" }
        assertNull(vertical(photos, f, up = true))
        assertNull(vertical(photos, f, up = false))
    }

    @Test
    fun missingPitchCountsAsLevel() {
        val photos = ring(P("noPitch", 90.0), P("above", 91.0, pitch = 4.0))
        assertEquals("above", vertical(photos, photos.first { it.uid == "noPitch" }, up = true)?.uid)
    }

    @Test
    fun aPhotoAlreadyReachableSidewaysIsNotAlsoUp() {
        // One photo must never fill two slots: a swipe up and a swipe right
        // landing in the same place makes the pane look broken.
        val photos = ring(P("level", 90.0, pitch = 0.0), P("neighbour", 91.0, pitch = 10.0))
        val f = photos.first { it.uid == "level" }
        val r = photos.first { it.uid == "neighbour" }
        assertEquals("neighbour", vertical(photos, f, up = true)?.uid)
        assertNull(vertical(photos, f, up = true, exclude = listOf(r)))
    }
}
