package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.runTest

private class FakeSource(vararg initial: PhotoMarker) : PhotoMarkerSource {
    override val markers = MutableStateFlow(initial.toList())
    override var pinnedId: String? = null
    var lastViewport: MapViewport? = null
    var refreshes = 0

    override fun setViewport(viewport: MapViewport) {
        lastViewport = viewport
    }

    override suspend fun refresh() {
        refreshes++
    }
}

private fun marker(
    id: String,
    source: String,
    md5: String? = null,
) = PhotoMarker(
    id = id,
    latitude = 50.0,
    longitude = 14.0,
    bearingDeg = null,
    capturedAtMs = 0,
    source = source,
    fileMd5 = md5,
)

class CompositeMarkerSourceTest {

    @Test
    fun anUploadedCaptureCollapsesIntoItsBackendSelf() = runTest {
        val device = FakeSource(
            marker("local-1", "device", md5 = "same"),
            marker("local-2", "device", md5 = "only-local"),
        )
        val api = FakeSource(marker("server-1", "hillview", md5 = "same"))
        val composite = CompositeMarkerSource(listOf(device, api))
        composite.refresh()

        val ids = composite.markers.value.map { it.id }
        // The twin shows once, as the backend copy (it carries featured /
        // filtering / everyone-visible identity)…
        assertEquals(listOf("local-2", "server-1"), ids.sorted())
        // …and the winner really is the hillview one.
        assertEquals(
            "hillview",
            composite.markers.value.first { it.fileMd5 == "same" }.source,
        )
    }

    @Test
    fun markersWithoutAHashNeverCollapse() = runTest {
        val device = FakeSource(marker("a", "device"), marker("b", "device"))
        val api = FakeSource(marker("c", "hillview"))
        val composite = CompositeMarkerSource(listOf(device, api))
        composite.refresh()
        assertEquals(3, composite.markers.value.size)
    }

    @Test
    fun pinAndViewportFanOutToEverySource() = runTest {
        val device = FakeSource()
        val api = FakeSource()
        val composite = CompositeMarkerSource(listOf(device, api))

        composite.pinnedId = "picked"
        assertEquals("picked", device.pinnedId)
        assertEquals("picked", api.pinnedId)

        val viewport = MapViewport(50.1, 14.3, 50.0, 14.5)
        composite.setViewport(viewport)
        assertEquals(viewport, device.lastViewport)
        assertEquals(viewport, api.lastViewport)

        composite.refresh()
        assertEquals(1, device.refreshes)
        assertEquals(1, api.refreshes)
    }
}
