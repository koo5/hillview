package cz.hillview.nav

import androidx.navigation3.runtime.NavKey
import kotlinx.serialization.Serializable

// Route keys for the whole app; screens beyond P0 arrive with their phases.
// Serializable so the back stack survives process death.

/** The app itself: the split Main page (map + activity panel). */
@Serializable
data object MainKey : NavKey

/**
 * Legacy keys, kept registered so a back stack persisted by an older build
 * still deserializes after an update — their entries alias to Main. Home
 * was the pre-merge launcher screen; Map and Capture were destinations
 * before they became Main-page activities.
 */
@Serializable
data object HomeKey : NavKey

@Serializable
data object LoginKey : NavKey

@Serializable
data object ClockVideoKey : NavKey

@Serializable
data object CaptureKey : NavKey

@Serializable
data object SettingsKey : NavKey

/** The /device-photos analog: every capture and its upload fate. */
@Serializable
data object DevicePhotosKey : NavKey

/** The app's own recent events (see EventLogScreen). */
@Serializable
data object EventLogKey : NavKey

/** Why the uploader is or is not running (see UploadStatusScreen). */
@Serializable
data object UploadStatusKey : NavKey

/** The capture-controls manual (gestures follow native conventions). */
@Serializable
data object CaptureGuideKey : NavKey

/** What locking the controls is allowed to do (see ControlsLock). */
@Serializable
data object LockSettingsKey : NavKey

@Serializable
data object MapKey : NavKey

/**
 * One photo on its own — what the shutter's thumbnail opens.
 *
 * The same card the Device photos list draws, because it is the same
 * question asked about one row: where it went, what it is licensed as, what
 * you thought of it. A second, slightly different photo screen would be two
 * places to fix anything said about a photo.
 */
@Serializable
data class PhotoDetailKey(val photoId: String) : NavKey
