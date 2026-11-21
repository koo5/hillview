package cz.hillview.settings

/**
 * What a healthy capture sounds like. The warning for a degraded position is
 * its own switch ([UploadSettings.warnDegradedPosition]), so the shutter can
 * be silent while the warning still speaks.
 */
enum class ShutterSound(val key: String, val label: String) {
    Click("click", "Click"),
    Beep("beep", "Beep"),
    Off("off", "Off");

    companion object {
        fun fromKey(key: String?): ShutterSound? = entries.firstOrNull { it.key == key }
    }
}

/**
 * Which of the phone's volume controls the capture sounds obey.
 *
 * Why the user picks: the stock MediaActionSound click plays on the system's
 * "enforced" stream, which one phone aliases to the ring volume and another
 * leaves outside every slider, and the warning beep used the notification
 * stream — so the two sounds followed different controls, and which ones
 * varied by device (user-reported, 2026-11-07: "pretty random"). Owning the
 * sounds lets them sit on one named stream.
 */
enum class SoundChannel(val key: String, val label: String, val explanation: String) {
    Media(
        "media", "Media volume",
        "The same control as music and video — the volume keys set it on most phones.",
    ),
    Notification(
        "notification", "Notification volume",
        "Follows the notification volume, so silent and vibrate mode mute it.",
    ),
    Alarm(
        "alarm", "Alarm volume",
        "Plays even in silent mode — for interval runs in a pocket.",
    );

    companion object {
        fun fromKey(key: String?): SoundChannel? = entries.firstOrNull { it.key == key }
    }
}

const val CAPTURE_SOUND_VOLUME_DEFAULT = 1f
