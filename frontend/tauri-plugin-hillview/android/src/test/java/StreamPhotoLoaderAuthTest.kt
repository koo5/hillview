package cz.hillview.plugin

import kotlinx.coroutines.test.runTest
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The stream loader sends the access token as an Authorization header, never in
 * the URL, and answers a 401 with exactly one retry on a token the session was
 * refreshed for. An OkHttp interceptor plays the server, so no socket opens.
 */
class StreamPhotoLoaderAuthTest {

    /** Answers each request with the next scripted status; 200 streams one photo. */
    private class FakeServer(vararg statuses: Int) : Interceptor {
        private val script = statuses.toMutableList()
        val requests = mutableListOf<Request>()

        override fun intercept(chain: Interceptor.Chain): Response {
            val request = chain.request()
            requests += request
            val code = if (script.isEmpty()) 200 else script.removeAt(0)
            val ok = code == 200
            return Response.Builder()
                .request(request)
                .protocol(Protocol.HTTP_1_1)
                .code(code)
                .message(if (ok) "OK" else "Error")
                .body(
                    (if (ok) SSE_BODY else """{"detail":"Invalid authentication token"}""")
                        .toResponseBody((if (ok) "text/event-stream" else "application/json").toMediaType())
                )
                .build()
        }
    }

    private class CountingRefresher(private val token: String?) {
        var calls = 0
        val fn: suspend () -> String? = { calls++; token }
    }

    private fun loader(server: FakeServer) =
        StreamPhotoLoader(OkHttpClient.Builder().addInterceptor(server).build())

    private suspend fun StreamPhotoLoader.load(token: String?, refresher: (suspend () -> String?)? = null) =
        loadPhotos(SOURCE, BOUNDS, 10, token, { false }, refreshAuthToken = refresher)

    private suspend fun failureOf(block: suspend () -> Unit): Throwable? =
        try { block(); null } catch (e: Throwable) { e }

    @Test
    fun theTokenTravelsInTheAuthorizationHeaderNotTheUrl() = runTest {
        val server = FakeServer(200)
        val photos = loader(server).load("tok")

        assertEquals(listOf("p1"), photos.map { it.id })
        assertEquals("Bearer tok", server.requests.single().header("Authorization"))
        assertNull(server.requests.single().url.queryParameter("token"))
    }

    @Test
    fun noTokenSendsNoAuthorizationHeader() = runTest {
        val server = FakeServer(200)
        loader(server).load(null)

        assertNull(server.requests.single().header("Authorization"))
    }

    @Test
    fun a401IsRetriedOnceWithARefreshedToken() = runTest {
        val server = FakeServer(401, 200)
        val refresher = CountingRefresher("fresh")
        val photos = loader(server).load("stale", refresher.fn)

        assertEquals(listOf("p1"), photos.map { it.id })
        assertEquals(1, refresher.calls)
        assertEquals(listOf("Bearer stale", "Bearer fresh"), server.requests.map { it.header("Authorization") })
    }

    @Test
    fun a401WithoutARefresherFailsAtOnce() = runTest {
        val server = FakeServer(401)
        val failure = failureOf { loader(server).load("stale") }

        assertTrue(failure is StreamHttpException)
        assertEquals(401, (failure as StreamHttpException).code)
        assertEquals(1, server.requests.size)
    }

    @Test
    fun aPersistent401GivesUpAfterOneRefresh() = runTest {
        val server = FakeServer(401, 401)
        val refresher = CountingRefresher("still-bad")
        val failure = failureOf { loader(server).load("stale", refresher.fn) }

        assertEquals(401, (failure as StreamHttpException).code)
        assertEquals(1, refresher.calls)
        assertEquals(2, server.requests.size)
    }

    @Test
    fun otherHttpErrorsAreNotRetried() = runTest {
        val server = FakeServer(422)
        val refresher = CountingRefresher("fresh")
        val failure = failureOf { loader(server).load("tok", refresher.fn) }

        assertEquals(422, (failure as StreamHttpException).code)
        assertEquals(0, refresher.calls)
        assertEquals(1, server.requests.size)
    }

    private companion object {
        const val SSE_BODY =
            "data: {\"type\":\"photos\",\"photos\":[{\"id\":\"p1\",\"geometry\":{\"coordinates\":[14.5,50.5]},\"bearing\":10}]}\n\n" +
                "data: {\"type\":\"stream_complete\"}\n\n"
        val SOURCE = SourceConfig(
            id = "hillview", name = "Hillview", type = "stream", enabled = true,
            color = "#000000", url = "https://example.test/api/hillview",
        )
        val BOUNDS = Bounds(top_left = LatLng(51.0, 14.0), bottom_right = LatLng(50.0, 15.0))
    }
}
