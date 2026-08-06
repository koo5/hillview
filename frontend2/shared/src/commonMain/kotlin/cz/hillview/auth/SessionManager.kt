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

    /**
     * One-shot involuntary-death notice ("session expired: refresh token
     * rejected"), surfaced by the UI until dismissed or the user logs in
     * again. Fed from the platform auth manager's persisted flag (restore)
     * and its live callback (see [onPlatformSessionExpired]).
     */
    private val _sessionExpiredNotice = MutableStateFlow<String?>(null)
    val sessionExpiredNotice: StateFlow<String?> = _sessionExpiredNotice.asStateFlow()

    private var tokens: StoredTokens? = null
    private val refreshMutex = Mutex()
    private var restored = false

    /** Idempotent; called once at app start. */
    suspend fun restoreIfNeeded() {
        if (restored) return
        restored = true
        // Surface an involuntary death that happened while the UI was gone
        // (background drain hit a definitive 401) — mirrors the Tauri app's
        // JS reconciler reading the same persisted flag.
        store.peekSessionExpiredReason()?.let { _sessionExpiredNotice.value = it }
        val stored = store.load()
        tokens = stored
        _state.value = if (stored != null) {
            SessionState.LoggedIn(stored.username)
        } else {
            SessionState.LoggedOut
        }
    }

    /**
     * Live push from the platform auth manager's session-death choke point
     * (Android wires AuthenticationManager.onSessionExpired to this): tokens
     * are already cleared natively — drop the UI state in lockstep.
     */
    suspend fun onPlatformSessionExpired() {
        _sessionExpiredNotice.value =
            store.peekSessionExpiredReason() ?: "session expired"
        tokens = null
        _state.value = SessionState.LoggedOut
    }

    suspend fun dismissSessionExpiredNotice() {
        _sessionExpiredNotice.value = null
        store.acknowledgeSessionExpired()
    }

    /**
     * Throws [InvalidCredentialsException] or [TransientBackendException].
     */
    suspend fun login(username: String, password: String) {
        val token = api.token(username, password)
        _sessionExpiredNotice.value = null // superseded by the new session
        store.acknowledgeSessionExpired()
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
     * When the store has a platform refresher (Android), its token wins —
     * it may have rotated the session underneath us.
     */
    suspend fun <T> authorized(block: suspend (accessToken: String) -> T): T {
        val t = tokens ?: throw NotLoggedInException()
        val platformToken = store.freshAccessToken()
        return try {
            block(platformToken ?: t.accessToken)
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
            // A platform refresher (shared-kt AuthenticationManager on
            // Android) may have rotated the store underneath us — adopt its
            // tokens instead of replaying our now-spent refresh token, which
            // strict single-use rotation would treat as theft and answer by
            // revoking the whole session.
            val storedNow = store.load()
            if (storedNow != null && storedNow.accessToken != current.accessToken) {
                tokens = storedNow
                return
            }

            // Where a platform refresher exists (Android), IT owns refreshing:
            // it serializes with the upload stack on a process-wide mutex, so
            // the stored refresh token is never presented twice. Running our
            // own Ktor refresh alongside it would race — and the backend
            // answers a replayed single-use refresh token by revoking the
            // whole session.
            val platformRefreshed = store.forceRefresh()
            if (platformRefreshed != null) {
                val after = store.load()
                if (platformRefreshed && after != null) {
                    tokens = after
                    return
                }
                // Failed. The platform manager clears tokens only on a
                // definitive rejection; surviving tokens mean 5xx/IO, which
                // must NOT log the user out.
                if (after == null) {
                    tokens = null
                    _state.value = SessionState.LoggedOut
                    _sessionExpiredNotice.value =
                        store.peekSessionExpiredReason() ?: "session expired"
                    throw SessionExpiredException("platform refresh rejected")
                }
                tokens = after
                throw TransientBackendException("platform refresh failed (session kept)")
            }

            val refreshToken = current.refreshToken
                ?: throw SessionExpiredException("no refresh token")
            val newToken = try {
                api.refresh(refreshToken)
            } catch (e: SessionExpiredException) {
                // Definitive: the session is over.
                tokens = null
                store.clear()
                _state.value = SessionState.LoggedOut
                _sessionExpiredNotice.value = e.message ?: "session expired"
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
