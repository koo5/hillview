package cz.hillview.auth

/**
 * Persisted session tokens. Platform-backed (SharedPreferences on Android,
 * java.util.prefs on desktop); tests use an in-memory implementation.
 */
interface TokenStore {
    suspend fun load(): StoredTokens?
    suspend fun save(tokens: StoredTokens)
    suspend fun clear()
}

class InMemoryTokenStore(private var tokens: StoredTokens? = null) : TokenStore {
    override suspend fun load(): StoredTokens? = tokens
    override suspend fun save(tokens: StoredTokens) { this.tokens = tokens }
    override suspend fun clear() { tokens = null }
}
