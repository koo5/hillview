package cz.hillview.settings

/** No photos table on desktop — there is no capture path to fill one. */
actual fun photoTableDumpLabel(): String? = null

actual suspend fun dumpPhotoTableNow(): String = "not supported on this platform"
