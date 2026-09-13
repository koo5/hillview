package cz.hillview.settings

import kotlinx.coroutines.flow.StateFlow

/**
 * Upload settings. On Android these ARE the shared-kt stack's config: the
 * repository persists them 1:1 into the `hillview_upload_prefs` keys the
 * shared PhotoUploadLogic/PhotoUploadManager/AuthenticationManager read —
 * the same contract the Tauri app's settings UI writes.
 */
/**
 * Where "open in web app" links go. The original hardcodes this
 * (HILLVIEW_BASE_URL in urlUtils.ts) regardless of which API it talks to;
 * here it is a setting with the same default, so a dev backend can pair
 * with a dev web app. Its own value, deliberately — never derived from the
 * API URL by trimming a path segment.
 */
const val HILLVIEW_WEB_URL = "https://hillview.cz"

/**
 * The production API. Its OWN host (api.hillview.cz), which is the whole
 * reason the API URL is a value of its own and never derived from the web
 * root — see BackendConfig.
 */
const val HILLVIEW_API_URL = "https://api.hillview.cz/api"

/** One predefined choice of the API-URL combobox: a name and the FULL …/api URL. */
data class ServerPreset(val label: String, val apiUrl: String)

/**
 * The combobox's predefined choices; anything else is typed. The dev entry
 * is the platform default (on Android the emulator's route to the host
 * machine; on the desktop shell HILLVIEW_BACKEND or localhost), so a phone
 * on the LAN still types its address.
 */
fun serverPresets(): List<ServerPreset> = listOf(
    ServerPreset("Production", HILLVIEW_API_URL),
    ServerPreset("Local dev backend", cz.hillview.core.net.defaultBackendConfig().apiUrl),
)

data class UploadSettings(
    /** The FULL API URL (…/api) — see BackendConfig; never assembled from a host. */
    val serverUrl: String,
    /** The web app's root, for links out of the app — see HILLVIEW_WEB_URL. */
    val webUrl: String = HILLVIEW_WEB_URL,
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
    /**
     * OPT-IN full EXIF in the photo files (GPS, heading, provenance) — for
     * using the files outside the hillview pipeline. OFF is the
     * hillview-centered default: finalization is just the CameraX save
     * (ExifInterface has no surgical patch, so writing EXIF means copying
     * the whole 4–25 MB file per shot — the throughput ceiling the CMP
     * rewrite exists to remove). The stamp is complete either way: it lives
     * in the photos table and rides the upload's metadata field, which the
     * server prefers over file EXIF.
     */
    val writeExif: Boolean = false,
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

/**
 * One grant the user can pick, in their words. [id] is the WRITE
 * vocabulary (the backend's LEGAL_RIGHTS_TO_LICENSE keys); [label] is what
 * the web app shows on read; [explainer] is the substance of the web
 * app's /licensing page in two sentences, for a choice made on a hill
 * without that page to hand. The full1 wording is deliberate: the grant
 * to Hillview is full, and what Hillview does with it TODAY is publish
 * the photo as all-rights-reserved PLUS the same OpenStreetMap mapping
 * grant the CC option carries (the read-side name is 'arr', but the OSM
 * grant is part of that modality) — the two are different facts, and
 * the second may change (docs/todo/content-license-model-draft.md).
 */
data class LicenseInfo(val id: String, val label: String, val explainer: String)

val LICENSE_INFO: List<LicenseInfo> = listOf(
    LicenseInfo(
        id = "ccbysa4+osm",
        label = "CC BY-SA 4.0 + OSM mapping grant",
        explainer = "You keep your copyright. Anyone may copy, share and " +
            "remix the photo, commercially too, as long as they credit you " +
            "and share alike; OpenStreetMap mappers may also trace map data " +
            "from it into OSM. Choose this to contribute to the open commons.",
    ),
    LicenseInfo(
        id = "full1",
        label = "Full rights to Hillview",
        explainer = "You keep your copyright and grant Hillview full rights to " +
            "the photo, including paid tiers later. Hillview currently " +
            "publishes it as all rights reserved plus the same OpenStreetMap " +
            "mapping grant: others can view it here and OSM mappers may trace " +
            "map data from it, but nobody may otherwise reuse it without " +
            "arrangement. Choose this to support the project.",
    ),
)

/** The ids above, in selector order — the backend's ALLOWED_LICENSES. */
val ALLOWED_LICENSES: List<String> = LICENSE_INFO.map { it.id }

/** Human label for a grant id; the id itself for one we do not know. */
fun licenseLabel(id: String): String = LICENSE_INFO.firstOrNull { it.id == id }?.label ?: id

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
