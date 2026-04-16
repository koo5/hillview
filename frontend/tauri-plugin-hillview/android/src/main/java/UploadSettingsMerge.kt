package cz.hillview.plugin

import android.content.SharedPreferences
import app.tauri.plugin.JSObject

/**
 * Values produced by merging an incoming partial set_settings params object with
 * the currently-stored preferences. Any field missing from `params` keeps the
 * previous value instead of falling back to a hard-coded default.
 */
data class MergedUploadSettings(
    val autoUploadEnabled: Boolean,
    val autoUploadPromptEnabled: Boolean,
    val autoUploadLicense: String?,
    val wifiOnly: Boolean,
    val landscapeArmor22: Boolean,
)

/**
 * Merge a partial set_settings params object against a baseline snapshot.
 *
 * Uses [JSObject.getBoolean] two-arg overload explicitly so missing keys fall
 * back to the baseline value. The one-arg overload returns `false` for missing
 * keys (see JSObject.kt in tauri-api), which would silently zero-out unspecified
 * settings when callers send a partial params object — the cause of a prior
 * regression where auto-upload prompt and wifi-only were being reset on app
 * restart.
 */
fun mergeUploadSettings(
    params: JSObject,
    previous: MergedUploadSettings,
): MergedUploadSettings = MergedUploadSettings(
    autoUploadEnabled = params.getBoolean("auto_upload_enabled", previous.autoUploadEnabled),
    autoUploadPromptEnabled = params.getBoolean("auto_upload_prompt_enabled", previous.autoUploadPromptEnabled),
    // has() distinguishes "key absent" (keep previous) from "key present but null" (user cleared license)
    autoUploadLicense = if (params.has("auto_upload_license")) params.getString("auto_upload_license") else previous.autoUploadLicense,
    wifiOnly = params.getBoolean("wifi_only", previous.wifiOnly),
    landscapeArmor22 = params.getBoolean("landscape_armor22_workaround", previous.landscapeArmor22),
)

/** Read the current persisted settings out of SharedPreferences. */
fun readStoredUploadSettings(
    uploadPrefs: SharedPreferences,
    compassPrefs: SharedPreferences,
): MergedUploadSettings = MergedUploadSettings(
    autoUploadEnabled = uploadPrefs.getBoolean("auto_upload_enabled", false),
    autoUploadPromptEnabled = uploadPrefs.getBoolean("auto_upload_prompt_enabled", true),
    autoUploadLicense = uploadPrefs.getString("auto_upload_license", null),
    wifiOnly = uploadPrefs.getBoolean("wifi_only", false),
    landscapeArmor22 = compassPrefs.getBoolean("landscape_armor22_workaround", false),
)
