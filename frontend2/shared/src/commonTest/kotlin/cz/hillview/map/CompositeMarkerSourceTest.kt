package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest

private class FakeSource(vararg initial: PhotoMarker) : PhotoMarkerSource {
    override var descriptor: MapSourceDescriptor? = null
    override val markers = MutableStateFlow(initial.toList())
    override var pinnedId: String? = null
    var lastViewport: MapViewport? = null
    var refreshes = 0

    /** When set, refresh() waits on it: the test decides when this source answers. */
    var gate: CompletableDeferred<Unit>? = null

    /** What refresh() publishes once through the gate; null leaves the set alone. */
    var answer: List<PhotoMarker>? = null
    var failWith: Exception? = null

    override fun setViewport(viewport: MapViewport) {
        lastViewport = viewport
    }

    override suspend fun refresh() {
        refreshes++
        gate?.await()
        failWith?.let { throw it }
        answer?.let { markers.value = it }
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

private val viewport = MapViewport(50.1, 14.3, 50.0, 14.5)

/**
 * Runs everything due, through one publish cooldown. Not settle():
 * that stops once only BACKGROUND work is left, and the composite runs
 * entirely in the background scope.
 */
private fun TestScope.settle() {
    advanceTimeBy(CompositeMarkerSource.PUBLISH_THROTTLE_MS + 1)
    runCurrent()
}

/** Sources under test, run on the test's virtual clock. */
private fun TestScope.composite(
    vararg sources: PhotoMarkerSource,
    maxPhotos: Int = Int.MAX_VALUE,
) = CompositeMarkerSource(
    sources = sources.toList(),
    scope = backgroundScope,
    maxPhotos = { maxPhotos },
)

class CompositeMarkerSourceTest {

    @Test
    fun anUploadedCaptureCollapsesIntoItsBackendSelf() = runTest {
        val device = FakeSource(
            marker("local-1", "device", md5 = "same"),
            marker("local-2", "device", md5 = "only-local"),
        )
        val api = FakeSource(marker("server-1", "hillview", md5 = "same"))
        val composite = composite(device, api)
        composite.refresh()
        settle()

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
        val composite = composite(device, api)
        composite.refresh()
        settle()
        assertEquals(3, composite.markers.value.size)
    }

    @Test
    fun pinAndViewportFanOutToEverySource() = runTest {
        val device = FakeSource()
        val api = FakeSource()
        val composite = composite(device, api)

        composite.pinnedId = "picked"
        assertEquals("picked", device.pinnedId)
        assertEquals("picked", api.pinnedId)

        composite.setViewport(viewport)
        assertEquals(viewport, device.lastViewport)
        assertEquals(viewport, api.lastViewport)

        composite.refresh()
        assertEquals(1, device.refreshes)
        assertEquals(1, api.refreshes)
    }

    @Test
    fun aDisabledSourceNeitherShowsNorSpends() = runTest {
        val device = FakeSource(marker("a", "device")).apply {
            descriptor = MapSourceDescriptor("device", "Device")
        }
        val api = FakeSource(marker("c", "hillview")).apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
        }
        val composite = composite(device, api)
        composite.refresh()
        settle()
        assertEquals(2, composite.markers.value.size)

        // Toggling off hides from the cached sets without a fetch…
        composite.setSourceEnabled("hillview", false)
        runCurrent()
        assertEquals(listOf("a"), composite.markers.value.map { it.id })

        // …and the next refresh doesn't spend network on it.
        composite.refresh()
        assertEquals(2, device.refreshes)
        assertEquals(1, api.refreshes)

        // Back on: cached markers return without waiting for a refresh.
        composite.setSourceEnabled("hillview", true)
        runCurrent()
        assertEquals(2, composite.markers.value.size)
    }

    @Test
    fun descriptorDefaultsGateUntouchedSources() = runTest {
        val off = FakeSource(marker("m", "mapillary")).apply {
            descriptor = MapSourceDescriptor("mapillary", "Mapillary", defaultEnabled = false)
        }
        val composite = composite(off)
        composite.refresh()
        settle()
        // Never toggled: the original's default-off sources stay dark.
        assertEquals(0, composite.markers.value.size)
        assertEquals(0, off.refreshes)
    }

    // --- sources arrive on their own time --------------------------------

    @Test
    fun aFastSourceShowsBeforeASlowOneAnswers() = runTest {
        val device = FakeSource().apply {
            descriptor = MapSourceDescriptor("device", "Device")
            answer = listOf(marker("a", "device"))
        }
        val api = FakeSource().apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            gate = CompletableDeferred()
            answer = listOf(marker("c", "hillview"))
        }
        val composite = composite(device, api)

        backgroundScope.launch { composite.refresh() }
        runCurrent()
        // Device answered; hillview is still on the wire — and the map
        // already has the device markers.
        assertEquals(listOf("a"), composite.markers.value.map { it.id })
        assertEquals(setOf("hillview"), composite.loading.value)

        api.gate!!.complete(Unit)
        settle()
        assertEquals(listOf("a", "c"), composite.markers.value.map { it.id })
        assertTrue(composite.loading.value.isEmpty(), "settled")
    }

    @Test
    fun aFailingSourceKeepsItsLastSetAndNeverBlanksTheOthers() = runTest {
        val device = FakeSource().apply {
            descriptor = MapSourceDescriptor("device", "Device")
            answer = listOf(marker("a", "device"))
        }
        val api = FakeSource(marker("stale", "hillview")).apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            failWith = IllegalStateException("backend down")
        }
        val composite = composite(device, api)
        composite.refresh()
        settle()

        assertEquals(listOf("a", "stale"), composite.markers.value.map { it.id })
        assertTrue(composite.loading.value.isEmpty(), "a failure still settles")
    }

    @Test
    fun aCancelledCallerLosesNothingAlreadyPublished() = runTest {
        val device = FakeSource().apply {
            descriptor = MapSourceDescriptor("device", "Device")
            answer = listOf(marker("a", "device"))
        }
        val api = FakeSource().apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            gate = CompletableDeferred()
            answer = listOf(marker("c", "hillview"))
        }
        val composite = composite(device, api)

        // The map's collectLatest: the caller is cancelled mid-wait.
        val caller = launch { composite.refresh() }
        runCurrent()
        assertEquals(listOf("a"), composite.markers.value.map { it.id })
        caller.cancel()
        runCurrent()

        // What was on the map stays, and the fetch in flight belongs to the
        // composite, not the caller — it still lands.
        assertEquals(listOf("a"), composite.markers.value.map { it.id })
        api.gate!!.complete(Unit)
        settle()
        assertEquals(listOf("a", "c"), composite.markers.value.map { it.id })
    }

    @Test
    fun aToggleMidStreamDoesNotRestartTheStream() = runTest {
        val device = FakeSource().apply {
            descriptor = MapSourceDescriptor("device", "Device")
            answer = listOf(marker("a", "device"))
        }
        val api = FakeSource().apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            gate = CompletableDeferred()
        }
        val composite = composite(device, api)
        composite.setViewport(viewport)

        backgroundScope.launch { composite.refresh() }
        runCurrent()
        // The map's second caller: a source toggled while hillview streams.
        composite.setSourceEnabled("device", false)
        backgroundScope.launch { composite.refresh() }
        runCurrent()

        assertEquals(1, api.refreshes, "same viewport, same pin: the stream is left alone")
        assertEquals(1, device.refreshes, "disabled: not started again")
        // Mid-load, the toggle rides the cooldown like any other change.
        settle()
        assertEquals(emptyList(), composite.markers.value.map { it.id })

        api.gate!!.complete(Unit)
        settle()
    }

    @Test
    fun aNewViewportRestartsAStaleFetch() = runTest {
        val api = FakeSource().apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            gate = CompletableDeferred()
        }
        val composite = composite(api)
        composite.setViewport(viewport)
        backgroundScope.launch { composite.refresh() }
        runCurrent()
        assertEquals(1, api.refreshes)

        composite.setViewport(MapViewport(51.1, 15.3, 51.0, 15.5))
        backgroundScope.launch { composite.refresh() }
        runCurrent()
        assertEquals(2, api.refreshes, "the fetch for the old viewport is replaced")

        api.gate!!.complete(Unit)
        settle()
        assertTrue(composite.loading.value.isEmpty())
    }

    // --- the publish policy ----------------------------------------------

    @Test
    fun publishesAreThrottledWhileLoadingAndFlushedOnSettle() = runTest {
        val device = FakeSource().apply {
            descriptor = MapSourceDescriptor("device", "Device")
            answer = listOf(marker("a", "device"))
        }
        val api = FakeSource().apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
            gate = CompletableDeferred()
        }
        val composite = composite(device, api)

        backgroundScope.launch { composite.refresh() }
        runCurrent()
        // First arrival: at once.
        assertEquals(listOf("a"), composite.markers.value.map { it.id })

        // A batch lands while the stream is open: held for the cooldown…
        api.markers.value = listOf(marker("c1", "hillview"))
        runCurrent()
        assertEquals(listOf("a"), composite.markers.value.map { it.id })
        // …and published on its trailing edge.
        advanceTimeBy(CompositeMarkerSource.PUBLISH_THROTTLE_MS)
        runCurrent()
        assertEquals(listOf("a", "c1"), composite.markers.value.map { it.id })

        // The last batch and stream_complete: settling ends the cooldown
        // early, so the final set is not held for another 300 ms.
        api.markers.value = listOf(marker("c1", "hillview"), marker("c2", "hillview"))
        runCurrent()
        assertEquals(listOf("a", "c1"), composite.markers.value.map { it.id })
        api.gate!!.complete(Unit)
        runCurrent()
        assertEquals(listOf("a", "c1", "c2"), composite.markers.value.map { it.id })
        assertTrue(composite.loading.value.isEmpty())
    }

    @Test
    fun anIdleMapPublishesToggleAtOnce() = runTest {
        val device = FakeSource(marker("a", "device")).apply {
            descriptor = MapSourceDescriptor("device", "Device")
        }
        val api = FakeSource(marker("c", "hillview")).apply {
            descriptor = MapSourceDescriptor("hillview", "Hillview")
        }
        val composite = composite(device, api)
        composite.refresh()
        settle()

        // Nothing loading: no cooldown stands between a toggle and the map.
        composite.setSourceEnabled("hillview", false)
        runCurrent()
        assertEquals(listOf("a"), composite.markers.value.map { it.id })
        composite.setSourceEnabled("hillview", true)
        runCurrent()
        assertEquals(listOf("a", "c"), composite.markers.value.map { it.id })
    }

    // --- the budget is cross-source --------------------------------------

    @Test
    fun theBudgetHoldsAcrossSources() = runTest {
        val device = FakeSource(*(1..5).map { marker("d$it", "device") }.toTypedArray())
        val api = FakeSource(*(1..5).map { marker("h$it", "hillview") }.toTypedArray())
        val composite = composite(device, api, maxPhotos = 3)
        composite.setViewport(viewport)
        composite.refresh()
        settle()
        assertEquals(3, composite.markers.value.size)
    }

    @Test
    fun thePinSurvivesTheBudget() = runTest {
        val api = FakeSource(*(1..5).map { marker("h$it", "hillview") }.toTypedArray())
        val composite = composite(api, maxPhotos = 1)
        composite.setViewport(viewport)
        composite.pinnedId = "h5"
        composite.refresh()
        settle()
        assertEquals(listOf("h5"), composite.markers.value.map { it.id })
    }

    @Test
    fun theFinalSetDoesNotDependOnWhoAnsweredFirst() = runTest {
        suspend fun TestScope.run(apiFirst: Boolean): List<String> {
            val device = FakeSource().apply {
                descriptor = MapSourceDescriptor("device", "Device")
                gate = CompletableDeferred()
                answer = (1..4).map { marker("d$it", "device", md5 = "m$it") }
            }
            val api = FakeSource().apply {
                descriptor = MapSourceDescriptor("hillview", "Hillview")
                gate = CompletableDeferred()
                // Two twins of device photos among its own.
                answer = listOf(marker("s2", "hillview", md5 = "m2"), marker("s9", "hillview", md5 = "m9"), marker("s3", "hillview", md5 = "m3"))
            }
            val composite = composite(device, api, maxPhotos = 5)
            composite.setViewport(viewport)
            backgroundScope.launch { composite.refresh() }
            runCurrent()
            (if (apiFirst) api else device).gate!!.complete(Unit)
            settle()
            (if (apiFirst) device else api).gate!!.complete(Unit)
            settle()
            return composite.markers.value.map { "${it.source}:${it.id}" }
        }

        assertEquals(run(apiFirst = false), run(apiFirst = true))
    }
}
