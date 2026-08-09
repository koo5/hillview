package cz.hillview.auth.ui

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.auth.AuthApi
import cz.hillview.auth.CredentialGateway
import cz.hillview.auth.InMemoryTokenStore
import cz.hillview.auth.LoginViewModel
import cz.hillview.auth.SavedCredential
import cz.hillview.auth.SessionManager
import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The CredentialGateway seam through the login screen: the passive
 * saved-password offer, save-on-success, and the native Google path —
 * fake gateway, fake backend, real screen.
 */
@OptIn(ExperimentalTestApi::class)
class CredentialLoginTest {

    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

    private class FakeGateway(
        var saved: SavedCredential? = null,
        var googleToken: String? = null,
        override val googleAvailable: Boolean = googleToken != null,
    ) : CredentialGateway {
        val savedBack = mutableListOf<SavedCredential>()
        override suspend fun getSavedPassword(): SavedCredential? = saved
        override suspend fun savePassword(username: String, password: String) {
            savedBack += SavedCredential(username, password)
        }
        override suspend fun googleIdToken(): String? = googleToken
    }

    private fun okBackend() = MockEngine { request ->
        when {
            request.url.encodedPath.endsWith("/token") ||
                request.url.encodedPath.endsWith("/google/native") -> respond(
                """{"access_token":"a1","refresh_token":"r1","token_type":"bearer",
                   "expires_at":"2026-08-04T13:00:00Z"}""",
                HttpStatusCode.OK,
                jsonHeaders,
            )
            else -> respond(
                """{"id":"u1","email":"t@e.c","username":"native","is_active":true,
                   "is_test":true,"role":"user"}""",
                HttpStatusCode.OK,
                jsonHeaders,
            )
        }
    }

    private fun viewModelWith(engine: MockEngine, gateway: CredentialGateway): LoginViewModel {
        val api = AuthApi(createHttpClient(engine), BackendConfig("http://test"))
        return LoginViewModel(SessionManager(api, InMemoryTokenStore()), gateway)
    }

    @Test
    fun aSavedCredentialSignsInWithoutAKeystrokeAndIsNotSavedBack() = runComposeUiTest {
        val gateway = FakeGateway(saved = SavedCredential("test", "StrongTestPassword123!"))
        var loggedIn = false
        setContent {
            LoginScreen(
                onBack = {},
                onLoggedIn = { loggedIn = true },
                viewModel = viewModelWith(okBackend(), gateway),
            )
        }
        waitUntil(timeoutMillis = 5_000) { loggedIn }
        // It came FROM the provider — offering to save it again would nag.
        assertTrue(gateway.savedBack.isEmpty())
    }

    @Test
    fun aManualLoginOffersTheProviderTheCredential() = runComposeUiTest {
        val gateway = FakeGateway(saved = null)
        var loggedIn = false
        setContent {
            LoginScreen(
                onBack = {},
                onLoggedIn = { loggedIn = true },
                viewModel = viewModelWith(okBackend(), gateway),
            )
        }
        onNodeWithTag("login-username").performTextInput("test")
        onNodeWithTag("login-password").performTextInput("pw")
        onNodeWithTag("login-submit").performClick()
        waitUntil(timeoutMillis = 5_000) { loggedIn }
        assertEquals(listOf(SavedCredential("test", "pw")), gateway.savedBack)
    }

    @Test
    fun theGoogleButtonOnlyExistsWhenConfigured() = runComposeUiTest {
        setContent {
            LoginScreen(
                onBack = {},
                onLoggedIn = {},
                viewModel = viewModelWith(okBackend(), FakeGateway(googleToken = null)),
            )
        }
        assertTrue(onAllNodesWithTag("continue-with-google").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun theGoogleTokenBuysASession() = runComposeUiTest {
        val gateway = FakeGateway(googleToken = "gid-token-1")
        var loggedIn = false
        setContent {
            LoginScreen(
                onBack = {},
                onLoggedIn = { loggedIn = true },
                viewModel = viewModelWith(okBackend(), gateway),
            )
        }
        onNodeWithTag("continue-with-google").performClick()
        waitUntil(timeoutMillis = 5_000) { loggedIn }
    }

    @Test
    fun aDismissedGoogleSheetIsNotAnError() = runComposeUiTest {
        val gateway = object : CredentialGateway {
            override val googleAvailable = true
            override suspend fun getSavedPassword(): SavedCredential? = null
            override suspend fun savePassword(username: String, password: String) {}
            override suspend fun googleIdToken(): String? = null
        }
        setContent {
            LoginScreen(
                onBack = {},
                onLoggedIn = {},
                viewModel = viewModelWith(okBackend(), gateway),
            )
        }
        onNodeWithTag("continue-with-google").performClick()
        waitUntil(timeoutMillis = 2_000) {
            onAllNodesWithTag("login-submit").fetchSemanticsNodes().isNotEmpty()
        }
        // No error surfaced, the form is still usable.
        assertTrue(onAllNodesWithTag("login-error").fetchSemanticsNodes().isEmpty())
    }
}
