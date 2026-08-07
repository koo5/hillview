package cz.hillview.settings

import android.os.Build

/**
 * The storage rules changed repeatedly across Android versions, so the
 * settings screen describes THIS device:
 *
 *  - API 30+ (Android 11): an app may create files in the media collections
 *    (DCIM/…) with the File API — verified on API 36. Android/data stopped
 *    being browsable by other apps' file managers here.
 *  - API 29 (Android 10): scoped storage blocks direct writes into DCIM
 *    (this app does not request the legacy opt-out). MediaStore's
 *    RELATIVE_PATH arrives, so the MediaStore mode works from here on.
 *  - API 24-28: a direct write needs WRITE_EXTERNAL_STORAGE, which this app
 *    does not request; and the MediaStore mode uses RELATIVE_PATH, which
 *    doesn't exist yet. Only the app-private folder is usable — the
 *    fallback chain lands there on its own.
 *
 * A hidden ".Hillview" is skipped by the media scanner, which is the point
 * of that switch.
 */
actual fun storageFacts(mode: StorageMode, hideFromGallery: Boolean): StorageFacts {
    val sdk = Build.VERSION.SDK_INT
    return when (mode) {
        StorageMode.PublicFolder -> StorageFacts(
            inGallery = !hideFromGallery,
            fileManagerReachable = true,
            survivesUninstall = true,
            availableHere = sdk >= Build.VERSION_CODES.R,
            note = when {
                sdk >= Build.VERSION_CODES.R ->
                    "Written straight to the folder, then announced to the gallery."
                sdk == Build.VERSION_CODES.Q ->
                    "Not available on Android 10 — writing here is blocked, so " +
                        "another option is used."
                else ->
                    "Not available on this Android version — it needs a storage " +
                        "permission this app does not ask for."
            },
        )

        StorageMode.PrivateFolder -> StorageFacts(
            inGallery = false,
            // Android 11 closed Android/data to other apps, file managers included.
            fileManagerReachable = sdk < Build.VERSION_CODES.R,
            survivesUninstall = false,
            availableHere = true,
            note = if (sdk >= Build.VERSION_CODES.R) {
                "Only this app can see these photos; connect the phone to a " +
                    "computer to get them out."
            } else {
                "Tucked away in the app's own folder."
            },
        )

        StorageMode.MediaStore -> StorageFacts(
            // Rows go into the media database directly rather than being
            // scanned, so hiding can't apply — verified on API 36, where the
            // system also renamed ".Hillview" to "_.Hillview" on the way in.
            inGallery = true,
            fileManagerReachable = true,
            survivesUninstall = true,
            availableHere = sdk >= Build.VERSION_CODES.Q,
            note = if (sdk < Build.VERSION_CODES.Q) {
                "Not available on this Android version."
            } else if (hideFromGallery) {
                "Handed to the system media database, which does not accept a " +
                    "hidden folder — these photos stay visible. Use DCIM/.Hillview " +
                    "to hide them."
            } else {
                "Handed to the system media database — the option that works " +
                    "when writing the file directly does not."
            },
        )
    }
}
