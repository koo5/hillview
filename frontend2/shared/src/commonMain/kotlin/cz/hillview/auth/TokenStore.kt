package cz.hillview.auth

/**
 * Persisted session tokens. On Android this is an adapter over the shared-kt
 * AuthenticationManager — the SAME store and refresher the upload stack uses
 * (one implementation, like the Tauri app: UI logs in, native owns
 * storage/refresh/key-registration). Desktop uses java.util.prefs; tests use
 * an in-memory implementation.
 */
interface TokenStore {
    suspend fun load(): StoredTokens?
    suspend fun save(tokens: StoredTokens)
    suspend fun clear()

    /**
     * A currently-valid access token from the platform's own auth manager,
     * refreshed by it if needed (Android: shared-kt AuthenticationManager,
     * process-wide refresh mutex shared with the upload stack). Null when
     * the store has no platform refresher — then SessionManager's Ktor
     * refresh path applies (desktop, tests).
     */
    suspend fun freshAccessToken(): String? = null
}

class InMemoryTokenStore(private var tokens: StoredTokens? = null) : TokenStore {
    override suspend fun load(): StoredTokens? = tokens
    override suspend fun save(tokens: StoredTokens) { this.tokens = tokens }
    override suspend fun clear() { tokens = null }
}
