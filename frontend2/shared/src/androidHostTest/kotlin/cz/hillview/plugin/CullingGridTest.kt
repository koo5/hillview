package cz.hillview.plugin

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The shared culling grid — the Svelte pipeline's CullingGrid.test.ts
 * cases, ported, plus the property the incremental marker pipeline leans
 * on: the culled set is a function of what each source holds, never of
 * which source answered first.
 */
class CullingGridTest {

    private val bounds = Bounds(
        top_left = LatLng(50.1, 14.3),
        bottom_right = LatLng(50.0, 14.4),
    )

    private fun photo(
        id: String,
        source: String,
        lat: Double = 50.05,
        lng: Double = 14.35,
        hash: String? = null,
        capturedAt: Long? = null,
    ) = PhotoData(
        id = id,
        uid = "$source-$id",
        source_type = source,
        coord = LatLng(lat, lng),
        bearing = 0.0,
        source = source,
        fileHash = hash,
        captured_at = capturedAt,
        is_device_photo = source == "device",
    )

    private fun cull(perSource: Map<String, List<PhotoData>>, max: Int, picks: Set<String> = emptySet()) =
        CullingGrid(bounds).cullPhotos(perSource, max, picks)

    // --- priority ---------------------------------------------------------

    @Test
    fun devicePhotosComeFirst() {
        val out = cull(
            mapOf(
                "device" to listOf(photo("d1", "device", hash = "h1")),
                "hillview" to listOf(photo("h1", "hillview", hash = "h2")),
            ),
            max = 1,
        )
        assertEquals(listOf("device"), out.map { it.source })
    }

    @Test
    fun hillviewFillsInOnceTheBudgetAllows() {
        val out = cull(
            mapOf(
                "device" to listOf(photo("d1", "device", 50.09, 14.31, hash = "h1")),
                "hillview" to listOf(photo("h1", "hillview", 50.01, 14.39, hash = "h2")),
            ),
            max = 200,
        )
        assertEquals(setOf("device", "hillview"), out.map { it.source }.toSet())
    }

    @Test
    fun mapillaryComesLast() {
        val out = cull(
            mapOf(
                "mapillary" to listOf(photo("m1", "mapillary")),
                "other" to listOf(photo("o1", "other")),
            ),
            max = 1,
        )
        assertEquals(listOf("other"), out.map { it.source })
    }

    @Test
    fun unknownSourcesTieBreakOnTheirId() {
        // Neither is in the priority table; the tie must not fall to
        // whichever the caller happened to insert first.
        val zeta = "zeta" to listOf(photo("z1", "zeta"))
        val alpha = "alpha" to listOf(photo("a1", "alpha"))
        assertEquals(listOf("alpha"), cull(mapOf(zeta, alpha), max = 1).map { it.source })
        assertEquals(listOf("alpha"), cull(mapOf(alpha, zeta), max = 1).map { it.source })
    }

    // --- md5 twins --------------------------------------------------------

    @Test
    fun twinsInOneCellCollapseToOne() {
        val out = cull(
            mapOf(
                "device" to listOf(photo("d1", "device", hash = "same")),
                "hillview" to listOf(photo("h1", "hillview", hash = "same")),
            ),
            max = 100,
        )
        assertEquals(1, out.size)
    }

    @Test
    fun differentHashesBothSurvive() {
        val out = cull(
            mapOf(
                "device" to listOf(photo("d1", "device", 50.09, 14.31, hash = "h1")),
                "hillview" to listOf(photo("h1", "hillview", 50.01, 14.39, hash = "h2")),
            ),
            max = 200,
        )
        assertEquals(2, out.size)
    }

    @Test
    fun photosWithoutAHashAreNeverCollapsed() {
        val out = cull(
            mapOf(
                "device" to listOf(photo("d1", "device", 50.09, 14.31)),
                "hillview" to listOf(photo("h1", "hillview", 50.01, 14.39, hash = "h1")),
            ),
            max = 200,
        )
        assertEquals(2, out.size)
    }

    // --- distribution -----------------------------------------------------

    @Test
    fun spreadsAcrossCells() {
        val out = cull(
            mapOf(
                "device" to listOf(
                    photo("d1", "device", 50.09, 14.31, hash = "h1"),
                    photo("d2", "device", 50.01, 14.39, hash = "h2"),
                ),
            ),
            max = 2,
        )
        assertEquals(setOf("d1", "d2"), out.map { it.id }.toSet())
    }

    @Test
    fun aCrowdedCellYieldsOnePhotoPerRound() {
        val out = cull(
            mapOf(
                "device" to listOf(
                    photo("d1", "device", hash = "h1"),
                    photo("d2", "device", hash = "h2"),
                    photo("d3", "device", hash = "h3"),
                ),
            ),
            max = 1,
        )
        assertEquals(listOf("d1"), out.map { it.id })
    }

    @Test
    fun devicePhotosInACellPreferTheNewest() {
        val out = cull(
            mapOf(
                "device" to listOf(
                    photo("old", "device", capturedAt = 1_000L),
                    photo("new", "device", capturedAt = 9_000L),
                ),
            ),
            max = 1,
        )
        assertEquals(listOf("new"), out.map { it.id })
    }

    @Test
    fun picksAlwaysSurvive() {
        val crowd = (1..50).map { photo("c$it", "hillview") }
        val out = cull(
            mapOf("hillview" to crowd + photo("chosen", "hillview")),
            max = 3,
            picks = setOf("hillview-chosen"),
        )
        assertTrue(out.any { it.id == "chosen" })
        assertEquals(3, out.size)
    }

    // --- edges ------------------------------------------------------------

    @Test
    fun noSourcesIsNoPhotos() {
        assertEquals(emptyList(), cull(emptyMap(), max = 10))
    }

    @Test
    fun aZeroBudgetIsNoPhotos() {
        assertEquals(emptyList(), cull(mapOf("device" to listOf(photo("d1", "device"))), max = 0))
    }

    @Test
    fun photosOutsideTheBoundsLandInAnEdgeCell() {
        // Same as the TS twin: bounds shape the grid, they do not filter.
        val out = cull(mapOf("device" to listOf(photo("far", "device", 60.0, 20.0))), max = 100)
        assertEquals(listOf("far"), out.map { it.id })
    }

    // --- the property the incremental pipeline needs ----------------------

    private fun spread(source: String, n: Int, seed: Int) = (0 until n).map { i ->
        // A deterministic scatter over the viewport, different per source.
        val lat = 50.0 + ((i * 7 + seed) % 100) / 1000.0
        val lng = 14.3 + ((i * 13 + seed) % 100) / 1000.0
        photo("$source$i", source, lat, lng, hash = "$source-$i")
    }

    @Test
    fun theResultDoesNotDependOnWhichSourceArrivedFirst() {
        val hillview = "hillview" to spread("hillview", 60, 3)
        val panoramax = "panoramax" to spread("panoramax", 60, 11)
        val mapillary = "mapillary" to spread("mapillary", 60, 29)

        val abc = cull(mapOf(hillview, panoramax, mapillary), max = 40)
        val cba = cull(mapOf(mapillary, panoramax, hillview), max = 40)
        val bac = cull(mapOf(panoramax, hillview, mapillary), max = 40)

        assertEquals(40, abc.size)
        assertEquals(abc.map { it.uid }, cba.map { it.uid })
        assertEquals(abc.map { it.uid }, bac.map { it.uid })
    }

    @Test
    fun anIntermediateCullLeavesNoTraceOnTheNext() {
        // The composite culls {A}, then {A,B} when B lands. The grid must
        // hold no state between calls: the second cull equals a fresh one.
        val hillview = "hillview" to spread("hillview", 60, 3)
        val mapillary = "mapillary" to spread("mapillary", 60, 29)
        val grid = CullingGrid(bounds)

        grid.cullPhotos(mapOf(hillview), 40)
        val second = grid.cullPhotos(mapOf(hillview, mapillary), 40)
        val fresh = CullingGrid(bounds).cullPhotos(mapOf(hillview, mapillary), 40)

        assertEquals(fresh.map { it.uid }, second.map { it.uid })
    }
}
