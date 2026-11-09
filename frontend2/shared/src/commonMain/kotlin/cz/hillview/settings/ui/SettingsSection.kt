package cz.hillview.settings.ui

import cz.hillview.settings.LICENSE_INFO
import cz.hillview.settings.MapSettings
import cz.hillview.settings.ShutterSound
import cz.hillview.settings.StorageMode
import cz.hillview.settings.UploadSettings
import kotlinx.serialization.Serializable

/**
 * The Settings sub-pages (user, 2026-11-07: "reorganize the settings menu
 * into proper subscreens"). Settings used to be one long page of ~20
 * controls; it is now this list, each entry its own back-stack page, so
 * system Back leaves a sub-page for the list, and the page survives
 * process death like every other screen.
 *
 * [key] is persisted in the back stack and names the test tags, so it
 * never changes once shipped; [title] is free to.
 */
@Serializable
enum class SettingsSection(val key: String, val title: String) {
    Uploads("uploads", "Uploads & licence"),
    Capture("capture", "Capture"),
    Storage("storage", "Photo files"),
    Location("location", "Location & compass"),
    Servers("servers", "Servers"),
}

/**
 * The one line under a section's name on the list: what is set there,
 * enough to tell without opening it whether anything needs doing.
 */
fun settingsSectionSummary(
    section: SettingsSection,
    upload: UploadSettings,
    map: MapSettings,
    loggedIn: Boolean,
    runtimeApiUrl: String,
): String = when (section) {
    SettingsSection.Uploads -> buildList {
        val license = LICENSE_INFO.firstOrNull { it.id == upload.license }
        if (license == null) {
            add("No licence picked — photos stay on this phone")
        } else {
            add(
                when {
                    !upload.autoUploadEnabled -> "Auto-upload off"
                    upload.wifiOnly -> "Auto-upload on Wi-Fi"
                    else -> "Auto-upload on"
                },
            )
            add(license.label)
        }
        if (!loggedIn) add("not signed in")
    }.joinToString(" · ")

    SettingsSection.Capture -> buildList {
        if (upload.shutterSound == ShutterSound.Off && !upload.warnDegradedPosition) {
            add("Silent")
        } else {
            add("Shutter: " + upload.shutterSound.label.lowercase())
            add(upload.captureSoundChannel.label)
        }
        add(if (map.sfmRunEnabled) "SfM run on" else "SfM run off")
    }.joinToString(" · ")

    SettingsSection.Storage -> buildList {
        add(
            when (upload.storage) {
                StorageMode.PublicFolder -> "DCIM folder"
                StorageMode.MediaStore -> "DCIM via the gallery database"
                StorageMode.PrivateFolder -> "App-private folder"
            },
        )
        if (upload.hideFromGallery) add("hidden from the gallery")
        if (upload.writeExif) add("EXIF written")
    }.joinToString(" · ")

    SettingsSection.Location -> buildList {
        add("Tracking export, compass quirk")
        if (map.showGeoDebug) add("debug readout on")
    }.joinToString(" · ")

    SettingsSection.Servers -> {
        val host = upload.serverUrl.substringAfter("://").substringBefore('/')
        if (upload.serverUrl.trimEnd('/') != runtimeApiUrl.trimEnd('/')) {
            "$host — restart the app to apply"
        } else {
            host
        }
    }
}
