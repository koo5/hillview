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
    val storage: StorageMode,
    /** Save into ".Hillview" instead of "Hillview" (hidden from gallery scans). */
    val hideFromGallery: Boolean,
)

/**
 * Where captures are saved — the same three the Tauri app offers (its
 * device_photos.rs `preferred_storage`), with the same fallback semantics:
 * the preferred target is tried first, the others after it.
 */
enum class StorageMode(val key: String) {
    /** DCIM/Hillview — visible in the gallery, survives uninstall. */
    PublicFolder("public_folder"),

    /** Android/data/<pkg>/files/Pictures/Hillview — no permission, uninstall-deleted. */
    PrivateFolder("private_folder"),

    /** MediaStore insert with RELATIVE_PATH DCIM/Hillview; yields a content:// URI. */
    MediaStore("mediastore_api");

    companion object {
        fun fromKey(key: String?): StorageMode? = entries.firstOrNull { it.key == key }
    }
}

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
    // Matches the Tauri default (device_photos.rs falls back to
    // "public_folder"): photos in the gallery where the user can find them.
    storage = StorageMode.PublicFolder,
    hideFromGallery = false,
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
