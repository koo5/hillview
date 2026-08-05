package cz.hillview.auth.ui

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.runComposeUiTest
import cz.hillview.auth.AuthApi
import cz.hillview.auth.InMemoryTokenStore
import cz.hillview.auth.LoginViewModel
import cz.hillview.auth.SessionManager
import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.client.engine.mock.respond
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Desktop-JVM Compose UI tests: real screens, fake backend — the layer that
 * inherits the Playwright suite's role for app UI flows.
 */
@OptIn(ExperimentalTestApi::class)
class LoginScreenTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private fun viewModelWith(engine: MockEngine): LoginViewModel {
        val api = AuthApi(createHttpClient(engine), BackendConfig("http://test"))
        return LoginViewModel(SessionManager(api, InMemoryTokenStore()))
    }

    @Test
    fun rejectedCredentialsShowError() = runComposeUiTest {
        val engine = MockEngine {
            respond("""{"detail":"nope"}""", HttpStatusCode.Unauthorized, jsonHeaders)
        }
        setContent {
            LoginScreen(onBack = {}, onLoggedIn = {}, viewModel = viewModelWith(engine))
        }

        onNodeWithTag("login-username").performTextInput("test")
        onNodeWithTag("login-password").performTextInput("wrong")
        onNodeWithTag("login-submit").performClick()

        waitUntil(timeoutMillis = 5_000) {
            onAllNodesWithTag("login-error").fetchSemanticsNodes().isNotEmpty()
        }
    }

    @Test
    fun successfulLoginInvokesCallback() = runComposeUiTest {
        val engine = MockEngine { request ->
            when {
                request.url.encodedPath.endsWith("/token") -> respond(
                    """{"access_token":"a1","refresh_token":"r1","token_type":"bearer",
                       "expires_at":"2026-08-04T13:00:00Z"}""",
                    HttpStatusCode.OK,
                    jsonHeaders,
                )
                else -> respond(
                    """{"id":"u1","email":"t@e.c","username":"test","is_active":true,
                       "is_test":true,"role":"user","created_at":"2026-01-01T00:00:00Z"}""",
                    HttpStatusCode.OK,
                    jsonHeaders,
                )
            }
        }
        var loggedIn = false
        setContent {
            LoginScreen(onBack = {}, onLoggedIn = { loggedIn = true }, viewModel = viewModelWith(engine))
        }

        onNodeWithTag("login-username").performTextInput("test")
        onNodeWithTag("login-password").performTextInput("StrongTestPassword123!")
        onNodeWithTag("login-submit").performClick()

        waitUntil(timeoutMillis = 5_000) { loggedIn }
        assertTrue(loggedIn)
    }
}
