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
    /**
     * Backend vocabulary (user_routes.ALLOWED_LICENSES) — or null while the
     * user has not accepted one. Null is load-bearing twice over: the shared
     * upload stack refuses to upload without it ("No upload license
     * configured"), and the settings UI keeps the auto-upload controls inert
     * until it is set. Defaulting to an accepted licence would quietly agree
     * to it on the user's behalf.
     */
    val license: String?,
    val storage: StorageMode,
    /** Save into ".Hillview" instead of "Hillview" (hidden from gallery scans). */
    val hideFromGallery: Boolean,
    /**
     * "Disabled (never prompt)": suppresses the after-capture auto-upload
     * prompt entirely, "so the capture-then-prompt overlay doesn't block
     * rapid-fire clicks".
     */
    val autoUploadPromptEnabled: Boolean = true,
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

/**
 * What a storage choice actually means ON THIS DEVICE. Every one of these
 * depends on the Android version — Android/data stopped being browsable to
 * file managers in 11, direct writes into DCIM were blocked in 10 and need a
 * permission before that, MediaStore's RELATIVE_PATH only exists from 10 —
 * so the settings screen asks the platform instead of stating universals.
 */
data class StorageFacts(
    val inGallery: Boolean,
    val fileManagerReachable: Boolean,
    val survivesUninstall: Boolean,
    /** False when this device can't use the mode at all; the chain falls through. */
    val availableHere: Boolean,
    val note: String,
)

expect fun storageFacts(mode: StorageMode, hideFromGallery: Boolean): StorageFacts

/** The photo folder's display name (build-configurable on Android). */
expect fun storageFolderName(hideFromGallery: Boolean): String

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
    license = null,
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
