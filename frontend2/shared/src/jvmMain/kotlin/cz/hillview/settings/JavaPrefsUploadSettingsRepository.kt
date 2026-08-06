package cz.hillview.settings

import java.util.prefs.Preferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Desktop settings store. There is no upload stack on desktop (capture is
 * unsupported), but serverUrl feeds BackendConfig, and the screen works the
 * same on every platform.
 */
class JavaPrefsUploadSettingsRepository(
    defaults: UploadSettings,
) : UploadSettingsRepository {
    private val node = Preferences.userRoot().node("cz/hillview/frontend2/upload_settings")

    private val _settings = MutableStateFlow(
        UploadSettings(
            serverUrl = node.get("server_url", null) ?: defaults.serverUrl,
            autoUploadEnabled = node.getBoolean("auto_upload_enabled", defaults.autoUploadEnabled),
            wifiOnly = node.getBoolean("wifi_only", defaults.wifiOnly),
            license = node.get("auto_upload_license", null) ?: defaults.license,
            storage = StorageMode.fromKey(node.get("preferred_storage", null)) ?: defaults.storage,
            hideFromGallery = node.getBoolean("hide_from_gallery", defaults.hideFromGallery),
        ).also(::persist)
    )
    override val settings: StateFlow<UploadSettings> = _settings.asStateFlow()

    override fun update(transform: (UploadSettings) -> UploadSettings) {
        val next = transform(_settings.value)
        persist(next)
        _settings.value = next
    }

    private fun persist(s: UploadSettings) {
        node.put("server_url", s.serverUrl)
        node.putBoolean("auto_upload_enabled", s.autoUploadEnabled)
        node.putBoolean("wifi_only", s.wifiOnly)
        node.put("auto_upload_license", s.license)
        node.put("preferred_storage", s.storage.key)
        node.putBoolean("hide_from_gallery", s.hideFromGallery)
    }
}
