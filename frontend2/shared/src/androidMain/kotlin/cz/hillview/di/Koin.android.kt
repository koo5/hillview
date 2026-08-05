package cz.hillview.di

import android.content.Context
import cz.hillview.auth.StoredTokens
import cz.hillview.auth.TokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.Module
import org.koin.dsl.module

/**
 * The Android token store IS the shared-kt AuthenticationManager (prefs
 * "hillview_auth") — the same store and process-wide refresh mutex the
 * upload stack uses. Mirrors the Tauri architecture: UI performs the login
 * call, native owns storage, refresh and client-key registration
 * (storeAuthToken registers the key; 409 = already registered). Only the
 * username — pure UI state — lives in a side pref.
 */
private class AuthManagerTokenStore(context: Context) : TokenStore {
    private val auth = cz.hillview.plugin.AuthenticationManager(context)
    private val uiPrefs = context.getSharedPreferences("hillview_session", Context.MODE_PRIVATE)

    override suspend fun load(): StoredTokens? = withContext(Dispatchers.IO) {
        val (token, expiresAt) = auth.getTokenInfo()
        if (token == null) return@withContext null
        StoredTokens(
            accessToken = token,
            refreshToken = auth.getRefreshToken(),
            expiresAt = expiresAt,
            refreshTokenExpiresAt = auth.getRefreshTokenExpiresAt(),
            username = uiPrefs.getString("username", null),
        )
    }

    override suspend fun save(tokens: StoredTokens) = withContext(Dispatchers.IO) {
        uiPrefs.edit().putString("username", tokens.username).apply()
        val expiresAt = tokens.expiresAt
        if (expiresAt == null) {
            // The backend's Token model always carries expires_at; without it
            // the native store can't manage the session.
            android.util.Log.e("HillviewTokenStore", "no expires_at on login token — session not persisted")
            return@withContext
        }
        val result = auth.storeAuthToken(
            tokens.accessToken,
            expiresAt,
            tokens.refreshToken,
            tokens.refreshTokenExpiresAt,
        )
        if (!result.success) {
            android.util.Log.w("HillviewTokenStore", "client-key registration failed: ${result.error}")
        }
    }

    override suspend fun clear(): Unit = withContext(Dispatchers.IO) {
        uiPrefs.edit().remove("username").apply()
        auth.clearAuthToken()
    }

    override suspend fun freshAccessToken(): String? = withContext(Dispatchers.IO) {
        auth.getValidToken()
    }

    override suspend fun consumeSessionExpiredReason(): String? = withContext(Dispatchers.IO) {
        val info = auth.getSessionExpiredInfo() ?: return@withContext null
        auth.clearSessionExpiredFlag()
        info.second
    }
}

actual fun platformModule(): Module = module {
    // Eager: construction materializes hillview_upload_prefs defaults, which
    // must exist before first login (client-key registration reads server_url).
    single<cz.hillview.settings.UploadSettingsRepository>(createdAtStart = true) {
        cz.hillview.settings.PrefsUploadSettingsRepository(
            androidContext(),
            cz.hillview.settings.defaultUploadSettings(cz.hillview.core.net.defaultBackendConfig().apiUrl),
        )
    }
    single<TokenStore> { AuthManagerTokenStore(androidContext()) }
    // Captures go to the shared-kt upload stack — the same code the Tauri
    // app runs. See /shared-kt/README.md.
    single<cz.hillview.upload.UploadPipeline> {
        cz.hillview.upload.SharedStackUploadPipeline(androidContext())
    }
}
