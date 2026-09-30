package cz.hillview.settings

/**
 * The photos-table dump (androidMain's PhotoTableDump), as the settings
 * screen sees it.
 *
 * There is no on/off here on purpose: the dump is what keeps a photo that
 * outlives the app from being meaningless, and a safety net with a switch is
 * one people discover they had turned off. What the screen offers is where it
 * went and a way to write it again.
 */
expect fun photoTableDumpLabel(): String?

/** Writes it now and returns what happened, for showing in place. */
expect suspend fun dumpPhotoTableNow(): String
