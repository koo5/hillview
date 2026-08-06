package cz.hillview.di

import cz.hillview.auth.StoredTokens
import cz.hillview.auth.TokenStore
import cz.hillview.core.net.backendJson
import org.koin.core.module.Module
import org.koin.dsl.module
import java.util.prefs.Preferences

private class JavaPrefsTokenStore : TokenStore {
    private val node = Preferences.userRoot().node("cz/hillview/frontend2")

    override suspend fun load(): StoredTokens? =
        node.get("tokens", null)?.let {
            try {
                backendJson.decodeFromString(StoredTokens.serializer(), it)
            } catch (e: Exception) {
                null
            }
        }

    override suspend fun save(tokens: StoredTokens) {
        node.put("tokens", backendJson.encodeToString(StoredTokens.serializer(), tokens))
    }

    override suspend fun clear() {
        node.remove("tokens")
    }
}

actual fun platformModule(): Module = module {
    single<cz.hillview.settings.UploadSettingsRepository> {
        cz.hillview.settings.JavaPrefsUploadSettingsRepository(
            cz.hillview.settings.defaultUploadSettings(cz.hillview.core.net.defaultBackendConfig().apiUrl),
        )
    }
    single<cz.hillview.settings.CompassSettingsRepository> {
        cz.hillview.settings.JavaPrefsCompassSettingsRepository()
    }
    single<TokenStore> { JavaPrefsTokenStore() }
    // Desktop can't capture, so there is no upload path here.
    single<cz.hillview.upload.UploadPipeline> { cz.hillview.upload.NoopUploadPipeline() }
}
