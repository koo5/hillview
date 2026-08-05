package cz.hillview.settings

import kotlinx.coroutines.flow.StateFlow

/**
 * Upload settings. On Android these ARE the shared-kt stack's config: the
 * repository persists them 1:1 into the `hillview_upload_prefs` keys the
 * shared PhotoUploadLogic/PhotoUploadManager/AuthenticationManager read —
 * the same contract the Tauri app's settings UI writes.
 */
data class UploadSettings(
    /** The FULL API URL (…/api) — see BackendConfig; never assembled from a host. */
    val serverUrl: String,
    val autoUploadEnabled: Boolean,
    val wifiOnly: Boolean,
    /** Backend vocabulary (user_routes.ALLOWED_LICENSES). */
    val license: String,
)

val ALLOWED_LICENSES = listOf("ccbysa4+osm", "full1")

/**
 * Defaults. autoUploadEnabled is OFF until the user turns it on — a
 * privacy/safety default (same as the Tauri app): captures never leave the
 * device without an explicit opt-in.
 */
fun defaultUploadSettings(apiUrl: String) = UploadSettings(
    serverUrl = apiUrl,
    autoUploadEnabled = false,
    wifiOnly = false,
    license = ALLOWED_LICENSES.first(),
)

/**
 * Owns the persisted settings: implementations materialize defaults for
 * missing keys at construction, so consumers that read the underlying store
 * directly (the shared-kt upload stack, client-key registration at login)
 * always find them populated.
 */
interface UploadSettingsRepository {
    val settings: StateFlow<UploadSettings>
    fun update(transform: (UploadSettings) -> UploadSettings)
}
