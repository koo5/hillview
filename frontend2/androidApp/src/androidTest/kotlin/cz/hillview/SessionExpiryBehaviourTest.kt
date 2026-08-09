package cz.hillview

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.auth.AuthApi
import cz.hillview.auth.SessionManager
import cz.hillview.auth.SessionState
import cz.hillview.auth.TokenStore
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * Session expiry reconciled across app death — the port of
 * session-expiry-reconcile.test.ts. The chain under test: a refresh
 * definitively rejected (401) makes the shared-kt AuthenticationManager
 * clear the tokens, PERSIST the expired flag, and fire the lockstep
 * callback; the UI drops to logged-out with the "session has expired"
 * notice; and the persisted flag alone must resurface the notice on the
 * next launch, even when the live callback was never delivered.
 *
 * Process death itself is out of instrumentation's reach (the Appium layer
 * had it) — the next-launch path is exercised the way settings persistence
 * does it: a FRESH SessionManager over the same store, whose
 * restoreIfNeeded() IS the startup reconciler. Backend down → the test
 * SKIPS (Assume), like the other backend-needing port.
 */
@RunWith(AndroidJUnit4::class)
class SessionExpiryBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.POST_NOTIFICATIONS,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    @Before
    fun requireBackend() {
        val code = Behaviour.post("http://10.0.2.2:8055/api/debug/recreate-test-users")
        assumeTrue("dev backend not reachable from the emulator (got $code)", code == 200)
    }

    @After
    fun clearTheFlagForOtherTests() {
        try {
            runBlocking {
                GlobalContext.get().get<SessionManager>().dismissSessionExpiredNotice()
            }
        } catch (_: Exception) {
            // best effort — the flag is also superseded by any later login
        }
    }

    @Test
    fun expiryIsPersistedAndTheStartupReconcilerSurfacesIt() {
        compose.loginThroughTheUi()

        // Invalidate the session server-side: access AND refresh now 401.
        val code = Behaviour.post(
            "http://10.0.2.2:8055/api/internal/debug/force-logout-user",
            """{"username": "test", "clear": false}""",
        )
        assertEquals("force-logout-user failed", 200, code)

        // Force the native refresh — the shared-kt manager meets the 401,
        // clears tokens, persists the flag, and fires the lockstep callback.
        val store = GlobalContext.get().get<TokenStore>()
        val refreshed = runBlocking { store.forceRefresh() }
        assertEquals("the forced refresh must be definitively rejected", false, refreshed)

        // The Appium checkpoint, probe-without-consuming: the death is
        // persisted BEFORE any relaunch — that is the whole premise.
        val reason = runBlocking { store.peekSessionExpiredReason() }
        assertNotNull("expired flag must be persisted at the choke point", reason)

        // Live lockstep: the Main page shows the persistent notice with the
        // asserted phrase, and the menu drops to signed-out.
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("session-expired-notice")
                .fetchSemanticsNodes().isNotEmpty()
        }
        val notice = compose.onNodeWithTag("session-expired-notice")
            .fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text)
            ?.joinToString(" ") { it.text } ?: ""
        assertTrue("got: $notice", notice.contains("session has expired"))
        compose.openMenu()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("menu-login-button")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.closeMenu()

        // The next launch, from the persisted flag alone: a fresh
        // SessionManager (the startup reconciler) over the same store.
        val fresh = SessionManager(
            GlobalContext.get().get<AuthApi>(),
            store,
        )
        runBlocking { fresh.restoreIfNeeded() }
        assertEquals(SessionState.LoggedOut, fresh.state.value)
        assertNotNull(
            "the startup reconciler must surface the persisted expiry",
            fresh.sessionExpiredNotice.value,
        )
    }
}
