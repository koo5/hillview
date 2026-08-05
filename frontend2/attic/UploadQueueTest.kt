package cz.hillview.upload

import cz.hillview.auth.AuthApi
import cz.hillview.auth.InMemoryTokenStore
import cz.hillview.auth.SessionManager
import cz.hillview.auth.StoredTokens
import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.fail

/**
 * Deterministic ports of the old app's upload chaos/resilience Appium specs
 * (chaos-photos-recovery, chaos-worker-upload-recovery, upload-queue-offline,
 * session-expiry-reconcile) as fault-injection tests over the queue core.
 */
class UploadQueueTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private class FakeSigner : UploadSigner {
        override val keyId = "key_test"
        override val publicKeyPem = "-----BEGIN PUBLIC KEY-----\nTEST\n-----END PUBLIC KEY-----\n"
        override val createdAtIso = "2026-08-04T00:00:00Z"
        override fun sign(payload: String) = "sig($payload)"
    }

    private class Rig(loggedIn: Boolean = true) {
        val handlers = ArrayDeque<suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData>()
        val engine = MockEngine { request ->
            val h = handlers.removeFirstOrNull()
                ?: fail("unexpected request: ${request.method.value} ${request.url}")
            h(this, request)
        }
        val http = createHttpClient(engine)
        val session = SessionManager(
            AuthApi(http, BackendConfig("http://test")),
            InMemoryTokenStore(
                if (loggedIn) StoredTokens("a1", "r1", username = "test") else null
            ),
        )
        val store = InMemoryQueueStore()
        val files = mutableMapOf("p1" to ByteArray(10) { 1 }, "p2" to ByteArray(10) { 2 })
        val queue = UploadQueue(
            store = store,
            api = PhotoUploadApi(http, BackendConfig("http://test"), session),
            signer = FakeSigner(),
            readFile = { path -> files[path] ?: error("no file $path") },
        )

        suspend fun start() {
            session.restoreIfNeeded()
        }
    }

    private fun entry(id: String) = PendingUpload(id = id, filePath = id, filename = "$id.jpg")

    private fun MockRequestHandleScope.ok(body: String) = respond(body, HttpStatusCode.OK, jsonHeaders)
    private fun authJson(photoId: String) =
        """{"upload_jwt":"jwt-$photoId","photo_id":"$photoId","worker_url":"http://worker",
           "expires_at":"2026-08-04T13:00:00Z","upload_authorized_at":1754300000}"""

    @Test
    fun happyPathUploadsAllPending() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1")); rig.queue.enqueue(entry("p2"))

        rig.handlers.addLast { ok("{}") }                         // register key
        rig.handlers.addLast { ok(authJson("ph1")) }              // authorize p1
        rig.handlers.addLast { ok("""{"fly_machine_id":"m1"}""") } // ready
        rig.handlers.addLast { ok("""{"success":true}""") }        // upload p1
        rig.handlers.addLast { ok(authJson("ph2")) }
        rig.handlers.addLast { ok("""{"fly_machine_id":"m1"}""") }
        rig.handlers.addLast { ok("""{"success":true}""") }

        rig.queue.drain()

        val states = rig.queue.entries().map { it.state }
        assertEquals(listOf(UploadState.Done, UploadState.Done), states)
        assertEquals(0, rig.queue.stats.value.pending)
        assertEquals(2, rig.queue.stats.value.done)
    }

    @Test
    fun transientFailureKeepsEntryAndContinues() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1")); rig.queue.enqueue(entry("p2"))

        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { respond("boom", HttpStatusCode.InternalServerError, jsonHeaders) } // authorize p1
        rig.handlers.addLast { ok(authJson("ph2")) }              // p2 proceeds
        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { ok("""{"success":true}""") }

        rig.queue.drain()

        val byId = rig.queue.entries().associateBy { it.id }
        assertEquals(UploadState.Pending, byId.getValue("p1").state)
        assertEquals(1, byId.getValue("p1").attempts)
        assertEquals(UploadState.Done, byId.getValue("p2").state)

        // Chaos recovery: the next drain retries p1 and succeeds.
        rig.handlers.addLast { ok(authJson("ph1")) }
        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { ok("""{"success":true}""") }
        rig.queue.drain()
        assertEquals(UploadState.Done, rig.queue.entries().first { it.id == "p1" }.state)
    }

    @Test
    fun duplicateAnswerMarksEntryDuplicate() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1"))

        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast {
            ok("""{"duplicate":true,"message":"seen it","existing_photo_id":"old1",
                  "existing_filename":"p1.jpg"}""")
        }

        rig.queue.drain()

        val e = rig.queue.entries().single()
        assertEquals(UploadState.Duplicate, e.state)
        assertEquals("old1", e.photoId)
    }

    @Test
    fun definitiveRejectionParksEntry() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1"))

        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { respond("""{"detail":"bad"}""", HttpStatusCode.UnprocessableEntity, jsonHeaders) }

        rig.queue.drain()

        assertEquals(UploadState.FailedPermanent, rig.queue.entries().single().state)
    }

    @Test
    fun saturatedWorkerAbortsWholePass() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1")); rig.queue.enqueue(entry("p2"))

        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { ok(authJson("ph1")) }
        rig.handlers.addLast { respond("full", HttpStatusCode.ServiceUnavailable, jsonHeaders) } // ready 503

        rig.queue.drain()

        val byId = rig.queue.entries().associateBy { it.id }
        assertEquals(UploadState.Pending, byId.getValue("p1").state)
        assertEquals(1, byId.getValue("p1").attempts)
        // p2 was never attempted — no request burned against a full queue.
        assertEquals(UploadState.Pending, byId.getValue("p2").state)
        assertEquals(0, byId.getValue("p2").attempts)
    }

    @Test
    fun loggedOutDrainLeavesQueueIntact() = runTest {
        val rig = Rig(loggedIn = false); rig.start()
        rig.queue.enqueue(entry("p1"))

        rig.queue.drain() // no handlers: any network call would fail the test

        assertEquals(UploadState.Pending, rig.queue.entries().single().state)
        assertEquals("not logged in", rig.queue.stats.value.lastError)
    }

    @Test
    fun expiredAccessTokenRefreshesMidDrain() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1"))

        rig.handlers.addLast { ok("{}") }                                     // register (old token ok)
        rig.handlers.addLast { respond("expired", HttpStatusCode.Unauthorized, jsonHeaders) } // authorize 401
        rig.handlers.addLast {
            ok("""{"access_token":"a2","refresh_token":"r2","token_type":"bearer",
                  "expires_at":"2026-08-04T14:00:00Z"}""")                    // refresh
        }
        rig.handlers.addLast { ok(authJson("ph1")) }                          // authorize retry
        rig.handlers.addLast { ok("{}") }
        rig.handlers.addLast { ok("""{"success":true}""") }

        rig.queue.drain()

        assertEquals(UploadState.Done, rig.queue.entries().single().state)
    }

    @Test
    fun queueSurvivesRestart() = runTest {
        val rig = Rig(); rig.start()
        rig.queue.enqueue(entry("p1"))

        // "Process death": a new queue over the same store still sees it.
        val revived = UploadQueue(
            store = rig.store,
            api = PhotoUploadApi(rig.http, BackendConfig("http://test"), rig.session),
            signer = FakeSigner(),
            readFile = { rig.files.getValue(it) },
        )
        assertEquals(UploadState.Pending, revived.entries().single().state)
    }
}
