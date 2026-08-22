package cz.hillview.settings

import android.content.Context
import cz.hillview.plugin.PhotoUploadManager
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
    private val context: Context,
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
            license = prefs.getString("auto_upload_license", null),
            storage = StorageMode.fromKey(prefs.getString("preferred_storage", null))
                ?: defaults.storage,
            hideFromGallery =
                if (prefs.contains("hide_from_gallery")) prefs.getBoolean("hide_from_gallery", false)
                else defaults.hideFromGallery,
            autoUploadPromptEnabled = prefs.getBoolean("auto_upload_prompt_enabled", true),
            writeExif = prefs.getBoolean("write_exif", false),
        ).also(::persist)
    )
    override val settings: StateFlow<UploadSettings> = _settings.asStateFlow()

    override fun update(transform: (UploadSettings) -> UploadSettings) {
        val previous = _settings.value
        val next = transform(previous)
        persist(next)
        _settings.value = next

        // Any of these three changes what the schedule SHOULD be: turning
        // auto-upload on must pick up photos captured while it was off (a
        // capture during that time enqueued nothing at all), and flipping the
        // network rule invalidates the constraint baked into whatever is
        // already parked. The reconciler works out which; this only reports
        // that something relevant moved.
        if (next.autoUploadEnabled != previous.autoUploadEnabled ||
            next.wifiOnly != previous.wifiOnly ||
            next.license != previous.license
        ) {
            PhotoUploadManager(context).reconcile("settings_changed")
        }
    }

    private fun persist(s: UploadSettings) {
        prefs.edit()
            .putString("server_url", s.serverUrl)
            .putBoolean("auto_upload_enabled", s.autoUploadEnabled)
            .putBoolean("wifi_only", s.wifiOnly)
            .putString("auto_upload_license", s.license)
            // Same key/vocabulary as the Tauri app's preferred_storage (it
            // keeps it in localStorage; here it joins the other upload prefs).
            .putString("preferred_storage", s.storage.key)
            .putBoolean("hide_from_gallery", s.hideFromGallery)
            .putBoolean("auto_upload_prompt_enabled", s.autoUploadPromptEnabled)
            .putBoolean("write_exif", s.writeExif)
            .apply()
    }
}
