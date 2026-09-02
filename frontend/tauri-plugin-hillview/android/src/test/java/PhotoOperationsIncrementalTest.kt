package cz.hillview.plugin

import android.content.Context
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.mockito.Mockito

/**
 * processArea loads every enabled source concurrently and hands each one's
 * photos to onSourcePhotos as they land — the map fills in per source instead
 * of after the slowest one.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PhotoOperationsIncrementalTest {

    private val bounds = Bounds(LatLng(50.1, 14.3), LatLng(50.0, 14.4))

    private fun photo(id: String, source: String) = PhotoData(
        id = id, uid = "$source-$id", source_type = "stream",
        coord = LatLng(50.05, 14.35), bearing = 0.0, source = source
    )

    private fun stream(id: String) = SourceConfig(id = id, name = id, type = "stream", enabled = true, color = "#000", url = "https://x/$id")
    private fun device() = SourceConfig(id = "device", name = "Device", type = "device", enabled = true, color = "#0f0")

    /** A stream whose completion (and batches) the test controls per source. */
    private class GatedStream : StreamLoading {
        val done = mutableMapOf<String, CompletableDeferred<List<PhotoData>>>()
        val batch = mutableMapOf<String, (List<PhotoData>) -> Unit>()
        fun gate(id: String) = done.getOrPut(id) { CompletableDeferred() }

        override suspend fun load(
            source: SourceConfig, bounds: Bounds?, maxPhotos: Int, authToken: String?, shouldAbort: () -> Boolean,
            picks: Set<String>, queryOptionsJson: String?, onBatch: ((List<PhotoData>) -> Unit)?
        ): List<PhotoData> {
            batch[source.id] = onBatch ?: {}
            return gate(source.id).await()
        }
    }

    private class GatedDevice : DeviceLoading {
        val done = CompletableDeferred<List<PhotoData>>()
        override suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, picks: Set<String>) = done.await()
    }

    private object NoPanoramax : PanoramaxLoading {
        override suspend fun load(source: SourceConfig, bounds: Bounds?, maxPhotos: Int, shouldAbort: () -> Boolean, hillviewBackendUrl: String?, authToken: String?) = emptyList<PhotoData>()
    }

    private class Harness(stream: GatedStream, device: GatedDevice = GatedDevice()) {
        val ops = PhotoOperations(
            context = Mockito.mock(Context::class.java),
            deviceLoader = device, streamLoader = stream, panoramaxLoader = NoPanoramax,
            backendUrlProvider = { null }
        )
        val arrivals = mutableListOf<Pair<String, List<String>>>()
        val status = mutableListOf<Triple<String, Boolean, String?>>()  // source, isLoading, error
        var abort = false

        suspend fun run(sources: List<SourceConfig>) = ops.processArea(
            processId = "p", sources = sources, bounds = Bounds(LatLng(50.1, 14.3), LatLng(50.0, 14.4)),
            shouldAbort = { abort }, authTokenProvider = { null },
            onSourceLoadingStatus = { id, loading, _, error -> status += Triple(id, loading, error) },
            onSourcePhotos = { id, photos -> arrivals += id to photos.map { it.id } }
        )
    }

    @Test
    fun aFastSourceIsDeliveredBeforeTheSlowOneCompletes() = runTest {
        val stream = GatedStream()
        val h = Harness(stream)
        var result: Map<String, List<PhotoData>>? = null
        launch { result = h.run(listOf(stream("hillview"), stream("mapillary"))) }
        runCurrent()

        // Both sources are in flight at once…
        assertEquals(setOf("hillview", "mapillary"), stream.done.keys)
        assertTrue(h.status.containsAll(listOf(Triple("hillview", true, null), Triple("mapillary", true, null))))

        // …and hillview landing is reported while mapillary is still open.
        stream.gate("hillview").complete(listOf(photo("h1", "hillview")))
        runCurrent()
        assertEquals(listOf("hillview" to listOf("h1")), h.arrivals)
        assertNull("area not settled while mapillary is loading", result)
        assertTrue(h.status.contains(Triple("hillview", false, null)))

        stream.gate("mapillary").complete(listOf(photo("m1", "mapillary")))
        runCurrent()
        assertEquals(setOf("hillview", "mapillary"), result!!.keys)
        assertEquals(listOf("hillview" to listOf("h1"), "mapillary" to listOf("m1")), h.arrivals)
    }

    @Test
    fun streamBatchesAreDeliveredBeforeTheStreamCompletes() = runTest {
        val stream = GatedStream()
        val h = Harness(stream)
        launch { h.run(listOf(stream("mapillary"))) }
        runCurrent()

        stream.batch.getValue("mapillary")(listOf(photo("m1", "mapillary")))
        stream.batch.getValue("mapillary")(listOf(photo("m1", "mapillary"), photo("m2", "mapillary")))
        assertEquals(listOf("mapillary" to listOf("m1"), "mapillary" to listOf("m1", "m2")), h.arrivals)

        stream.gate("mapillary").complete(listOf(photo("m1", "mapillary"), photo("m2", "mapillary")))
        runCurrent()
        assertEquals(3, h.arrivals.size)
    }

    @Test
    fun aFailingSourceNeitherBlanksNorBlocksTheOthers() = runTest {
        val stream = GatedStream()
        val h = Harness(stream)
        var result: Map<String, List<PhotoData>>? = null
        launch { result = h.run(listOf(stream("hillview"), stream("mapillary"))) }
        runCurrent()

        stream.gate("mapillary").completeExceptionally(RuntimeException("boom"))
        runCurrent()
        assertTrue(h.status.any { it.first == "mapillary" && !it.second && it.third == "Error: boom" })
        assertNull("hillview is still loading; the failure did not end the area", result)

        stream.gate("hillview").complete(listOf(photo("h1", "hillview")))
        runCurrent()
        assertEquals(listOf("hillview" to listOf("h1")), h.arrivals)
        assertEquals(setOf("hillview"), result!!.keys)
    }

    @Test
    fun aSupersededAreaDeliversNothingThatArrivesAfterTheAbort() = runTest {
        val stream = GatedStream()
        val h = Harness(stream)
        var result: Map<String, List<PhotoData>>? = null
        launch { result = h.run(listOf(stream("hillview"), stream("mapillary"))) }
        runCurrent()

        stream.gate("hillview").complete(listOf(photo("h1", "hillview")))
        runCurrent()
        assertEquals(1, h.arrivals.size)

        h.abort = true
        stream.batch.getValue("mapillary")(listOf(photo("late", "mapillary")))
        stream.gate("mapillary").complete(listOf(photo("late", "mapillary")))
        runCurrent()

        assertEquals("the late batch and completion were dropped", 1, h.arrivals.size)
        assertFalse(result!!.containsKey("mapillary"))
    }

    @Test
    fun theDeviceSourceLoadsAlongsideTheStreams() = runTest {
        val stream = GatedStream()
        val device = GatedDevice()
        val h = Harness(stream, device)
        launch { h.run(listOf(device(), stream("hillview"))) }
        runCurrent()

        device.done.complete(listOf(photo("d1", "device")))
        runCurrent()
        assertEquals(listOf("device" to listOf("d1")), h.arrivals)
        assertTrue(h.status.contains(Triple("hillview", true, null)))

        stream.gate("hillview").complete(emptyList())
        runCurrent()
        assertEquals(listOf("device" to listOf("d1"), "hillview" to emptyList()), h.arrivals)
    }
}
