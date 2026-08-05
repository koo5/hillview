package cz.hillview.upload

import android.content.Context
import cz.hillview.core.net.BackendConfig

/**
 * The shared-kt upload stack configures itself from `hillview_upload_prefs`
 * — in the Tauri app the settings UI writes these. frontend2 has no
 * upload-settings screen yet, so this seeds the DEFAULTS once at app start
 * (they must exist before first login: client-key registration reads
 * server_url). Only missing keys are written — a future settings screen
 * edits the same prefs and its values stick.
 *
 * Note the dev-default divergence: auto_upload_enabled defaults to true
 * here (capture-first app), while the Tauri app ships it off until the user
 * enables it in settings.
 */
fun seedUploadSettings(context: Context, backend: BackendConfig) {
    val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
    val edit = prefs.edit()
    if (!prefs.contains("server_url")) {
        // The full API URL, verbatim — see BackendConfig.
        edit.putString("server_url", backend.apiUrl)
    }
    if (!prefs.contains("auto_upload_enabled")) {
        edit.putBoolean("auto_upload_enabled", true)
    }
    if (!prefs.contains("auto_upload_license")) {
        // Backend vocabulary (user_routes.ALLOWED_LICENSES): 'ccbysa4+osm' | 'full1'.
        edit.putString("auto_upload_license", "ccbysa4+osm")
    }
    edit.apply()
}
