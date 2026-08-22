package cz.hillview.auth

import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import kotlinx.coroutines.runBlocking
import org.junit.Assume.assumeTrue
import java.net.HttpURLConnection
import java.net.URI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Contract tests against the real backend (docker compose, localhost:8055),
 * using the standard dev test account. Skipped (JUnit assumption) when the
 * backend isn't running, so `jvmTest` stays green offline.
 */
class BackendAuthIntegrationTest {

    // Full API URL, per project convention (never assembled from a host).
    private val apiUrl = System.getenv("HILLVIEW_BACKEND") ?: "http://localhost:8055/api"

    private fun backendUp(): Boolean = try {
        val conn = URI("$apiUrl/debug").toURL().openConnection() as HttpURLConnection
        conn.connectTimeout = 2_000
        conn.readTimeout = 2_000
        conn.responseCode == 200
    } catch (e: Exception) {
        false
    }

    private fun api() = AuthApi(createHttpClient(), BackendConfig(apiUrl))

    @Test
    fun loginMeRefreshRoundTrip() {
        assumeTrue("backend not running at $apiUrl", backendUp())
        runBlocking {
            val api = api()
            val token = api.token("test", "StrongTestPassword123!")
            assertTrue(token.accessToken.isNotBlank())
            assertNotNull(token.refreshToken, "backend should issue a refresh token")

            val user = api.me(token.accessToken)
            assertEquals("test", user.username)
            assertTrue(user.isActive)

            val refreshed = api.refresh(token.refreshToken!!)
            assertTrue(refreshed.accessToken.isNotBlank())

            // The refreshed access token must be honored.
            val user2 = api.me(refreshed.accessToken)
            assertEquals("test", user2.username)
        }
    }

    @Test
    fun wrongPasswordIsDefinitive() {
        assumeTrue("backend not running at $apiUrl", backendUp())
        runBlocking {
            assertFailsWith<InvalidCredentialsException> {
                api().token("test", "definitely-wrong-password")
            }
        }
    }

    @Test
    fun bogusRefreshTokenIsSessionExpiry() {
        assumeTrue("backend not running at $apiUrl", backendUp())
        runBlocking {
            assertFailsWith<SessionExpiredException> {
                api().refresh("not-a-real-refresh-token")
            }
        }
    }
}
