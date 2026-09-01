package cz.hillview.viewer

import cz.hillview.map.BearingState
import cz.hillview.map.MapStateHolder
import cz.hillview.map.PhotoMarker
import cz.hillview.map.SpatialState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The viewer's state derivation and its one action, from
 * docs/tauri-viewer-ui-contract.md.
 */
class ViewerStateTest {

    private fun photo(
        id: String,
        bearing: Double?,
        pitch: Double? = null,
        featured: Boolean = false,
        filteredOut: Boolean = false,
    ) = PhotoMarker(
        id = id,
        latitude = 50.0,
        longitude = 14.0,
        bearingDeg = bearing,
        pitchDeg = pitch,
        capturedAtMs = 0L,
        featured = featured,
        filteredOut = filteredOut,
    )

    /**
     * Stands in for shared-kt's AngularRangeCuller: keeps everything, sorted
     * the way the real one guarantees. What is tested here is the derivation
     * around it, not the culling.
     */
    private val keepAll = RangeCuller { photos, _, _, _, _ ->
        photos.sortedWith(compareBy({ it.bearingDeg ?: Double.MAX_VALUE }, { it.id }))
    }

    private fun derive(
        markers: List<PhotoMarker>,
        bearing: Double = 0.0,
        stickyUid: String? = null,
        hunter: Boolean = true,
        override: Boolean = false,
        cull: RangeCuller = keepAll,
    ) = deriveViewerState(
        markers,
        SpatialState(latitude = 50.0, longitude = 14.0, range = 500.0),
        BearingState(bearing = bearing, photoUid = stickyUid),
        hunter, override, cull,
    )

    @Test
    fun theRingIsWhatYouCanTurnTo() {
        val state = derive(
            listOf(photo("n", 0.0), photo("e", 90.0), photo("hidden", 45.0, filteredOut = true)),
        )
        assertEquals(listOf("n", "e"), state.ring.map { it.id })
        assertEquals("n", state.front?.id)
        // Two photos, so both sides of the ring are the same one.
        assertEquals("e", state.left?.id)
        assertEquals("e", state.right?.id)
    }

    @Test
    fun theFrontPhotoFollowsTheBearing() {
        val markers = listOf(photo("n", 0.0), photo("e", 90.0), photo("s", 180.0))
        assertEquals("n", derive(markers, bearing = 5.0).front?.id)
        assertEquals("e", derive(markers, bearing = 80.0).front?.id)
        assertEquals("s", derive(markers, bearing = 190.0).front?.id)
    }

    @Test
    fun upAndDownNeverDuplicateLeftOrRight() {
        val markers = listOf(
            photo("level", 90.0, pitch = 0.0),
            photo("high", 91.0, pitch = 20.0),
            photo("far", 200.0, pitch = 40.0),
        )
        val state = derive(markers, bearing = 90.0)
        assertEquals("level", state.front?.id)
        assertEquals("high", state.right?.id)
        assertNull(state.up, "the photo above is already reachable sideways")
    }

    @Test
    fun aPhotoWithNoBearingIsNotInTheRing() {
        val state = derive(listOf(photo("a", 0.0), photo("nobearing", null)))
        assertEquals(listOf("a"), state.ring.map { it.id })
    }

    @Test
    fun theChosenPhotoIsOfferedToTheCullerAsAPick() {
        // The contract's reason: without this, the photo you are looking at
        // can be culled out from under you when the map moves.
        var seenPicks: Set<String>? = null
        val spy = RangeCuller { photos, _, _, _, picks ->
            seenPicks = picks
            photos.sortedBy { it.bearingDeg }
        }
        derive(listOf(photo("a", 0.0)), stickyUid = "chosen", cull = spy)
        assertEquals(setOf("chosen"), seenPicks)
    }

    @Test
    fun nothingInRangeIsAnEmptyStateNotACrash() {
        val state = derive(emptyList())
        assertTrue(state.ring.isEmpty())
        assertNull(state.front)
        assertNull(state.left)
        assertNull(state.up)
    }

    @Test
    fun turningWritesTheBearingAndRemembersTheChoice() {
        // The point of the pane: navigating IS turning, through the one
        // funnel, so the map and the next capture's stamp follow from it.
        val map = MapStateHolder()
        val holder = holderFor(map)

        holder.turnTo(photo("chosen", 137.0))

        assertEquals(137.0, map.bearing.value.bearing)
        assertEquals("chosen", map.bearing.value.photoUid)
        assertEquals(ViewerStateHolder.SOURCE_PHOTO_NAVIGATION, map.bearing.value.source)
    }

    @Test
    fun choosingAPhotoWithNoBearingKeepsTheViewStill() {
        // It used to be refused outright; now the choice lands — the view
        // just has nothing to turn to, so the bearing stays put.
        val map = MapStateHolder()
        stoodDown = false
        val before = map.bearing.value.bearing
        holderFor(map).turnTo(photo("unknown", null))
        assertEquals(before, map.bearing.value.bearing)
        assertEquals("unknown", map.bearing.value.photoUid)
        assertEquals(ViewerStateHolder.SOURCE_PHOTO_NAVIGATION, map.bearing.value.source)
        // Deliberate choice: tracking stands down like for any turn.
        assertTrue(stoodDown)
    }

    @Test
    fun aChosenPhotoWithNoBearingFrontsWithNoNeighbours() {
        val markers = listOf(photo("n", 0.0), photo("e", 90.0), photo("plus", null))
        val state = derive(markers, bearing = 5.0, stickyUid = "plus")
        assertEquals("plus", state.front?.id)
        // The ring is still what you can TURN to — unchanged.
        assertEquals(listOf("n", "e"), state.ring.map { it.id })
        assertNull(state.left)
        assertNull(state.right)
        assertNull(state.up)
        assertNull(state.down)
    }

    @Test
    fun theHeadinglessChoiceDropsWithThePhotoUid() {
        // Any bearing write without photoUid clears the choice (see
        // MapStateTest.bearingClearsPhotoAndAccuracyWhenNotGiven); the
        // derivation then falls back to the nearest-bearing rule.
        val markers = listOf(photo("n", 0.0), photo("plus", null))
        assertEquals("n", derive(markers, bearing = 5.0, stickyUid = null).front?.id)
    }

    private var stoodDown = false

    /**
     * The derivation is not free — a range cull and a sort of every marker
     * — and it used to run on every compass tick for the life of the
     * process, viewer or no viewer. It must run only while something
     * collects, as the original's derived store does.
     */
    @Test
    fun nothingIsDerivedWhileNobodyIsLooking() = kotlinx.coroutines.test.runTest {
        var culls = 0
        val counting = RangeCuller { photos, a, b, c, d -> culls++; keepAll.inRange(photos, a, b, c, d) }
        val map = MapStateHolder()
        val holder = ViewerStateHolder(
            map = map,
            standDownTracking = {},
            markers = MutableStateFlow(listOf(photo("a", 90.0))),
            hunterMode = MutableStateFlow(true),
            overrideFilters = MutableStateFlow(false),
            cull = counting,
            // The sharing coroutine lives as long as the holder; runTest
            // cancels backgroundScope at the end instead of waiting on it.
            scope = backgroundScope,
            now = { 1_000L },
        )
        // The compass ticks; nobody is in the viewer.
        repeat(5) { map.updateBearing(10.0 * it, now = it.toLong()) }
        testScheduler.advanceUntilIdle()
        assertEquals(0, culls, "derived with no subscriber")

        // The viewer opens: the value is derived, and follows the compass.
        val derived = kotlinx.coroutines.withTimeout(5_000) {
            holder.state.first { it.ring.isNotEmpty() }
        }
        assertEquals("a", derived.front?.id)
        assertTrue(culls >= 1, "not derived for a subscriber")
        val before = culls
        val watcher = launch { holder.state.collect {} }
        testScheduler.runCurrent()
        map.updateBearing(180.0, now = 99L)
        testScheduler.advanceUntilIdle()
        assertTrue(culls > before, "a bearing change did not re-derive (culls=$culls, before=$before)")
        watcher.cancel()
    }

    /**
     * The original's updateBearingWithPhoto() disables bearing tracking
     * before writing the photo's bearing; without that the compass takes
     * the value back on its next reading and the turn does not stick.
     */
    @Test
    fun turningToAPhotoStandsBearingTrackingDown() {
        val map = MapStateHolder()
        stoodDown = false
        holderFor(map).turnTo(photo("p1", 90.0))
        assertTrue(stoodDown)
        assertEquals(90.0, map.bearing.value.bearing)
    }

    private fun holderFor(map: MapStateHolder) = ViewerStateHolder(
        map = map,
        standDownTracking = { stoodDown = true },
        markers = MutableStateFlow(emptyList()),
        hunterMode = MutableStateFlow(true),
        overrideFilters = MutableStateFlow(false),
        cull = keepAll,
        scope = CoroutineScope(Dispatchers.Unconfined),
        now = { 1_000L },
    )
}
