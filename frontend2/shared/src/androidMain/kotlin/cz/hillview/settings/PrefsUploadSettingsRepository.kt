package cz.hillview.settings

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Android settings live in `hillview_upload_prefs` — the exact prefs the
 * shared-kt upload stack reads (key names are its contract; the Tauri
 * settings UI writes the same ones). Construction materializes defaults for
 * missing keys, so the stack and login-time key registration never see an
 * unconfigured store.
 */
class PrefsUploadSettingsRepository(
    context: Context,
    defaults: UploadSettings,
) : UploadSettingsRepository {
    private val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)

    private val _settings = MutableStateFlow(
        UploadSettings(
            serverUrl = prefs.getString("server_url", null) ?: defaults.serverUrl,
            autoUploadEnabled =
                if (prefs.contains("auto_upload_enabled")) prefs.getBoolean("auto_upload_enabled", false)
                else defaults.autoUploadEnabled,
            wifiOnly =
                if (prefs.contains("wifi_only")) prefs.getBoolean("wifi_only", false)
                else defaults.wifiOnly,
            license = prefs.getString("auto_upload_license", null) ?: defaults.license,
        ).also(::persist)
    )
    override val settings: StateFlow<UploadSettings> = _settings.asStateFlow()

    override fun update(transform: (UploadSettings) -> UploadSettings) {
        val next = transform(_settings.value)
        persist(next)
        _settings.value = next
    }

    private fun persist(s: UploadSettings) {
        prefs.edit()
            .putString("server_url", s.serverUrl)
            .putBoolean("auto_upload_enabled", s.autoUploadEnabled)
            .putBoolean("wifi_only", s.wifiOnly)
            .putString("auto_upload_license", s.license)
            .apply()
    }
}
