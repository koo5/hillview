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
    single<cz.hillview.settings.MapSettingsRepository> { InMemoryMapSettings() }
    single<cz.hillview.map.MapStateStore> { cz.hillview.map.InMemoryMapStateStore() }
    single<cz.hillview.map.PhotoMarkerSource> { EmptyMarkerSource() }
    single<TokenStore> { JavaPrefsTokenStore() }
    single<cz.hillview.devicephotos.DevicePhotoBrowser> {
        cz.hillview.devicephotos.EmptyDevicePhotoBrowser()
    }
    // Desktop can't capture, so there is no upload path here.
    single<cz.hillview.upload.UploadPipeline> { cz.hillview.upload.NoopUploadPipeline() }
}

/** Desktop has no map yet; these keep the graph resolvable. */
private class InMemoryMapSettings : cz.hillview.settings.MapSettingsRepository {
    private val state = kotlinx.coroutines.flow.MutableStateFlow(cz.hillview.settings.MapSettings())
    override val settings = state
    override fun update(transform: (cz.hillview.settings.MapSettings) -> cz.hillview.settings.MapSettings) {
        state.value = transform(state.value)
    }
}

private class EmptyMarkerSource : cz.hillview.map.PhotoMarkerSource {
    override val markers = kotlinx.coroutines.flow.MutableStateFlow(emptyList<cz.hillview.map.PhotoMarker>())
    override var pinnedId: String? = null
    override suspend fun refresh() {}
}
