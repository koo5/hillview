package cz.hillview.auth

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

sealed interface SessionState {
    /** Before restore() has looked at the token store. */
    data object Unknown : SessionState
    data object LoggedOut : SessionState
    data class LoggedIn(val username: String?) : SessionState
}

/**
 * The auth state machine. Rules carried over from the old app's Appium specs
 * (native-refresh-5xx-keeps-session, native-transient-refresh-keeps-session,
 * session-expiry-reconcile):
 *
 *  - a 401 on an authorized call triggers ONE refresh + retry;
 *  - refresh failing with 5xx/network trouble is TRANSIENT: tokens are kept,
 *    the session stays logged in, the call fails with
 *    [TransientBackendException];
 *  - refresh rejected with 401/403 is DEFINITIVE: tokens are cleared and the
 *    state drops to LoggedOut.
 */
class SessionManager(
    private val api: AuthApi,
    private val store: TokenStore,
) {
    private val _state = MutableStateFlow<SessionState>(SessionState.Unknown)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    private var tokens: StoredTokens? = null
    private val refreshMutex = Mutex()
    private var restored = false

    /** Idempotent; called once at app start. */
    suspend fun restoreIfNeeded() {
        if (restored) return
        restored = true
        val stored = store.load()
        tokens = stored
        _state.value = if (stored != null) {
            SessionState.LoggedIn(stored.username)
        } else {
            SessionState.LoggedOut
        }
    }

    /**
     * Throws [InvalidCredentialsException] or [TransientBackendException].
     */
    suspend fun login(username: String, password: String) {
        val token = api.token(username, password)
        val stored = StoredTokens(
            accessToken = token.accessToken,
            refreshToken = token.refreshToken,
            expiresAt = token.expiresAt,
            refreshTokenExpiresAt = token.refreshTokenExpiresAt,
            username = username,
        )
        tokens = stored
        store.save(stored)
        _state.value = SessionState.LoggedIn(username)
        // Best-effort profile fetch; the session is valid regardless.
        try {
            val user = api.me(token.accessToken)
            val enriched = stored.copy(username = user.username)
            tokens = enriched
            store.save(enriched)
            _state.value = SessionState.LoggedIn(user.username)
        } catch (e: Exception) {
            // ignore — username from the form is good enough
        }
    }

    suspend fun logout() {
        val t = tokens
        tokens = null
        store.clear()
        _state.value = SessionState.LoggedOut
        if (t != null) {
            try {
                api.logout(t.accessToken)
            } catch (e: Exception) {
                // best-effort; local logout already happened
            }
        }
    }

    /**
     * Runs [block] with a valid access token, refreshing once on 401.
     */
    suspend fun <T> authorized(block: suspend (accessToken: String) -> T): T {
        val t = tokens ?: throw NotLoggedInException()
        return try {
            block(t.accessToken)
        } catch (e: UnauthorizedException) {
            refresh()
            val fresh = tokens ?: throw SessionExpiredException("logged out during refresh")
            block(fresh.accessToken)
        }
    }

    /**
     * Refresh with failure classification; see class docs. Serialized so
     * concurrent 401s produce a single refresh.
     */
    suspend fun refresh() {
        val before = tokens ?: throw NotLoggedInException()
        refreshMutex.withLock {
            val current = tokens ?: throw SessionExpiredException("logged out")
            // Another caller already refreshed while we waited.
            if (current.accessToken != before.accessToken) return
            val refreshToken = current.refreshToken
                ?: throw SessionExpiredException("no refresh token")
            val newToken = try {
                api.refresh(refreshToken)
            } catch (e: SessionExpiredException) {
                // Definitive: the session is over.
                tokens = null
                store.clear()
                _state.value = SessionState.LoggedOut
                throw e
            }
            // (TransientBackendException propagates with tokens intact.)
            val stored = current.copy(
                accessToken = newToken.accessToken,
                refreshToken = newToken.refreshToken ?: current.refreshToken,
                expiresAt = newToken.expiresAt,
                refreshTokenExpiresAt = newToken.refreshTokenExpiresAt
                    ?: current.refreshTokenExpiresAt,
            )
            tokens = stored
            store.save(stored)
        }
    }

    /** Current access token, if logged in — for services that manage their own retry. */
    fun currentAccessToken(): String? = tokens?.accessToken
}
