package cz.hillview.settings

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** The worker override's rules (user, 2026-11-05: "i want to also be able to override worker url"). */
class WorkerEndpointsTest {

    private val base = defaultUploadSettings("https://api.example/api")
    private val pin = CertificatePin("AAAA", "AB:CD", "CN=w", "2027")

    @Test
    fun aWorkerUrlIsHttpOrHttpsWithAHost() {
        assertEquals("https://w.lan:8056", normalizeWorkerUrl("  https://w.lan:8056/ "))
        assertEquals("http://10.0.2.2:8056", normalizeWorkerUrl("http://10.0.2.2:8056"))
        assertNull(normalizeWorkerUrl("w.lan:8056"))
        assertNull(normalizeWorkerUrl("ftp://w.lan"))
        assertNull(normalizeWorkerUrl("https://"))
        assertNull(normalizeWorkerUrl("https:///path"))
        assertNull(normalizeWorkerUrl("https://w lan"))
    }

    @Test
    fun byDefaultTheServerDecides() {
        assertNull(base.activeWorker)
        assertEquals(emptyList(), base.workerEndpoints)
    }

    @Test
    fun addingAWorkerUsesItAndAddingItAgainDoesNotDuplicate() {
        val s = base.withWorkerAdded("https://w").withWorkerAdded("https://w")
        assertEquals(listOf(WorkerEndpoint("https://w")), s.workerEndpoints)
        assertEquals("https://w", s.activeWorker?.url)
    }

    @Test
    fun removingTheSelectedWorkerFallsBackToTheServer() {
        val s = base.withWorkerAdded("https://a").withWorkerAdded("https://b")
        assertEquals("https://b", s.withWorkerRemoved("https://a").activeWorker?.url)
        val gone = s.withWorkerRemoved("https://b")
        assertNull(gone.activeWorker)
        assertNull(gone.workerOverrideUrl)
    }

    @Test
    fun selectingAnUnknownUrlSelectsTheServer() {
        val s = base.withWorkerAdded("https://a")
        assertNull(s.withWorkerSelected("https://nope").workerOverrideUrl)
        assertNull(s.withWorkerSelected(null).activeWorker)
        assertEquals("https://a", s.withWorkerSelected(null).withWorkerSelected("https://a").activeWorker?.url)
    }

    @Test
    fun aPinBelongsToItsOwnWorker() {
        val s = base.withWorkerAdded("https://a").withWorkerAdded("https://b").withWorkerPin("https://a", pin)
        assertEquals(pin, s.workerEndpoints.first { it.url == "https://a" }.pin)
        assertNull(s.workerEndpoints.first { it.url == "https://b" }.pin)
        assertNull(s.withWorkerPin("https://a", null).workerEndpoints.first().pin)
    }

    @Test
    fun theListSurvivesStorageAndAGarbledOneIsDropped() {
        val list = listOf(WorkerEndpoint("https://a", pin), WorkerEndpoint("http://b"))
        assertEquals(list, decodeWorkerEndpoints(encodeWorkerEndpoints(list)))
        assertEquals(emptyList(), decodeWorkerEndpoints("{not json"))
        assertEquals(emptyList(), decodeWorkerEndpoints(null))
    }
}
