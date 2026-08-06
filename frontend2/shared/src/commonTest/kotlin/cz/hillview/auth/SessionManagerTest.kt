package cz.hillview.auth

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
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.fail

/**
 * The auth state machine, tested against scripted backend behavior. The
 * transient-vs-definitive refresh scenarios are deterministic ports of the
 * old app's Appium specs (native-refresh-5xx-keeps-session,
 * native-transient-refresh-keeps-session, session-expiry cases).
 */
class SessionManagerTest {

    private class Scripted {
        val handlers = ArrayDeque<suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData>()
        val engine = MockEngine { request ->
            val handler = handlers.removeFirstOrNull()
                ?: fail("unexpected request: ${request.method.value} ${request.url}")
            handler(request)
        }

        fun enqueue(handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData) {
            handlers.addLast(handler)
        }
    }

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private fun tokenJson(access: String, refresh: String? = "r1") = """
        {"access_token":"$access","refresh_token":${refresh?.let { "\"$it\"" } ?: "null"},
         "token_type":"bearer","expires_at":"2026-08-04T13:00:00Z"}
    """.trimIndent()

    private val meJson = """
        {"id":"u1","email":"test@example.com","username":"test",
         "is_active":true,"is_test":true,"role":"user","created_at":"2026-01-01T00:00:00Z"}
    """.trimIndent()

    private fun sessionWith(scripted: Scripted, store: TokenStore = InMemoryTokenStore()): SessionManager {
        val api = AuthApi(createHttpClient(scripted.engine), BackendConfig("http://test"))
        return SessionManager(api, store)
    }

    @Test
    fun loginSuccessStoresTokensAndFetchesProfile() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore()
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()
        assertEquals(SessionState.LoggedOut, session.state.value)

        scripted.enqueue { respond(tokenJson("a1"), HttpStatusCode.OK, jsonHeaders) }
        scripted.enqueue { respond(meJson, HttpStatusCode.OK, jsonHeaders) }

        session.login("test", "pw")

        assertEquals(SessionState.LoggedIn("test"), session.state.value)
        val stored = store.load()
        assertNotNull(stored)
        assertEquals("a1", stored.accessToken)
        assertEquals("r1", stored.refreshToken)
    }

    @Test
    fun loginRejectedThrowsAndStaysLoggedOut() = runTest {
        val scripted = Scripted()
        val session = sessionWith(scripted)
        session.restoreIfNeeded()

        scripted.enqueue { respond("""{"detail":"bad"}""", HttpStatusCode.Unauthorized, jsonHeaders) }

        assertFailsWith<InvalidCredentialsException> { session.login("test", "wrong") }
        assertEquals(SessionState.LoggedOut, session.state.value)
    }

    @Test
    fun loginBackendDownIsTransient() = runTest {
        val scripted = Scripted()
        val session = sessionWith(scripted)
        session.restoreIfNeeded()

        scripted.enqueue { respond("oops", HttpStatusCode.InternalServerError, jsonHeaders) }

        assertFailsWith<TransientBackendException> { session.login("test", "pw") }
        assertEquals(SessionState.LoggedOut, session.state.value)
    }

    @Test
    fun authorizedRefreshesOnceOn401AndRetries() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore(StoredTokens("stale", "r1", username = "test"))
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()
        assertEquals(SessionState.LoggedIn("test"), session.state.value)

        scripted.enqueue { respond(tokenJson("fresh", "r2"), HttpStatusCode.OK, jsonHeaders) }

        var attempts = 0
        val result = session.authorized { token ->
            attempts++
            if (token == "stale") throw UnauthorizedException("401")
            "ok:$token"
        }

        assertEquals("ok:fresh", result)
        assertEquals(2, attempts)
        assertEquals("fresh", store.load()?.accessToken)
        assertEquals("r2", store.load()?.refreshToken)
    }

    @Test
    fun refresh5xxKeepsSession() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore(StoredTokens("stale", "r1", username = "test"))
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        scripted.enqueue { respond("boom", HttpStatusCode.InternalServerError, jsonHeaders) }

        assertFailsWith<TransientBackendException> {
            session.authorized { throw UnauthorizedException("401") }
        }
        // The session survives; tokens are intact for a later retry.
        assertIs<SessionState.LoggedIn>(session.state.value)
        assertEquals("stale", store.load()?.accessToken)
    }

    @Test
    fun refreshRejectedLogsOutAndClearsStore() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore(StoredTokens("stale", "r1", username = "test"))
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        scripted.enqueue { respond("""{"detail":"invalid"}""", HttpStatusCode.Unauthorized, jsonHeaders) }

        assertFailsWith<SessionExpiredException> {
            session.authorized { throw UnauthorizedException("401") }
        }
        assertEquals(SessionState.LoggedOut, session.state.value)
        assertNull(store.load())
    }

    @Test
    fun restoreFromStoreNeedsNoNetwork() = runTest {
        val scripted = Scripted() // no handlers: any request would fail the test
        val store = InMemoryTokenStore(StoredTokens("a1", "r1", username = "koo"))
        val session = sessionWith(scripted, store)

        session.restoreIfNeeded()

        assertEquals(SessionState.LoggedIn("koo"), session.state.value)
    }

    @Test
    fun logoutClearsLocalStateEvenIfServerCallFails() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore(StoredTokens("a1", "r1", username = "test"))
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        scripted.enqueue { respond("down", HttpStatusCode.ServiceUnavailable, jsonHeaders) }

        session.logout()

        assertEquals(SessionState.LoggedOut, session.state.value)
        assertNull(store.load())
    }

    /**
     * Stands in for Android's AuthManagerTokenStore: a store that owns
     * refreshing. [rotateTo] null means the refresh fails; [clearOnFailure]
     * distinguishes a definitive rejection (native side cleared the session)
     * from transient trouble (tokens survive).
     */
    private class PlatformRefresherStore(
        private var tokens: StoredTokens?,
        private val rotateTo: StoredTokens?,
        private val clearOnFailure: Boolean = false,
    ) : TokenStore {
        var refreshCalls = 0
            private set

        override suspend fun load(): StoredTokens? = tokens
        override suspend fun save(tokens: StoredTokens) { this.tokens = tokens }
        override suspend fun clear() { tokens = null }
        override suspend fun freshAccessToken(): String? = tokens?.accessToken

        override suspend fun forceRefresh(): Boolean {
            refreshCalls++
            if (rotateTo != null) {
                tokens = rotateTo
                return true
            }
            if (clearOnFailure) tokens = null
            return false
        }

        override suspend fun consumeSessionExpiredReason(): String? =
            if (tokens == null && clearOnFailure) "refresh token rejected (401)" else null
    }

    @Test
    fun refreshDelegatesToPlatformRefresherAndAdoptsItsTokens() = runTest {
        // No scripted handler enqueued: any Ktor /auth/refresh call would fail
        // the test — proving the second refresher never runs.
        val scripted = Scripted()
        val store = PlatformRefresherStore(
            tokens = StoredTokens("a1", "r1", username = "test"),
            rotateTo = StoredTokens("a2", "r2", username = "test"),
        )
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        session.refresh()

        assertEquals(1, store.refreshCalls)
        assertEquals(SessionState.LoggedIn("test"), session.state.value)
        assertEquals("a2", store.load()?.accessToken)
        // The adopted token is what subsequent authorized calls use.
        val used = session.authorized { token -> token }
        assertEquals("a2", used)
    }

    @Test
    fun platformRefreshFailureKeepsSessionWhenTokensSurvive() = runTest {
        // Transient (5xx/IO): the native manager leaves the session intact.
        val scripted = Scripted()
        val store = PlatformRefresherStore(
            tokens = StoredTokens("a1", "r1", username = "test"),
            rotateTo = null,
            clearOnFailure = false,
        )
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        assertFailsWith<TransientBackendException> { session.refresh() }

        assertEquals(SessionState.LoggedIn("test"), session.state.value)
        assertNotNull(store.load())
        assertNull(session.sessionExpiredNotice.value)
    }

    @Test
    fun platformRefreshRejectionLogsOut() = runTest {
        // Definitive (401): the native manager already cleared the session.
        val scripted = Scripted()
        val store = PlatformRefresherStore(
            tokens = StoredTokens("a1", "r1", username = "test"),
            rotateTo = null,
            clearOnFailure = true,
        )
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        assertFailsWith<SessionExpiredException> { session.refresh() }

        assertEquals(SessionState.LoggedOut, session.state.value)
        assertEquals("refresh token rejected (401)", session.sessionExpiredNotice.value)
    }

    @Test
    fun restoreSurfacesPersistedSessionExpiryOnce() = runTest {
        // The platform auth manager killed the session while the UI was gone
        // (background drain, definitive 401): tokens gone, flag persisted.
        val scripted = Scripted()
        val store = InMemoryTokenStore(
            tokens = null,
            expiredReason = "refresh token rejected (401)",
        )
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()

        assertEquals(SessionState.LoggedOut, session.state.value)
        assertEquals("refresh token rejected (401)", session.sessionExpiredNotice.value)
        // Consumed from the store — a fresh manager would not see it again.
        assertNull(store.consumeSessionExpiredReason())

        // A successful login supersedes the notice.
        scripted.enqueue { respond(tokenJson("a2"), HttpStatusCode.OK, jsonHeaders) }
        scripted.enqueue { respond(meJson, HttpStatusCode.OK, jsonHeaders) }
        session.login("test", "pw")
        assertNull(session.sessionExpiredNotice.value)
    }

    @Test
    fun platformSessionExpiryDropsStateInLockstep() = runTest {
        val scripted = Scripted()
        val store = InMemoryTokenStore(StoredTokens("a1", "r1", username = "test"))
        val session = sessionWith(scripted, store)
        session.restoreIfNeeded()
        assertEquals(SessionState.LoggedIn("test"), session.state.value)

        // Live callback path: the native side already cleared its store.
        session.onPlatformSessionExpired()

        assertEquals(SessionState.LoggedOut, session.state.value)
        assertNotNull(session.sessionExpiredNotice.value)
    }
}
