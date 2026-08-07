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

    override suspend fun forceRefresh(): Boolean = withContext(Dispatchers.IO) {
        // Unconditional refresh under the shared process-wide mutex — this is
        // the path the native manager documents for HTTP callers that got a
        // 401 on a locally-valid token.
        auth.forceRefreshToken()
    }

    override suspend fun peekSessionExpiredReason(): String? = withContext(Dispatchers.IO) {
        auth.getSessionExpiredInfo()?.second
    }

    override suspend fun acknowledgeSessionExpired() {
        withContext(Dispatchers.IO) { auth.clearSessionExpiredFlag() }
    }
}

actual fun platformModule(): Module = module {
    // Native auth: Credential Manager + Sign in with Google, behind the
    // common CredentialGateway seam (config in NativeAuthConfig, set by
    // HillviewApplication from BuildConfig).
    single<cz.hillview.auth.CredentialGateway> {
        cz.hillview.auth.AndroidCredentialGateway(androidContext())
    }
    // Eager: construction materializes hillview_upload_prefs defaults, which
    // must exist before first login (client-key registration reads server_url).
    single<cz.hillview.settings.UploadSettingsRepository>(createdAtStart = true) {
        cz.hillview.settings.PrefsUploadSettingsRepository(
            androidContext(),
            cz.hillview.settings.defaultUploadSettings(cz.hillview.core.net.defaultBackendConfig().apiUrl),
        )
    }
    single<cz.hillview.settings.CompassSettingsRepository> {
        cz.hillview.settings.PrefsCompassSettingsRepository(androidContext())
    }
    single<cz.hillview.settings.MapSettingsRepository> {
        cz.hillview.settings.PrefsMapSettingsRepository(androidContext())
    }
    single<cz.hillview.map.MapStateStore> { cz.hillview.map.PrefsMapStateStore(androidContext()) }
    // Device photos + the backend's viewport query — both through the
    // shared-kt photo-worker loaders (the Tauri app's Kotlin code) — deduped
    // by content hash (an uploaded capture shows once, as its backend self).
    single<cz.hillview.map.PhotoMarkerSource> {
        val tokenStore = get<TokenStore>()
        cz.hillview.map.CompositeMarkerSource(
            listOf(
                cz.hillview.map.DeviceMarkerSource(androidContext(), get()),
                cz.hillview.map.StreamMarkerSource(
                    source = cz.hillview.plugin.SourceConfig(
                        id = "hillview",
                        name = "Hillview",
                        type = "stream",
                        enabled = true,
                        color = "#000000",
                        url = "${get<cz.hillview.core.net.BackendConfig>().apiUrl}/hillview",
                    ),
                    settings = get(),
                    freshToken = { tokenStore.freshAccessToken() },
                ),
            ),
        )
    }
    single<TokenStore> { AuthManagerTokenStore(androidContext()) }
    single<cz.hillview.devicephotos.DevicePhotoBrowser> {
        cz.hillview.devicephotos.DaoDevicePhotoBrowser(androidContext())
    }
    // Captures go to the shared-kt upload stack — the same code the Tauri
    // app runs. See /shared-kt/README.md.
    single<cz.hillview.upload.UploadPipeline> {
        cz.hillview.upload.SharedStackUploadPipeline(androidContext())
    }
}
